"""
Query-first VidSnap workspace routes.
"""
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from ...core.logging import get_context_logger, logger
from ...models.workspace import (
    QueryPlanRequest,
    QueryPlanResponse,
    WorkspaceArtifactCreateRequest,
    WorkspaceJobCreateResponse,
    WorkspaceQARequest,
)
from ...services.llm_gateway_service import llm_gateway
from ...services.planner_service import planner_service
from ...services.skill_registry_service import skill_registry
from ...services.transcription_provider_service import transcription_provider_registry
from ...services.workspace_job_service import WorkspaceJobLimitError, workspace_job_service
from ...services.workspace_service import workspace_service
from ..upload_guards import (
    ALLOWED_VIDEO_EXTENSIONS,
    enforce_media_duration_limit,
    enforce_storage_quota,
    record_user_usage,
    resolve_user_context,
    save_upload_with_size_limit,
)

router = APIRouter(prefix="/workspace", tags=["workspace"])
security = HTTPBearer(auto_error=False)


@router.get("/skills")
async def list_skills():
    """List all externally visible P0 skills."""
    return {
        "status": "success",
        "skills": [skill.dict() for skill in skill_registry.list_skills()],
    }


@router.get("/transcription-providers")
async def list_transcription_providers():
    """List ASR provider adapters."""
    transcription_provider_registry.refresh()
    return {
        "status": "success",
        "providers": [
            provider.__dict__
            for provider in transcription_provider_registry.list_providers()
        ],
    }


@router.post("/plan", response_model=QueryPlanResponse)
async def create_plan(payload: QueryPlanRequest):
    """Preview a structured skill plan for a user query."""
    if not payload.query.strip():
        raise HTTPException(status_code=400, detail="query 不能为空")

    try:
        plan = planner_service.create_plan(payload.query, payload.force_skills, payload.visual_mode)
        validation = skill_registry.validate_plan(plan)
        return QueryPlanResponse(status="success", plan=plan, validation=validation)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/jobs", response_model=WorkspaceJobCreateResponse)
async def create_workspace_job(
    request: Request,
    video_file: Optional[UploadFile] = File(None),
    video_url: str = Form(""),
    query: str = Form(...),
    provider: str = Form("paraformer"),
    force_skills: str = Form(""),
    visual_mode: str = Form("auto"),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
):
    """Create a recoverable async workspace job."""
    ctx_logger = get_context_logger()
    forced_skills = [s.strip() for s in force_skills.split(",") if s.strip()]

    if not query.strip():
        raise HTTPException(status_code=400, detail="query 不能为空")

    video_url = (video_url or "").strip()
    has_file = bool(video_file and video_file.filename)
    if not has_file and not video_url:
        raise HTTPException(status_code=400, detail="必须上传本地视频文件，或提供 YouTube 链接")

    user_id, quota = await resolve_user_context(credentials)
    upload_dir = tempfile.mkdtemp(prefix="vidsnap_workspace_job_")

    try:
        if video_url:
            # YouTube 链接 → FetchYouTube skill 下载到本地，再走现有链路（不对反爬兜底）
            from ..services.youtube_service import fetch_youtube, is_youtube_url, YouTubeFetchError
            if not is_youtube_url(video_url):
                raise HTTPException(status_code=400, detail="目前仅支持 YouTube 链接")
            try:
                video_path = await fetch_youtube(video_url, upload_dir)
            except YouTubeFetchError as e:
                raise HTTPException(status_code=502, detail=str(e))
            safe_filename = Path(video_path).name
            upload_bytes = os.path.getsize(video_path)
        else:
            file_suffix = Path(video_file.filename).suffix.lower()
            if file_suffix not in ALLOWED_VIDEO_EXTENSIONS:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"不支持的视频格式: {file_suffix or 'unknown'}，"
                        "请上传 MP4、MOV、MKV、AVI、WEBM 或 M4V 文件"
                    ),
                )
            safe_filename = Path(video_file.filename).name
            video_path = os.path.join(upload_dir, safe_filename)
            upload_bytes = await save_upload_with_size_limit(video_file, video_path)

        enforce_storage_quota(quota, upload_bytes)
        await enforce_media_duration_limit(video_path, quota)

        job = await workspace_job_service.create_job(
            video_file_path=video_path,
            original_filename=safe_filename,
            query=query.strip(),
            user_id=user_id,
            provider=provider,
            force_skills=forced_skills,
            visual_mode=visual_mode,
        )

        ctx_logger.info(
            "workspace job accepted",
            job_id=job.job_id,
            file_name=video_file.filename,
            query=query,
            client_host=request.client.host if request.client else "unknown",
        )
        return WorkspaceJobCreateResponse(status="success", job_id=job.job_id, job=job)
    except WorkspaceJobLimitError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        ctx_logger.exception(f"workspace job 创建失败: {e}")
        raise HTTPException(status_code=500, detail=f"workspace job 创建失败: {str(e)}")
    finally:
        try:
            import shutil
            shutil.rmtree(upload_dir, ignore_errors=True)
        except Exception as e:
            logger.warning(f"清理 workspace job 上传临时文件失败: {e}")


