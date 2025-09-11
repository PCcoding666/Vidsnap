"""
Video analysis API routes.
"""
from fastapi import APIRouter, HTTPException
from typing import List, Dict, Any
import logging

from ...services.pipeline_service import pipeline
from ...core.logging import logger

router = APIRouter(prefix="/analysis", tags=["analysis"])


@router.get("/metadata/{video_id}")
async def get_video_metadata(video_id: str):
    """
    Get video metadata by video ID.
    
    Args:
        video_id: Video identifier
        
    Returns:
        Video metadata
    """
    try:
        metadata = await pipeline.get_video_metadata(video_id)
        if metadata:
            return {
                "status": "success",
                "metadata": metadata
            }
        else:
            raise HTTPException(status_code=404, detail="未找到视频metadata")
    except Exception as e:
        logger.exception(f"获取视频metadata失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取视频metadata失败: {str(e)}")


@router.get("/search/{video_id}")
async def search_in_transcript(video_id: str, keyword: str):
    """
    Search for keywords in video transcript.
    
    Args:
        video_id: Video identifier
        keyword: Search keyword
        
    Returns:
        Search results
    """
    try:
        results = await pipeline.search_in_transcript(video_id, keyword)
        return {
            "status": "success",
            "keyword": keyword,
            "results": results,
            "count": len(results)
        }
    except Exception as e:
        logger.exception(f"转录搜索失败: {e}")
        raise HTTPException(status_code=500, detail=f"转录搜索失败: {str(e)}")