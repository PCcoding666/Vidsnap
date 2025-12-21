"""
Video processing API routes.

安全更新 (2025-12):
- YouTube视频下载已禁用，改为使用YouTube字幕API
- 新增 /youtube-info 端点检查字幕可用性
- 新增 /download-instructions 端点获取客户端下载指令
"""
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional, Dict, Any
import logging
import tempfile
import os
import time

from ...services.pipeline_service import pipeline
from ...services.supabase_service import supabase_service
from ...services.youtube_transcript_service import youtube_transcript_service
from ...core.logging import logger, get_context_logger

router = APIRouter(prefix="/video", tags=["video"])
security = HTTPBearer(auto_error=False)  # auto_error=False 允许无token访问


@router.post("/process")
async def process_video(
    request: Request,
    youtube_url: Optional[str] = Form(None),
    video_file: Optional[UploadFile] = File(None),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
):
    """
    Process a video from either YouTube URL or uploaded file.
    
    认证: 可选（如果提供token则验证，否则使用匿名模式）
    
    Args:
        request: FastAPI Request对象
        youtube_url: YouTube video URL
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
        youtube_url=youtube_url if youtube_url else None,
        has_file=video_file is not None,
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
    if not youtube_url and not video_file:
        ctx_logger.error("❌ 请求验证失败: 未提供视频源")
        raise HTTPException(status_code=400, detail="必须提供YouTube URL或上传视频文件")
    
    if youtube_url and video_file:
        ctx_logger.error("❌ 请求验证失败: 同时提供了YouTube URL和文件")
        raise HTTPException(status_code=400, detail="不能同时提供YouTube URL和上传视频文件")
    
    try:
        # 保存上传的文件（如果有的话）
        video_path = None
        if video_file:
            upload_start = time.time()
            
            # 获取文件大小
            file_size = 0
            if hasattr(video_file, 'size'):
                file_size = video_file.size
            
            # 生成临时文件路径
            temp_dir = tempfile.gettempdir()
            video_path = os.path.join(temp_dir, video_file.filename)
            
            ctx_logger.info(
                f"📤 开始保存上传的视频文件",
                file_name=video_file.filename,
                file_size=file_size,
                temp_path=video_path,
                content_type=video_file.content_type
            )
            
            # 保存文件
            bytes_written = 0
            with open(video_path, "wb") as buffer:
                content = await video_file.read()
                bytes_written = len(content)
                buffer.write(content)
            
            upload_duration = (time.time() - upload_start) * 1000
            actual_file_size = os.path.getsize(video_path)
            
            ctx_logger.log_file_operation(
                "文件上传完成",
                video_path,
                file_size=actual_file_size,
                upload_duration_ms=upload_duration,
                upload_speed_mbps=round(actual_file_size / 1024 / 1024 / (upload_duration / 1000), 2)
            )
            
            # 记录上传后资源使用
            ctx_logger.log_resource_usage("文件上传完成")
        
        # 获取用户 ID
        # user_id 已在上面处理过
        
        # 处理视频(传递 user_id 用于 Supabase 集成)
        pipeline_start = time.time()
        ctx_logger.info(
            "🚀 开始处理视频管道",
            youtube_url=youtube_url,
            video_file=video_path,
            user_id=user_id
        )
        
        result = await pipeline.process_video_with_summary(
            youtube_url=youtube_url,
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
        
        # 清理临时文件
        if video_path and os.path.exists(video_path):
            try:
                os.remove(video_path)
                ctx_logger.debug(f"🗑️ 已清理临时文件", file_path=video_path)
            except Exception as e:
                ctx_logger.warning(f"⚠️ 清理临时文件失败: {e}", file_path=video_path)
        
        # 记录总体性能
        total_duration = (time.time() - start_time) * 1000
        ctx_logger.log_performance(
            "视频处理请求完成",
            total_duration_ms=total_duration,
            status=result.get('status'),
            video_id=result.get('video_id')
        )
        
        return result
        
    except Exception as e:
        error_message = str(e)
        ctx_logger.exception(
            f"❌ 视频处理失败",
            error_type=type(e).__name__,
            error_message=error_message,
            youtube_url=youtube_url,
            video_file=video_path if video_file else None,
            user_id=user_id
        )
        
         # 检测是否是YouTube机器人检测错误
        if 'Sign in to confirm you\'re not a bot' in error_message or 'Please sign in' in error_message:
            friendly_message = (
                "YouTube 检测到非人类访问,无法下载视频。\n\n"
                "💡 解决方案：\n"
                "1. 使用文件上传功能直接上传视频文件\n"
                "2. 在本地下载 YouTube 视频后再上传\n"
                "3. 尝试使用其他视频链接"
            )
            raise HTTPException(status_code=503, detail=friendly_message)
        
        # 提供更详细的错误信息
        detailed_error = f"视频处理失败: {type(e).__name__} - {error_message}"
        raise HTTPException(status_code=500, detail=detailed_error)


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


@router.get("/youtube-info")
async def get_youtube_info(youtube_url: str):
    """
    获取YouTube视频信息和字幕可用性
    
    这是一个轻量级接口，不下载视频，仅检查字幕可用性
    
    Args:
        youtube_url: YouTube视频URL
        
    Returns:
        视频信息和字幕可用性
    """
    try:
        logger.info(f"检查YouTube视频字幕可用性: {youtube_url}")
        
        availability = await youtube_transcript_service.check_transcript_availability(youtube_url)
        
        return {
            "status": "success",
            "video_id": availability.get("video_id"),
            "has_transcript": availability.get("has_transcript", False),
            "available_languages": availability.get("available_languages", []),
            "has_manual_transcript": availability.get("has_manual_transcript", False),
            "has_auto_generated": availability.get("has_auto_generated", False),
            "error": availability.get("error"),
            "message": "有可用字幕，可以直接分析" if availability.get("has_transcript") else "该视频没有可用字幕，请使用客户端下载工具"
        }
        
    except Exception as e:
        logger.exception(f"检查YouTube视频信息失败: {e}")
        raise HTTPException(status_code=500, detail=f"检查视频信息失败: {str(e)}")


@router.get("/download-instructions")
async def get_download_instructions(youtube_url: str):
    """
    获取客户端下载指令
    
    当YouTube视频没有可用字幕时，返回给用户下载指令
    用户需要使用自己的IP下载视频，然后上传给我们处理
    
    Args:
        youtube_url: YouTube视频URL
        
    Returns:
        下载指令和建议
    """
    try:
        instructions = youtube_transcript_service.get_client_download_instructions(youtube_url)
        
        return {
            "status": "success",
            **instructions
        }
        
    except Exception as e:
        logger.exception(f"获取下载指令失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取下载指令失败: {str(e)}")


@router.post("/process-transcript")
async def process_youtube_transcript(
    request: Request,
    youtube_url: str = Form(...),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
):
    """
    仅使用YouTube字幕处理视频（推荐方式）
    
    这是处理YouTube视频的推荐方式，不下载视频文件，保护服务器IP
    
    Args:
        request: FastAPI Request对象
        youtube_url: YouTube视频URL
        credentials: 可选的认证凭证
        
    Returns:
        处理结果
    """
    ctx_logger = get_context_logger()
    start_time = time.time()
    
    ctx_logger.info(
        "🎬 收到YouTube字幕处理请求",
        youtube_url=youtube_url,
        client_host=request.client.host if request.client else "unknown"
    )
    
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
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail="已达到本月视频处理上限，请升级订阅或等待下月重置"
                    )
                ctx_logger.info("✅ 用户认证成功", user_id=user_id)
        except HTTPException:
            raise
        except Exception as e:
            ctx_logger.warning(f"⚠️ Token验证失败，使用匿名模式: {e}")
    
    try:
        # 使用字幕流程处理
        result = await pipeline.process_youtube_transcript_only(
            youtube_url=youtube_url,
            user_id=user_id
        )
        
        # 如果处理成功，递增配额使用
        if result.get("status") == "success" and supabase_service.is_available() and user_id:
            try:
                supabase_service.increment_video_usage(user_id)
            except Exception as e:
                ctx_logger.error(f"⚠️ 递增配额使用失败: {e}")
        
        total_duration = (time.time() - start_time) * 1000
        ctx_logger.info(
            f"YouTube字幕处理完成",
            status=result.get("status"),
            duration_ms=total_duration
        )
        
        return result
        
    except Exception as e:
        ctx_logger.exception(f"❌ YouTube字幕处理失败: {e}")
        raise HTTPException(status_code=500, detail=f"处理失败: {str(e)}")