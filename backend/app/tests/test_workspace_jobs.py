from pathlib import Path

import pytest

from app.models.workspace import (
    Artifact,
    TranscriptIndexEntry,
    VideoAsset,
    WorkspaceArtifactCreateRequest,
    WorkspaceProcessResponse,
)
from app.services.planner_service import planner_service
from app.services.skill_registry_service import skill_registry
from app.services.workspace_job_service import (
    WorkspaceConcurrencyLimitError,
    WorkspaceJobLimitError,
    WorkspaceJobService,
)
from app.services.workspace_service import WorkspaceProcessingError
from app.services import workspace_job_service as job_module


def _response(query: str) -> WorkspaceProcessResponse:
    plan = planner_service.create_plan(query)
    validation = skill_registry.validate_plan(plan)
    transcript_index = [
        TranscriptIndexEntry(
            segment_index=0,
            text="The video explains transformer attention and PyTorch training.",
            start_time=12.0,
            end_time=25.0,
            confidence=0.95,
            chunk_id="chunk_000",
            provider="paraformer",
        )
    ]
    artifact = Artifact(
        artifact_id="artifact_test",
        artifact_type=plan.artifact_type,
        title="Test Artifact",
        content="Transformer attention notes",
        citations=[
            {
                "segment_index": 0,
                "start_time": 12.0,
                "end_time": 25.0,
                "text": transcript_index[0].text,
            }
        ],
    )
    return WorkspaceProcessResponse(
        status="success",
        video_asset=VideoAsset(
            video_id="video_test",
            title="Transformer Test",
            duration=60,
            processing_status="completed",
            transcript_segments_count=1,
            summary_generated=True,
            metadata={},
        ),
        plan=plan,
        validation=validation,
        artifact=artifact,
        transcript_index=transcript_index,
        skill_trace=[],
    )


@pytest.mark.asyncio
async def test_workspace_job_success_creates_artifact_version(tmp_path, monkeypatch):
    service = WorkspaceJobService()
    video = tmp_path / "sample.webm"
    video.write_bytes(b"video")

    async def fake_process(**kwargs):
        return _response(kwargs["query"])

    monkeypatch.setattr(job_module.workspace_service, "process_video_query", fake_process)

    job = await service.create_job(
        str(video),
        "sample.webm",
        "把视频整理成结构化笔记",
        start_immediately=False,
    )
    await service.run_job(job.job_id)

    status = service.get_job(job.job_id)
    assert status is not None
    assert status.status == "succeeded"
    assert status.progress == 100
    assert status.artifact_available is True
    assert status.artifact_versions_count == 1

    artifact_response = service.get_artifact_response(job.job_id)
    assert artifact_response is not None
    assert artifact_response.artifact_versions[0].version == 1
    assert artifact_response.transcript_index[0].chunk_id == "chunk_000"
    assert artifact_response.transcript_index[0].provider == "paraformer"

    # 成功后原始输入视频应被清理，产物仍可读取。
    assert not Path(service.input_paths[job.job_id]).exists()


@pytest.mark.asyncio
async def test_workspace_job_non_retryable_failure_cleans_input(tmp_path, monkeypatch):
    service = WorkspaceJobService()
    video = tmp_path / "sample.webm"
    video.write_bytes(b"video")

    async def fake_process(**_kwargs):
        raise ValueError("unsupported codec, not a transient error")

    monkeypatch.setattr(job_module.workspace_service, "process_video_query", fake_process)

    job = await service.create_job(
        str(video),
        "sample.webm",
        "转录这个视频",
        start_immediately=False,
    )
    await service.run_job(job.job_id)

    status = service.get_job(job.job_id)
    assert status is not None
    assert status.status == "failed"
    assert status.retryable is False
    # 不可重试的终态应清理输入文件。
    assert not Path(service.input_paths[job.job_id]).exists()


@pytest.mark.asyncio
async def test_workspace_job_failure_is_retryable_and_keeps_input(tmp_path, monkeypatch):
    service = WorkspaceJobService()
    video = tmp_path / "sample.webm"
    video.write_bytes(b"video")

    async def fake_process(**_kwargs):
        raise RuntimeError("SSLError unexpected_eof while submitting transcription")

    monkeypatch.setattr(job_module.workspace_service, "process_video_query", fake_process)

    job = await service.create_job(
        str(video),
        "sample.webm",
        "转录这个视频",
        start_immediately=False,
    )
    await service.run_job(job.job_id)

    status = service.get_job(job.job_id)
    assert status is not None
    assert status.status == "failed"
    assert status.retryable is True
    assert status.failed_stage == "transcribing"
    assert status.attempts == 1
    assert Path(service.input_paths[job.job_id]).exists()


