"""
Video processing API routes.
"""
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from typing import Optional
import logging

from ...services.pipeline_service import pipeline
from ...core.logging import logger

router = APIRouter(prefix="/video", tags=["video"])


@router.post("/process")
async def process_video(
    youtube_url: Optional[str] = Form(None),
    video_file: Optional[UploadFile] = File(None)
):
    """
    Process a video from either YouTube URL or uploaded file.
    
    Args:
        youtube_url: YouTube video URL
        video_file: Uploaded video file
        
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
            import tempfile
            import os
            temp_dir = tempfile.gettempdir()
            video_path = os.path.join(temp_dir, video_file.filename)
            
            # 保存文件
            with open(video_path, "wb") as buffer:
                content = await video_file.read()
                buffer.write(content)
            
            logger.info(f"已保存上传的视频文件: {video_path}")
        
        # 处理视频
        result = await pipeline.process_video(
            youtube_url=youtube_url,
            video_file=video_path
        )
        
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