@router.get("/jobs/{job_id}")
async def get_workspace_job(job_id: str):
    job = workspace_job_service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return {"status": "success", "job": job}


@router.get("/jobs/{job_id}/artifact")
async def get_workspace_job_artifact(job_id: str):
    response = workspace_job_service.get_artifact_response(job_id)
    if not response:
        raise HTTPException(status_code=404, detail="artifact not ready")
    return response


@router.get("/jobs/{job_id}/token-usage")
async def get_workspace_job_token_usage(job_id: str):
    """返回该 job 处理过程中消耗的 LLM token 汇总（输入/输出/图像，按模型细分）。"""
    if not workspace_job_service.get_job(job_id):
        raise HTTPException(status_code=404, detail="job not found")
    usage = workspace_job_service.token_usage.get(job_id)
    if usage is None:
        raise HTTPException(status_code=404, detail="token usage not ready")
    return {"status": "success", "job_id": job_id, "token_usage": usage}


@router.get("/token-usage")
async def get_global_token_usage():
    """返回进程启动以来所有 LLM 调用的 token 累计（全局，跨所有 job）。"""
    return {"status": "success", "token_usage": llm_gateway.global_stats().to_dict()}


@router.post("/jobs/{job_id}/retry")
async def retry_workspace_job(job_id: str):
    try:
        job = await workspace_job_service.retry_job(job_id)
        return {"status": "success", "job_id": job_id, "job": job}
    except KeyError:
        raise HTTPException(status_code=404, detail="job not found")
    except WorkspaceJobLimitError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/jobs/{job_id}/artifacts")
async def create_workspace_job_artifact_version(job_id: str, payload: WorkspaceArtifactCreateRequest):
    if not payload.query.strip():
        raise HTTPException(status_code=400, detail="query 不能为空")
    try:
        return await workspace_job_service.create_artifact_version(job_id, payload)
    except KeyError:
        raise HTTPException(status_code=404, detail="job not found")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/jobs/{job_id}/qa")
async def ask_workspace_job(job_id: str, payload: WorkspaceQARequest):
    if not payload.question.strip():
        raise HTTPException(status_code=400, detail="question 不能为空")
    try:
        return workspace_job_service.answer_question(job_id, payload.question, payload.top_k)
    except KeyError:
        raise HTTPException(status_code=404, detail="job not found")


