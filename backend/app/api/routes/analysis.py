"""
Video analysis API routes.
"""
from fastapi import APIRouter, HTTPException, UploadFile, File
from typing import List, Dict, Any, Optional
import logging
from dataclasses import asdict

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


@router.post("/summarize")
async def summarize_video(
    youtube_url: Optional[str] = None,
    video_file: Optional[UploadFile] = File(None),
    granularity: str = "standard",
    language: str = "auto"
):
    """
    Complete video analysis with LLM summarization.
    
    Args:
        youtube_url: YouTube video URL (optional)
        video_file: Uploaded video file (optional)
        granularity: Summary granularity ("brief", "standard", "detailed")
        language: Language for transcription (default: "auto")
        
    Returns:
        Complete analysis results including video summary
    """
    try:
        # 验证输入
        if not youtube_url and not video_file:
            raise HTTPException(
                status_code=400, 
                detail="必须提供 youtube_url 或 video_file 之一"
            )
        
        # 验证粒度参数
        if granularity not in ["brief", "standard", "detailed"]:
            raise HTTPException(
                status_code=400,
                detail="granularity 必须是 'brief', 'standard' 或 'detailed'"
            )
        
        # 处理上传的视频文件
        video_file_path = None
        if video_file:
            import tempfile
            import os
            
            # 保存上传的文件
            temp_dir = tempfile.mkdtemp()
            video_file_path = os.path.join(temp_dir, video_file.filename)
            
            with open(video_file_path, "wb") as f:
                content = await video_file.read()
                f.write(content)
            
            logger.info(f"上传的视频文件已保存: {video_file_path}")
        
        # 调用完整的处理管道
        logger.info(f"开始处理视频，粒度: {granularity}")
        
        result = await pipeline.process_video_with_summary(
            video_file=video_file_path,
            youtube_url=youtube_url,
            granularity=granularity
        )
        
        if result["status"] == "success":
            # 构建返回结果
            response = {
                "status": "success",
                "video_id": result["video_id"],
                "keyframes_count": result["keyframes_count"],
                "transcript_segments_count": result["transcript_segments_count"],
                "summary_generated": result.get("summary_generated", False)
            }
            
            # 添加视频总结
            if result.get("video_summary"):
                response["video_summary"] = asdict(result["video_summary"])
            
            # 添加 metadata
            if result.get("metadata"):
                response["metadata"] = asdict(result["metadata"])
            
            return response
        else:
            raise HTTPException(
                status_code=500,
                detail=result.get("error", "视频处理失败")
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"视频总结失败: {e}")
        raise HTTPException(
            status_code=500, 
            detail=f"视频总结失败: {str(e)}"
        )


@router.get("/services/status")
async def get_services_status():
    """
    Get the status of all services.
    
    Returns:
        Service availability status
    """
    try:
        services = pipeline.check_services_availability()
        return {
            "status": "success",
            "services": services,
            "all_available": all(services.values())
        }
    except Exception as e:
        logger.exception(f"获取服务状态失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取服务状态失败: {str(e)}")