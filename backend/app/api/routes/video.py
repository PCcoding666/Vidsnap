"""
Video processing API routes.

Slim 模式仅支持本地视频文件上传。
"""
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional
import tempfile
import os
import time
from pathlib import Path

from ...services.pipeline_service import pipeline
from ...services.supabase_service import supabase_service
from ...core.logging import logger, get_context_logger

router = APIRouter(prefix="/video", tags=["video"])
security = HTTPBearer(auto_error=False)  # auto_error=False 允许无token访问


@router.post("/process")
async def process_video(
    request: Request,
    video_file: UploadFile = File(...),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
):
    """
    Process an uploaded local video file.
    
    认证: 可选（如果提供token则验证，否则使用匿名模式）
    
    Args:
        request: FastAPI Request对象
        video_file: Uploaded video file
        credentials: 可选的认证凭证
        
    Returns:
        Processing result
    """
    # 创建带请求ID的上下文日志记录器
    ctx_logger = get_context_logger()
    start_time = time.time()
    
    # 记录请求详情
    ctx_logger.info(
        "🎬 收到视频处理请求",
        client_host=request.client.host if request.client else "unknown",
        user_agent=request.headers.get("user-agent", "unknown"),
        file_name=video_file.filename if video_file else None,
    )
    
    # 记录初始资源使用情况
    ctx_logger.log_resource_usage("请求开始")
    
    # 处理认证（可选）
    user_id = None
    if credentials and supabase_service.is_available():
        try:
            user = supabase_service.verify_token(credentials.credentials)
            if user:
                user_id = user.get("id")
                # 检查配额
                quota_ok = supabase_service.check_user_quota(str(user_id))
                if not quota_ok:
                    ctx_logger.warning("❌ 用户配额已耗尽", user_id=user_id, user_email=user.get('email'))
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail="已达到本月视频处理上限或存储空间已满，请升级订阅或等待下月重置"
                    )
                ctx_logger.info("✅ 用户认证成功", user_id=user_id, user_email=user.get('email'))
        except HTTPException:
            raise
        except Exception as e:
            ctx_logger.warning(f"⚠️ Token验证失败，使用匿名模式: {e}")
    else:
        ctx_logger.info("👤 使用匿名模式处理视频")
    
    # 验证输入
    if not video_file or not video_file.filename:
        ctx_logger.error("❌ 请求验证失败: 未上传视频文件")
        raise HTTPException(status_code=400, detail="必须上传视频文件")

    allowed_extensions = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v"}
    file_suffix = Path(video_file.filename).suffix.lower()
    if file_suffix not in allowed_extensions:
        ctx_logger.error("❌ 请求验证失败: 不支持的视频格式", file_name=video_file.filename)
        raise HTTPException(
            status_code=400,
            detail=f"不支持的视频格式: {file_suffix or 'unknown'}，请上传 MP4、MOV、MKV、AVI、WEBM 或 M4V 文件"
        )
    
    video_path = None
    try:
        upload_start = time.time()
        file_size = getattr(video_file, "size", 0) or 0
        upload_dir = tempfile.mkdtemp(prefix="vidsnap_upload_")
        safe_filename = Path(video_file.filename).name
        video_path = os.path.join(upload_dir, safe_filename)

        ctx_logger.info(
            "📤 开始保存上传的视频文件",
            file_name=video_file.filename,
            file_size=file_size,
            temp_path=video_path,
            content_type=video_file.content_type
        )

        with open(video_path, "wb") as buffer:
            while chunk := await video_file.read(1024 * 1024):
                buffer.write(chunk)

        upload_duration = (time.time() - upload_start) * 1000
        actual_file_size = os.path.getsize(video_path)
        upload_seconds = max(upload_duration / 1000, 0.001)

        ctx_logger.log_file_operation(
            "文件上传完成",
            video_path,
            file_size=actual_file_size,
            upload_duration_ms=upload_duration,
            upload_speed_mbps=round(actual_file_size / 1024 / 1024 / upload_seconds, 2)
        )
        
        # 记录上传后资源使用
        ctx_logger.log_resource_usage("文件上传完成")
        
        # 获取用户 ID
        # user_id 已在上面处理过
        
        # 处理视频(传递 user_id 用于 Supabase 集成)
        pipeline_start = time.time()
        ctx_logger.info(
            "🚀 开始处理视频管道",
            video_file=video_path,
            user_id=user_id
        )
        
        result = await pipeline.process_video_with_summary(
            video_file=video_path,
            user_id=user_id
        )
        
        pipeline_duration = (time.time() - pipeline_start) * 1000
        ctx_logger.log_performance(
            "视频处理管道",
            status=result.get('status'),
            video_id=result.get('video_id'),
            duration_ms=pipeline_duration
        )
        
        # 记录管道处理后资源使用
        ctx_logger.log_resource_usage("管道处理完成")
        
        # 如果处理成功,递增配额使用
        if result.get("status") == "success" and supabase_service.is_available() and user_id:
            try:
                supabase_service.increment_video_usage(user_id)
                ctx_logger.info("✅ 配额使用已更新", user_id=user_id)
            except Exception as e:
                ctx_logger.error(f"⚠️ 递增配额使用失败: {e}", user_id=user_id)
        
        # 记录总体性能
        total_duration = (time.time() - start_time) * 1000
        ctx_logger.log_performance(
            "视频处理请求完成",
            total_duration_ms=total_duration,
            status=result.get('status'),
            video_id=result.get('video_id')
        )
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        error_message = str(e)
        ctx_logger.exception(
            f"❌ 视频处理失败",
            error_type=type(e).__name__,
            error_message=error_message,
            video_file=video_path,
            user_id=user_id
        )

        # 提供更详细的错误信息
        detailed_error = f"视频处理失败: {type(e).__name__} - {error_message}"
        raise HTTPException(status_code=500, detail=detailed_error)
    finally:
        if video_path and os.path.exists(video_path):
            try:
                os.remove(video_path)
                parent_dir = os.path.dirname(video_path)
                if parent_dir.startswith(tempfile.gettempdir()) and os.path.isdir(parent_dir):
                    os.rmdir(parent_dir)
                ctx_logger.debug("🗑️ 已清理临时文件", file_path=video_path)
            except Exception as e:
                ctx_logger.warning(f"⚠️ 清理临时文件失败: {e}", file_path=video_path)