@pytest.mark.asyncio
async def test_workspace_job_failure_uses_pipeline_failure_stage(tmp_path, monkeypatch):
    service = WorkspaceJobService()
    video = tmp_path / "sample.webm"
    video.write_bytes(b"video")

    async def fake_process(**_kwargs):
        raise WorkspaceProcessingError(
            "音频转录失败：DashScope ASR submission SSL error",
            failure_stage="transcribing",
        )

    monkeypatch.setattr(job_module.workspace_service, "process_video_query", fake_process)

    job = await service.create_job(
        str(video),
        "sample.webm",
        "转录这个视频",
        start_immediately=False,
    )
    await service.run_job(job.job_id)

    status = service.get_job(job.job_id)
    assert status is not None
    assert status.status == "failed"
    assert status.failed_stage == "transcribing"
    assert status.retryable is True


@pytest.mark.asyncio
async def test_workspace_job_estimate_uses_media_duration(tmp_path, monkeypatch):
    service = WorkspaceJobService()
    video = tmp_path / "sample.mov"
    video.write_bytes(b"0" * 1024)

    monkeypatch.setattr(service, "_probe_duration_seconds", lambda _path: 1243.316667)
    monkeypatch.setattr(job_module.settings, "PARAFORMER_CHUNK_SECONDS", 1800)
    monkeypatch.setattr(job_module.settings, "PARAFORMER_AUDIO_FORMAT", "flac")

    job = await service.create_job(
        str(video),
        "sample.mov",
        "整理成结构化笔记",
        start_immediately=False,
    )

    estimate = job.cost_estimate
    assert estimate.estimate_source == "media_duration"
    assert estimate.source_duration_seconds == 1243.32
    assert estimate.estimated_transcript_minutes == 20.7
    assert estimate.estimated_audio_format == "flac"
    assert estimate.estimated_audio_mb == 33.16
    assert estimate.estimated_chunks == 1
    assert estimate.chunking_expected is False


@pytest.mark.asyncio
async def test_workspace_job_artifact_version_and_qa(tmp_path, monkeypatch):
    service = WorkspaceJobService()
    video = tmp_path / "sample.webm"
    video.write_bytes(b"video")

    async def fake_process(**kwargs):
        return _response(kwargs["query"])

    monkeypatch.setattr(job_module.workspace_service, "process_video_query", fake_process)

    job = await service.create_job(
        str(video),
        "sample.webm",
        "生成摘要",
        start_immediately=False,
    )
    await service.run_job(job.job_id)

    artifact_response = await service.create_artifact_version(
        job.job_id,
        WorkspaceArtifactCreateRequest(query="帮我定位 attention 的片段"),
    )
    assert len(artifact_response.artifact_versions) == 2

    answer = service.answer_question(job.job_id, "attention 在哪里", top_k=3)
    assert answer.status == "success"
    assert answer.partial is False
    assert answer.citations


@pytest.mark.asyncio
async def test_workspace_job_rejects_file_over_global_limit(tmp_path, monkeypatch):
    service = WorkspaceJobService()
    video = tmp_path / "large.webm"
    video.write_bytes(b"12345")

    monkeypatch.setattr(job_module.settings, "MAX_UPLOAD_BYTES", 4)

    with pytest.raises(WorkspaceJobLimitError) as exc_info:
        await service.create_job(
            str(video),
            "large.webm",
            "转录这个视频",
            start_immediately=False,
        )

    assert exc_info.value.status_code == 413
    assert "too large" in str(exc_info.value)


@pytest.mark.asyncio
async def test_workspace_job_rejects_duration_over_global_limit(tmp_path, monkeypatch):
    service = WorkspaceJobService()
    video = tmp_path / "long.webm"
    video.write_bytes(b"video")

    monkeypatch.setattr(job_module.settings, "MAX_UPLOAD_BYTES", 1024)
    monkeypatch.setattr(job_module.settings, "MAX_MEDIA_DURATION_SECONDS", 60)
    monkeypatch.setattr(service, "_probe_duration_seconds", lambda _path: 61.2)

    with pytest.raises(WorkspaceJobLimitError) as exc_info:
        await service.create_job(
            str(video),
            "long.webm",
            "转录这个视频",
            start_immediately=False,
        )

    assert exc_info.value.status_code == 422
    assert "too long" in str(exc_info.value)


