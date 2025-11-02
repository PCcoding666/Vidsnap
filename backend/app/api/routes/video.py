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
            
            # 保存文件
            with open(video_path, "wb") as buffer:
                content = await video_file.read()
                buffer.write(content)
            
            logger.info(f"已保存上传的视频文件: {video_path}")
        
        # 获取用户 ID
        # user_id 已在上面处理过
        
        # 处理视频(传递 user_id 用于 Supabase 集成)
        result = await pipeline.process_video_with_summary(
            youtube_url=youtube_url,
            video_file=video_path,
            user_id=user_id
        )
        
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
        logger.exception(f"视频处理失败: {e}")
        raise HTTPException(status_code=500, detail=f"视频处理失败: {str(e)}")


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