@router.get("/jobs/{job_id}/events")
async def stream_workspace_job_events(job_id: str):
    if not workspace_job_service.get_job(job_id):
        raise HTTPException(status_code=404, detail="job not found")
    return StreamingResponse(
        workspace_job_service.event_snapshots(job_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache"},
    )


@router.post("/process")
async def process_workspace_query(
    request: Request,
    video_file: UploadFile = File(...),
    query: str = Form(...),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
):
    """
    Execute the P0 flow: local video + natural language query -> plan -> artifact.
    """
    ctx_logger = get_context_logger()
    start_time = time.time()

    if not query.strip():
        raise HTTPException(status_code=400, detail="query 不能为空")

    if not video_file or not video_file.filename:
        raise HTTPException(status_code=400, detail="必须上传本地视频文件")

    file_suffix = Path(video_file.filename).suffix.lower()
    if file_suffix not in ALLOWED_VIDEO_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"不支持的视频格式: {file_suffix or 'unknown'}，"
                "请上传 MP4、MOV、MKV、AVI、WEBM 或 M4V 文件"
            ),
        )

    user_id, quota = await resolve_user_context(credentials)

    video_path = None
    upload_bytes = 0
    reservation_id = None
    try:
        upload_dir = tempfile.mkdtemp(prefix="vidsnap_workspace_")
        safe_filename = Path(video_file.filename).name
        video_path = os.path.join(upload_dir, safe_filename)

        upload_bytes = await save_upload_with_size_limit(video_file, video_path)
        enforce_storage_quota(quota, upload_bytes)
        await enforce_media_duration_limit(video_path, quota)
        reservation_id = await workspace_job_service.reserve_processing_slot()

        ctx_logger.info(
            "执行 query-first workspace 任务",
            file_name=video_file.filename,
            query=query,
            client_host=request.client.host if request.client else "unknown",
        )

        response = await workspace_service.process_video_query(
            video_file_path=video_path,
            original_filename=safe_filename,
            query=query,
            user_id=user_id,
        )

        if response.status == "success":
            await record_user_usage(user_id, upload_bytes)

        ctx_logger.info(
            "workspace 任务完成",
            duration_ms=round((time.time() - start_time) * 1000, 2),
            artifact_type=response.artifact.artifact_type,
            video_id=response.video_asset.video_id,
        )
        return response
    except WorkspaceJobLimitError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        ctx_logger.exception(f"workspace 任务失败: {e}")
        raise HTTPException(status_code=500, detail=f"workspace 任务失败: {str(e)}")
    finally:
        if reservation_id:
            await workspace_job_service.release_processing_slot(reservation_id)
        if video_path and os.path.exists(video_path):
            try:
                os.remove(video_path)
                parent_dir = os.path.dirname(video_path)
                if parent_dir.startswith(tempfile.gettempdir()) and os.path.isdir(parent_dir):
                    os.rmdir(parent_dir)
            except Exception as e:
                logger.warning(f"清理 workspace 临时文件失败: {e}")


@router.get("/evals/planner")
async def evaluate_planner():
    """
    Evaluate deterministic planner against the 100-query P0 golden set.
    """
    eval_path = Path(__file__).resolve().parents[2] / "evals" / "planner_eval_set.json"
    if not eval_path.exists():
        raise HTTPException(status_code=404, detail="planner eval set not found")

    cases = json.loads(eval_path.read_text(encoding="utf-8"))
    total = len(cases)
    required_hits = 0
    forbidden_violations = 0
    artifact_hits = 0

    failures = []
    for case in cases:
        plan = planner_service.create_plan(case["query"])
        planned_skills = {step.skill for step in plan.steps}
        required = set(case["required_skills"])
        forbidden = set(case.get("forbidden_skills", []))

        missing = sorted(required - planned_skills)
        forbidden_used = sorted(forbidden & planned_skills)

        if not missing:
            required_hits += 1
        if not forbidden_used:
            forbidden_violations += 1
        if plan.artifact_type == case["expected_artifact"]:
            artifact_hits += 1
        if missing or forbidden_used or plan.artifact_type != case["expected_artifact"]:
            failures.append(
                {
                    "id": case["id"],
                    "query": case["query"],
                    "expected_artifact": case["expected_artifact"],
                    "actual_artifact": plan.artifact_type,
                    "missing_required": missing,
                    "forbidden_used": forbidden_used,
                }
            )

    selection_accuracy = required_hits / total if total else 0
    unnecessary_skill_pass_rate = forbidden_violations / total if total else 0
    artifact_accuracy = artifact_hits / total if total else 0
    passes_p0 = (
        total >= 100
        and selection_accuracy >= 0.85
        and (1 - unnecessary_skill_pass_rate) <= 0.15
        and artifact_accuracy >= 0.85
    )

    return {
        "status": "success",
        "total": total,
        "selection_accuracy": round(selection_accuracy, 4),
        "unnecessary_skill_rate": round(1 - unnecessary_skill_pass_rate, 4),
        "artifact_accuracy": round(artifact_accuracy, 4),
        "passes_p0": passes_p0,
        "failures": failures[:20],
    }
