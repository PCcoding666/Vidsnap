import io

import pytest
from fastapi import HTTPException, UploadFile
from fastapi.security import HTTPAuthorizationCredentials

from app.api import upload_guards
from app.api.routes import video as video_routes


def _credentials() -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials="token")


@pytest.mark.asyncio
async def test_workspace_resolve_user_context_uses_local_database_quota(monkeypatch):
    async def fake_verify(_token):
        return {"id": "user-1", "email": "user@example.com"}

    async def fake_check(user_id):
        assert user_id == "user-1"
        return True

    async def fake_quota(user_id):
        assert user_id == "user-1"
        return {"max_video_duration_seconds": 600}

    monkeypatch.setattr(upload_guards.database_service, "verify_token", fake_verify)
    monkeypatch.setattr(upload_guards.database_service, "check_user_quota", fake_check)
    monkeypatch.setattr(upload_guards.database_service, "get_user_quota", fake_quota)

    user_id, quota = await upload_guards.resolve_user_context(_credentials())

    assert user_id == "user-1"
    assert quota["max_video_duration_seconds"] == 600


@pytest.mark.asyncio
async def test_workspace_resolve_user_context_rejects_exhausted_quota(monkeypatch):
    async def fake_verify(_token):
        return {"id": "user-1"}

    async def fake_check(_user_id):
        return False

    monkeypatch.setattr(upload_guards.database_service, "verify_token", fake_verify)
    monkeypatch.setattr(upload_guards.database_service, "check_user_quota", fake_check)

    with pytest.raises(HTTPException) as exc_info:
        await upload_guards.resolve_user_context(_credentials())

    assert exc_info.value.status_code == 429
    assert "上限" in exc_info.value.detail


@pytest.mark.asyncio
async def test_workspace_save_upload_rejects_stream_over_limit(tmp_path, monkeypatch):
    upload = UploadFile(file=io.BytesIO(b"12345"), filename="sample.webm")
    target = tmp_path / "sample.webm"

    monkeypatch.setattr(upload_guards.settings, "MAX_UPLOAD_BYTES", 4)

    with pytest.raises(HTTPException) as exc_info:
        await upload_guards.save_upload_with_size_limit(upload, str(target))

    assert exc_info.value.status_code == 413
    assert "上传文件过大" in exc_info.value.detail


@pytest.mark.asyncio
async def test_workspace_duration_limit_uses_user_quota(tmp_path, monkeypatch):
    video = tmp_path / "sample.webm"
    video.write_bytes(b"video")

    async def fake_probe(_path):
        return 601.0

    monkeypatch.setattr(upload_guards.settings, "MAX_MEDIA_DURATION_SECONDS", 3600)
    monkeypatch.setattr(upload_guards.workspace_job_service, "probe_duration_seconds", fake_probe)

    with pytest.raises(HTTPException) as exc_info:
        await upload_guards.enforce_media_duration_limit(
            str(video),
            {"max_video_duration_seconds": 600},
        )

    assert exc_info.value.status_code == 422
    assert "超过限制 600s" in exc_info.value.detail


@pytest.mark.asyncio
async def test_video_history_uses_local_database(monkeypatch):
    async def fake_verify(_token):
        return {"id": "user-1"}

    async def fake_videos(user_id, limit):
        assert user_id == "user-1"
        assert limit == 20
        return [
            {
                "video_id": "video-1",
                "title": "Local History",
                "duration": 12.5,
                "created_at": "2026-01-01T00:00:00",
                "processing_status": "completed",
                "source_type": "upload",
            }
        ]

    # resolve_user_context 走 upload_guards.database_service；直接的 get_user_videos 走 video_routes.database_service。
    monkeypatch.setattr(upload_guards.database_service, "verify_token", fake_verify)
    monkeypatch.setattr(upload_guards.database_service, "check_user_quota", lambda _uid: True)
    monkeypatch.setattr(video_routes.database_service, "get_user_videos", fake_videos)

    response = await video_routes.get_video_history(credentials=_credentials())

    assert response["status"] == "success"
    assert response["total"] == 1
    assert response["videos"][0]["id"] == "video-1"
