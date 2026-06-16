"""
In-process workspace job runner.

This is intentionally local-first for Slim P0/P1/P2 development. The API shape
keeps the processing contract async and recoverable, while the runner can later
be replaced by Celery/RQ without changing the frontend contract.
"""
import asyncio
import math
import os
import shutil
import subprocess
import tempfile
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..core.config import settings
from ..core.logging import logger
from ..models.workspace import (
    ArtifactVersion,
    PlanValidationResult,
    SkillPlan,
    TranscriptIndexEntry,
    WorkspaceArtifactCreateRequest,
    WorkspaceCostEstimate,
    WorkspaceJobArtifactResponse,
    WorkspaceJobStatus,
    WorkspaceProcessResponse,
    WorkspaceQAResponse,
)
from .planner_service import planner_service
from .skill_registry_service import skill_registry
from .transcription_provider_service import transcription_provider_registry
from .workspace_service import workspace_service


class WorkspaceJobService:
    """Manage query-first video jobs inside the API process."""

    def __init__(self) -> None:
        self.jobs: Dict[str, WorkspaceJobStatus] = {}
        self.results: Dict[str, WorkspaceProcessResponse] = {}
        self.artifact_versions: Dict[str, List[ArtifactVersion]] = {}
        self.input_paths: Dict[str, str] = {}
        self.user_ids: Dict[str, Optional[str]] = {}
        self.tasks: Dict[str, asyncio.Task] = {}
        self._lock = asyncio.Lock()

    async def create_job(
        self,
        video_file_path: str,
        original_filename: str,
        query: str,
        user_id: Optional[str] = None,
        provider: str = "paraformer",
        start_immediately: bool = True,
    ) -> WorkspaceJobStatus:
        plan = planner_service.create_plan(query)
        validation = skill_registry.validate_plan(plan)
        if not validation.valid:
            raise ValueError("; ".join(validation.errors))

        job_id = f"job_{uuid.uuid4().hex[:16]}"
        saved_path = self._persist_input(video_file_path, job_id, original_filename)
        now = self._now()
        job = WorkspaceJobStatus(
            job_id=job_id,
            status="queued",
            stage="queued",
            progress=5,
            message="Job accepted and queued",
            query=query,
            original_filename=Path(original_filename).name,
            created_at=now,
            updated_at=now,
            attempts=0,
            max_attempts=3,
            plan=plan,
            validation=validation,
            skill_trace=workspace_service._initial_trace(plan.steps),
            cost_estimate=await self._estimate(saved_path, provider),
        )

        async with self._lock:
            self.jobs[job_id] = job
            self.input_paths[job_id] = saved_path
            self.user_ids[job_id] = user_id
            self.artifact_versions[job_id] = []

        if start_immediately:
            self._start_task(job_id)

        return job

    def get_job(self, job_id: str) -> Optional[WorkspaceJobStatus]:
        return self.jobs.get(job_id)

    def get_artifact_response(self, job_id: str) -> Optional[WorkspaceJobArtifactResponse]:
        result = self.results.get(job_id)
        if not result:
            return None
        return WorkspaceJobArtifactResponse(
            status="success",
            job_id=job_id,
            video_asset=result.video_asset,
            plan=result.plan,
            validation=result.validation,
            artifact=result.artifact,
            artifact_versions=self.artifact_versions.get(job_id, []),
            transcript_index=result.transcript_index,
            skill_trace=result.skill_trace,
        )

    async def retry_job(self, job_id: str) -> WorkspaceJobStatus:
        job = self._require_job(job_id)
        if job.status == "running":
            return job
        if not job.retryable:
            raise ValueError("job is not retryable")
        if job.attempts >= job.max_attempts:
            raise ValueError("job has reached max attempts")
        if not self.input_paths.get(job_id) or not os.path.exists(self.input_paths[job_id]):
            raise ValueError("saved input file is no longer available")

        self._update(
            job_id,
            status="queued",
            stage="queued",
            progress=max(job.progress, 5),
            message="Retry queued from saved input",
            retryable=False,
            error=None,
            failed_stage=None,
        )
        self._start_task(job_id)
        return self._require_job(job_id)

    async def create_artifact_version(
        self,
        job_id: str,
        request: WorkspaceArtifactCreateRequest,
    ) -> WorkspaceJobArtifactResponse:
        result = self.results.get(job_id)
        if not result:
            raise ValueError("job does not have transcript context yet")

        next_result = workspace_service.create_artifact_from_existing(
            result,
            request.query,
            plan=request.plan,
        )
        self.results[job_id] = next_result
        self._append_artifact_version(job_id, next_result, request.query)
        self._update(
            job_id,
            artifact_available=True,
            artifact_versions_count=len(self.artifact_versions.get(job_id, [])),
            message="New artifact version created",
        )
        artifact_response = self.get_artifact_response(job_id)
        if artifact_response is None:
            raise ValueError("artifact response unavailable")
        return artifact_response

    def answer_question(self, job_id: str, question: str, top_k: int = 5) -> WorkspaceQAResponse:
        job = self._require_job(job_id)
        result = self.results.get(job_id)
        transcript_index = result.transcript_index if result else []
        locations = workspace_service._find_locations(question, transcript_index, limit=max(top_k, 1))

        if locations:
            evidence = "\n".join(
                f"- [{workspace_service._format_range(seg.start_time, seg.end_time)}] {seg.text}"
                for seg in locations
            )
            prefix = "Partial answer from currently available transcript context.\n\n" if job.status != "succeeded" else ""
            answer = f"{prefix}{evidence}"
        else:
            suffix = " Processing is still running." if job.status == "running" else ""
            answer = f"No transcript segment confidently matched the question.{suffix}"

        return WorkspaceQAResponse(
            status="success",
            job_id=job_id,
            partial=job.status != "succeeded",
            answer=answer,
            citations=workspace_service._citations_from_segments(locations),
        )

    async def event_snapshots(self, job_id: str):
        last_payload = None
        while True:
            job = self.get_job(job_id)
            if not job:
                yield 'event: error\ndata: {"detail":"job not found"}\n\n'
                return

            payload = job.json()
            if payload != last_payload:
                yield f"event: job\ndata: {payload}\n\n"
                last_payload = payload

            if job.status in {"succeeded", "failed", "canceled"}:
                return
            await asyncio.sleep(1)

    async def run_job(self, job_id: str) -> None:
        job = self._require_job(job_id)
        input_path = self.input_paths.get(job_id)
        if not input_path:
            self._fail(job_id, "Saved input path is missing", retryable=False)
            return

        self._update(
            job_id,
            status="running",
            stage="ingesting",
            progress=max(job.progress, 10),
            attempts=job.attempts + 1,
            message="Processing started",
        )

        try:
            start = time.time()
            result = await workspace_service.process_video_query(
                video_file_path=input_path,
                original_filename=job.original_filename,
                query=job.query,
                user_id=self.user_ids.get(job_id),
                progress_callback=lambda message: self._progress_from_pipeline(job_id, message),
            )
            self.results[job_id] = result
            self._append_artifact_version(job_id, result, job.query)
            self._update(
                job_id,
                status="succeeded",
                stage="completed",
                progress=100,
                message=f"Completed in {time.time() - start:.1f}s",
                retryable=False,
                error=None,
                failed_stage=None,
                skill_trace=result.skill_trace,
                artifact_available=True,
                artifact_versions_count=len(self.artifact_versions.get(job_id, [])),
                transcript_segments_count=len(result.transcript_index),
                partial=False,
            )
            # 成功后产物（transcript_index / artifact）已驻留内存，原始视频不再需要。
            self._cleanup_input(job_id)
        except Exception as exc:
            current_stage = self._require_job(job_id).stage
            error = str(exc)
            classification = transcription_provider_registry.classify_error(
                job.cost_estimate.provider,
                error,
            )
            retryable = bool(classification["retryable"]) or self._looks_retryable(error)
            failure_stage = getattr(exc, "failure_stage", None) or self._infer_failure_stage(error)
            if failure_stage == "failed":
                failure_stage = current_stage
            self._fail(job_id, error, retryable=retryable, failed_stage=failure_stage)
            # 仅在无法再重试时清理输入；可重试失败必须保留以支持 /retry。
            failed_job = self._require_job(job_id)
            if not failed_job.retryable or failed_job.attempts >= failed_job.max_attempts:
                self._cleanup_input(job_id)
        finally:
            self.tasks.pop(job_id, None)

    def _start_task(self, job_id: str) -> None:
        existing = self.tasks.get(job_id)
        if existing and not existing.done():
            return
        self.tasks[job_id] = asyncio.create_task(self.run_job(job_id))

    def _persist_input(self, source_path: str, job_id: str, original_filename: str) -> str:
        root = Path(settings.TEMP_DIR or tempfile.gettempdir()) / "workspace_jobs" / job_id
        root.mkdir(parents=True, exist_ok=True)
        safe_name = Path(original_filename).name or "uploaded_video"
        target = root / safe_name
        shutil.copy2(source_path, target)
        return str(target)

    def _cleanup_input(self, job_id: str) -> None:
        """删除作业的持久化输入视频及其目录（到达不可重试的终态后调用）。"""
        path = self.input_paths.get(job_id)
        if not path:
            return
        try:
            if os.path.exists(path):
                os.remove(path)
            parent = os.path.dirname(path)
            if parent and os.path.isdir(parent):
                os.rmdir(parent)
        except OSError as exc:
            logger.warning(f"清理 workspace job 输入文件失败 ({job_id}): {exc}")

    async def _estimate(self, path: str, provider: str) -> WorkspaceCostEstimate:
        file_bytes = os.path.getsize(path) if os.path.exists(path) else 0
        file_mb = file_bytes / (1024 * 1024)
        # ffprobe 是阻塞调用，放到线程里执行，避免卡住事件循环。
        duration_seconds = await asyncio.to_thread(self._probe_duration_seconds, path)
        if duration_seconds and duration_seconds > 0:
            estimated_minutes = duration_seconds / 60
            estimate_source = "media_duration"
        else:
            estimated_minutes = max(file_mb / 2.6, 1) if file_mb else 0
            estimate_source = "file_size_fallback"

        chunk_seconds = max(settings.PARAFORMER_CHUNK_SECONDS, 1)
        estimated_seconds = duration_seconds or estimated_minutes * 60
        estimated_chunks = max(math.ceil(estimated_seconds / chunk_seconds), 1)
        audio_format = settings.PARAFORMER_AUDIO_FORMAT or "flac"
        audio_mb_per_minute = 1.9 if audio_format == "wav" else 1.6
        estimated_audio_mb = (
            estimated_minutes * audio_mb_per_minute
            if duration_seconds
            else file_mb * (0.42 if audio_format == "wav" else 0.35)
        )
        return WorkspaceCostEstimate(
            source_file_bytes=file_bytes,
            source_file_mb=round(file_mb, 2),
            source_duration_seconds=round(duration_seconds, 2) if duration_seconds else None,
            estimated_audio_mb=round(estimated_audio_mb, 2),
            estimated_transcript_minutes=round(estimated_minutes, 1),
            provider=provider,
            estimated_audio_format=audio_format,
            chunking_expected=estimated_chunks > 1,
            chunk_seconds=chunk_seconds,
            estimated_chunks=estimated_chunks,
            estimate_source=estimate_source,
        )

    def _probe_duration_seconds(self, path: str) -> Optional[float]:
        if not path or not os.path.exists(path):
            return None

        try:
            completed = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    path,
                ],
                capture_output=True,
                check=False,
                text=True,
                timeout=8,
            )
        except Exception as exc:
            logger.warning(f"Workspace cost estimate ffprobe failed: {exc}")
            return None

        if completed.returncode != 0:
            logger.warning(f"Workspace cost estimate ffprobe returned {completed.returncode}: {completed.stderr[:300]}")
            return None

        try:
            duration = float((completed.stdout or "").strip() or 0)
        except ValueError:
            return None

        return duration if duration > 0 else None

    def _append_artifact_version(
        self,
        job_id: str,
        result: WorkspaceProcessResponse,
        query: str,
    ) -> None:
        versions = self.artifact_versions.setdefault(job_id, [])
        versions.append(
            ArtifactVersion(
                version=len(versions) + 1,
                artifact=result.artifact,
                query=query,
                plan_id=result.plan.plan_id,
                created_at=self._now(),
            )
        )

    def _progress_from_pipeline(self, job_id: str, message: str) -> None:
        normalized = message.lower()
        stage = "ingesting"
        progress = 15
        if "处理视频文件" in message or "开始处理视频" in message:
            stage, progress = "ingesting", 15
        elif "音频" in message and "上传" in message:
            stage, progress = "uploading_audio", 45
        elif "转录" in message:
            stage, progress = "transcribing", 55
        elif "音频" in message and "提取" in message:
            stage, progress = "extracting_audio", 35
        elif "metadata" in normalized:
            stage, progress = "indexing", 70
        elif "总结" in message or "artifact" in normalized:
            stage, progress = "generating_artifact", 85
        elif "完成" in message:
            stage, progress = "completed", 95

        self._update(
            job_id,
            stage=stage,
            progress=max(self._require_job(job_id).progress, progress),
            message=message,
        )

    def _fail(
        self,
        job_id: str,
        error: str,
        retryable: bool,
        failed_stage: Optional[str] = None,
    ) -> None:
        failed_stage = self._normalize_failure_stage(failed_stage) or self._infer_failure_stage(error)
        self._update(
            job_id,
            status="failed",
            stage="failed",
            progress=self._require_job(job_id).progress,
            message="Processing failed",
            error=error,
            retryable=retryable,
            failed_stage=failed_stage,
            partial=bool(self.results.get(job_id)),
        )

    def _update(self, job_id: str, **updates: Any) -> None:
        job = self._require_job(job_id)
        data = job.model_dump() if hasattr(job, "model_dump") else job.dict()
        data.update(updates)
        data["updated_at"] = self._now()
        self.jobs[job_id] = WorkspaceJobStatus(**data)

    def _require_job(self, job_id: str) -> WorkspaceJobStatus:
        job = self.jobs.get(job_id)
        if not job:
            raise KeyError(f"job not found: {job_id}")
        return job

    @staticmethod
    def _looks_retryable(error: str) -> bool:
        normalized = (error or "").lower()
        return any(
            token in normalized
            for token in (
                "timeout",
                "timed out",
                "connection",
                "ssl",
                "unexpected_eof",
                "max retries",
                "temporarily unavailable",
                "429",
                "502",
                "503",
                "504",
            )
        )

    @staticmethod
    def _normalize_failure_stage(stage: Optional[str]) -> Optional[str]:
        valid_stages = {
            "uploaded",
            "planning",
            "queued",
            "ingesting",
            "extracting_audio",
            "uploading_audio",
            "transcribing",
            "indexing",
            "generating_artifact",
            "completed",
            "failed",
        }
        return stage if stage in valid_stages else None

    @classmethod
    def _infer_failure_stage(cls, error: str) -> str:
        normalized = (error or "").lower()
        if any(token in normalized for token in ("oss", "upload_audio", "上传")):
            return "uploading_audio"
        if any(token in normalized for token in ("transcrib", "transcript", "transcription", "asr", "paraformer", "dashscope", "转录")):
            return "transcribing"
        if any(token in normalized for token in ("ffmpeg", "extract", "音频提取")):
            return "extracting_audio"
        return "failed"

    @staticmethod
    def _now() -> str:
        return datetime.now().isoformat()


workspace_job_service = WorkspaceJobService()