@router.get("/history")
async def get_video_history(
    limit: int = 20,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
):
    """
    Get user's video processing history.
    
    认证: 可选（无认证时返回空列表）
    
    Args:
        limit: 返回记录数量限制
        credentials: 认证凭证
        
    Returns:
        视频历史列表
    """
    # 处理认证
    user_id = None
    if credentials and supabase_service.is_available():
        try:
            user = supabase_service.verify_token(credentials.credentials)
            if user:
                user_id = user.get("id")
        except Exception as e:
            logger.warning(f"⚠️ Token验证失败: {e}")
            # 不抛出异常，只是返回空列表
    
    if not user_id or not supabase_service.is_available():
        return {
            "status": "success",
            "videos": [],
            "message": "需要登录才能查看历史记录"
        }
    
    try:
        videos = supabase_service.get_user_videos(user_id, limit)
        
        # 转换数据格式为前端需要的格式
        formatted_videos = []
        for video in videos:
            formatted_videos.append({
                "id": video.get("video_id"),
                "title": video.get("title", "未命名视频"),
                "duration": video.get("duration"),
                "created_at": video.get("created_at"),
                "processing_status": video.get("processing_status"),
                "source_type": video.get("source_type"),
                "thumbnail_url": None  # TODO: 从keyframes表获取第一帧作为缩略图
            })
        
        return {
            "status": "success",
            "videos": formatted_videos,
            "total": len(formatted_videos)
        }
    except Exception as e:
        logger.exception(f"获取视频历史失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取视频历史失败: {str(e)}")


@router.get("/details/{video_id}")
async def get_video_details(
    video_id: str,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
):
    """
    Get detailed information for a specific video.
    
    认证: 可选（但只能访问自己的视频）
    
    Args:
        video_id: 视频ID
        credentials: 认证凭证
        
    Returns:
        视频详细信息
    """
    # 处理认证
    user_id = None
    if credentials and supabase_service.is_available():
        try:
            user = supabase_service.verify_token(credentials.credentials)
            if user:
                user_id = user.get("id")
        except Exception as e:
            logger.warning(f"⚠️ Token验证失败: {e}")
    
    if not supabase_service.is_available():
        raise HTTPException(
            status_code=503,
            detail="数据库服务不可用"
        )
    
    try:
        # 获取视频基本信息
        video = supabase_service.get_video_by_id(video_id)
        if not video:
            raise HTTPException(
                status_code=404,
                detail=f"视频不存在: {video_id}"
            )
        
        # 检查权限（如果有用户登录）
        if user_id and str(video.get("user_id")) != str(user_id):
            raise HTTPException(
                status_code=403,
                detail="无权访问该视频"
            )
        
        # 获取完整的元数据（包括关键帧、转录、总结）
        metadata = supabase_service.get_compiled_metadata(video_id)
        if not metadata:
            raise HTTPException(
                status_code=404,
                detail=f"视频元数据不存在: {video_id}"
            )
        
        # 获取总结信息
        summaries = supabase_service.get_video_summaries(video_id)
        
        return {
            "status": "success",
            "video_id": video_id,
            "metadata": metadata,
            "video_summary": summaries,
            "summary_generated": bool(summaries)
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"获取视频详情失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取视频详情失败: {str(e)}")


@router.get("/status")
async def get_service_status():
    """
    Get the status of all services.
    
    Returns:
        Service status information
    """
    try:
        status = pipeline.check_services_availability()
        return {
            "status": "success",
            "services": status
        }
    except Exception as e:
        logger.exception(f"获取服务状态失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取服务状态失败: {str(e)}")
