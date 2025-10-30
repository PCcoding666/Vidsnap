"""
Video processing API routes.
"""
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends
from typing import Optional, Dict, Any
import logging
import tempfile
import os

from ...services.pipeline_service import pipeline
from ...services.supabase_service import supabase_service
from ...core.logging import logger
from ..dependencies import get_current_user, check_quota

router = APIRouter(prefix="/video", tags=["video"])


@router.post("/process")
async def process_video(
    youtube_url: Optional[str] = Form(None),
    video_file: Optional[UploadFile] = File(None),
    current_user: Dict[str, Any] = Depends(check_quota)  # 添加认证和配额检查
):
    """
    Process a video from either YouTube URL or uploaded file.
    
    需要认证: 是
    配额检查: 是
    
    Args:
        youtube_url: YouTube video URL
        video_file: Uploaded video file
        current_user: 当前用户信息(自动注入)
        
    Returns:
        Processing result
    """
    logger.info("收到视频处理请求")
    
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
        user_id = current_user.get("id")
        
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