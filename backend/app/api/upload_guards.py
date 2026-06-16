"""
上传与配额护栏的共享 helper。

workspace 与 video 两套路由都按同一规则做：本地 JWT 鉴权、配额检查、
流式大小限制、时长限制、存储配额和成功后的用量计费。集中到这里避免两份实现漂移。
"""
import math
import os
from typing import Any, Dict, Optional, Tuple

from fastapi import HTTPException, UploadFile, status
from fastapi.security import HTTPAuthorizationCredentials

from ..core.config import settings
from ..core.logging import get_context_logger, logger
from ..services.database_service import database_service
from ..services.workspace_job_service import workspace_job_service

ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v"}
UPLOAD_CHUNK_BYTES = 1024 * 1024


async def resolve_user_context(
    credentials: Optional[HTTPAuthorizationCredentials],
    enforce_quota: bool = True,
) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
    """校验本地 JWT，返回 (user_id, quota)。匿名或校验失败时返回 (None, None)。"""
    if not credentials:
        return None, None

    try:
        user = await database_service.verify_token(credentials.credentials)
        if not user:
            return None, None

        user_id = str(user.get("id") or "")
        if not user_id:
            return None, None

        if enforce_quota and not await database_service.check_user_quota(user_id):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="已达到本月视频处理上限或存储空间已满，请升级订阅或等待下月重置",
            )

        quota = await database_service.get_user_quota(user_id) if enforce_quota else None
        return user_id, quota
    except HTTPException:
        raise
    except Exception as e:
        get_context_logger().warning(f"⚠️ Token验证失败，使用匿名模式: {e}")
        return None, None


def max_upload_bytes() -> int:
    return max(int(getattr(settings, "MAX_UPLOAD_BYTES", 0) or 0), 0)


def format_bytes(value: int) -> str:
    return f"{value / (1024 * 1024):.1f} MB"


async def save_upload_with_size_limit(video_file: UploadFile, video_path: str) -> int:
    """流式写盘并在超过 MAX_UPLOAD_BYTES 时立即中止，返回写入字节数。"""
    max_bytes = max_upload_bytes()
    declared_size = getattr(video_file, "size", None) or 0
    if max_bytes > 0 and declared_size > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"上传文件过大，最大允许 {format_bytes(max_bytes)}",
        )

    total_bytes = 0
    with open(video_path, "wb") as buffer:
        while chunk := await video_file.read(UPLOAD_CHUNK_BYTES):
            total_bytes += len(chunk)
            if max_bytes > 0 and total_bytes > max_bytes:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=f"上传文件过大，最大允许 {format_bytes(max_bytes)}",
                )
            buffer.write(chunk)
    return total_bytes


def effective_max_duration_seconds(quota: Optional[Dict[str, Any]]) -> int:
    """取全局配置与用户配额时长上限中的更小值（0 表示不限制）。"""
    limits = []
    configured_limit = max(int(getattr(settings, "MAX_MEDIA_DURATION_SECONDS", 0) or 0), 0)
    if configured_limit > 0:
        limits.append(configured_limit)

    if quota:
        quota_limit = max(int(quota.get("max_video_duration_seconds") or 0), 0)
        if quota_limit > 0:
            limits.append(quota_limit)

    return min(limits) if limits else 0


async def enforce_media_duration_limit(
    video_path: str,
    quota: Optional[Dict[str, Any]],
) -> Optional[float]:
    max_duration_seconds = effective_max_duration_seconds(quota)
    if max_duration_seconds <= 0:
        return None

    duration_seconds = await workspace_job_service.probe_duration_seconds(video_path)
    if duration_seconds and duration_seconds > max_duration_seconds:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"视频时长 {duration_seconds:.1f}s 超过限制 {max_duration_seconds}s",
        )
    return duration_seconds


def enforce_storage_quota(quota: Optional[Dict[str, Any]], upload_bytes: int) -> None:
    if not quota:
        return

    total_storage_mb = int(quota.get("total_storage_mb") or 0)
    if total_storage_mb <= 0:
        return

    used_storage_mb = int(quota.get("used_storage_mb") or 0)
    upload_mb = math.ceil(upload_bytes / (1024 * 1024))
    if used_storage_mb + upload_mb > total_storage_mb:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"存储空间不足，当前剩余 {max(total_storage_mb - used_storage_mb, 0)} MB，"
                f"上传需要 {upload_mb} MB"
            ),
        )


async def record_user_usage(user_id: Optional[str], upload_bytes: int) -> None:
    if not user_id:
        return

    try:
        await database_service.increment_video_usage(user_id)
        upload_mb = math.ceil(upload_bytes / (1024 * 1024))
        if upload_mb > 0:
            await database_service.update_storage_usage(user_id, upload_mb)
    except Exception as e:
        logger.warning(f"更新用户配额失败: {e}")