@pytest.mark.asyncio
async def test_workspace_job_concurrency_limit(tmp_path, monkeypatch):
    service = WorkspaceJobService()
    first = tmp_path / "first.webm"
    second = tmp_path / "second.webm"
    first.write_bytes(b"video")
    second.write_bytes(b"video")

    monkeypatch.setattr(job_module.settings, "MAX_CONCURRENT_WORKSPACE_JOBS", 1)
    monkeypatch.setattr(service, "_probe_duration_seconds", lambda _path: None)

    await service.create_job(
        str(first),
        "first.webm",
        "转录这个视频",
        start_immediately=False,
    )

    with pytest.raises(WorkspaceConcurrencyLimitError) as exc_info:
        await service.create_job(
            str(second),
            "second.webm",
            "转录这个视频",
            start_immediately=False,
        )

    assert exc_info.value.status_code == 429
    assert exc_info.value.active_jobs == 1


@pytest.mark.asyncio
async def test_workspace_processing_slot_counts_against_job_limit(tmp_path, monkeypatch):
    service = WorkspaceJobService()
    video = tmp_path / "sample.webm"
    video.write_bytes(b"video")

    monkeypatch.setattr(job_module.settings, "MAX_CONCURRENT_WORKSPACE_JOBS", 1)
    monkeypatch.setattr(service, "_probe_duration_seconds", lambda _path: None)

    reservation_id = await service.reserve_processing_slot()
    try:
        with pytest.raises(WorkspaceConcurrencyLimitError):
            await service.create_job(
                str(video),
                "sample.webm",
                "转录这个视频",
                start_immediately=False,
            )
    finally:
        await service.release_processing_slot(reservation_id)

    assert service.get_active_job_count() == 0


@pytest.mark.asyncio
async def test_workspace_retry_respects_concurrency_limit(tmp_path, monkeypatch):
    service = WorkspaceJobService()
    video = tmp_path / "retry.webm"
    video.write_bytes(b"video")

    async def fake_process(**_kwargs):
        raise RuntimeError("SSLError unexpected_eof while submitting transcription")

    monkeypatch.setattr(job_module.settings, "MAX_CONCURRENT_WORKSPACE_JOBS", 1)
    monkeypatch.setattr(job_module.workspace_service, "process_video_query", fake_process)
    monkeypatch.setattr(service, "_probe_duration_seconds", lambda _path: None)

    job = await service.create_job(
        str(video),
        "retry.webm",
        "转录这个视频",
        start_immediately=False,
    )
    await service.run_job(job.job_id)
    assert service.get_job(job.job_id).retryable is True

    reservation_id = await service.reserve_processing_slot()
    try:
        with pytest.raises(WorkspaceConcurrencyLimitError):
            await service.retry_job(job.job_id)
    finally:
        await service.release_processing_slot(reservation_id)

    assert service.get_job(job.job_id).status == "failed"


@pytest.mark.asyncio
async def test_workspace_job_success_records_local_quota_usage(tmp_path, monkeypatch):
    service = WorkspaceJobService()
    video = tmp_path / "sample.webm"
    video.write_bytes(b"video")
    calls = []

    async def fake_process(**kwargs):
        return _response(kwargs["query"])

    async def fake_increment(user_id):
        calls.append(("increment", user_id))

    async def fake_storage(user_id, storage_mb):
        calls.append(("storage", user_id, storage_mb))

    monkeypatch.setattr(job_module.workspace_service, "process_video_query", fake_process)
    monkeypatch.setattr(job_module.database_service, "increment_video_usage", fake_increment)
    monkeypatch.setattr(job_module.database_service, "update_storage_usage", fake_storage)

    job = await service.create_job(
        str(video),
        "sample.webm",
        "生成摘要",
        user_id="user-1",
        start_immediately=False,
    )
    await service.run_job(job.job_id)

    assert ("increment", "user-1") in calls
    assert ("storage", "user-1", 1) in calls
