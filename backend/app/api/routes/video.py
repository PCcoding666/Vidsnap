"""
Video processing API routes.
"""
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional, Dict, Any
import logging
import tempfile
import os

from ...services.pipeline_service import pipeline
from ...services.supabase_service import supabase_service
from ...core.logging import logger

router = APIRouter(prefix="/video", tags=["video"])
security = HTTPBearer(auto_error=False)  # auto_error=False 允许无token访问


@router.post("/process")
async def process_video(
    youtube_url: Optional[str] = Form(None),
    video_file: Optional[UploadFile] = File(None),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
):
    """
    Process a video from either YouTube URL or uploaded file.
    
    认证: 可选（如果提供token则验证，否则使用匿名模式）
    
    Args:
        youtube_url: YouTube video URL
        video_file: Uploaded video file
        credentials: 可选的认证凭证
        
    Returns:
        Processing result
    """
    logger.info("收到视频处理请求")
    
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
                        detail="已达到本月视频处理上限或存储空间已满，请升级订阅或等待下月重置"
                    )
                logger.info(f"✅ 用户认证成功: {user.get('email')}")
        except HTTPException:
            raise
        except Exception as e:
            logger.warning(f"⚠️ Token验证失败，使用匿名模式: {e}")
    else:
        logger.info("👤 使用匿名模式处理视频")
    
    # 验证输入
    if not youtube_url and not video_file:
        raise HTTPException(status_code=400, detail="必须提供YouTube URL或上传视频文件")
    
    if youtube_url and video_file:
        raise HTTPException(status_code=400, detail="不能同时提供YouTube URL和上传视频文件")
    
    try:
        # 保存上传的文件（如果有的话）
        video_path = None
        if video_file:
            # 生成临时文件路径
            temp_dir = tempfile.gettempdir()
            video_path = os.path.join(temp_dir, video_file.filename)
            
            logger.info(f"📤 开始保存上传的视频文件: {video_file.filename}, 大小: {video_file.size if hasattr(video_file, 'size') else 'unknown'}")
            
            # 保存文件
            with open(video_path, "wb") as buffer:
                content = await video_file.read()
                buffer.write(content)
            
            logger.info(f"✅ 已保存上传的视频文件: {video_path}, 文件大小: {os.path.getsize(video_path)} bytes")
        
        # 获取用户 ID
        # user_id 已在上面处理过
        
        # 处理视频(传递 user_id 用于 Supabase 集成)
        logger.info(f"🚀 开始处理视频管道: youtube_url={youtube_url}, video_file={video_path}, user_id={user_id}")
        result = await pipeline.process_video_with_summary(
            youtube_url=youtube_url,
            video_file=video_path,
            user_id=user_id
        )
        logger.info(f"📊 视频处理管道返回结果: status={result.get('status')}, video_id={result.get('video_id')}")
        
        # 如果处理成功,递增配额使用
        if result.get("status") == "success" and supabase_service.is_available() and user_id:
            try:
                supabase_service.increment_video_usage(user_id)
            except Exception as e:
                logger.error(f"⚠️ 递增配额使用失败: {e}")
        
        # 清理临时文件
        if video_path and os.path.exists(video_path):
            try:
                os.remove(video_path)
                logger.debug(f"已清理临时文件: {video_path}")
            except Exception as e:
                logger.warning(f"清理临时文件失败: {e}")
        
        return result
        
    except Exception as e:
        error_message = str(e)
        logger.exception(f"❌ 视频处理失败: {e}")
        logger.error(f"❌ 错误类型: {type(e).__name__}")
        logger.error(f"❌ 错误详情: {error_message}")
        
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