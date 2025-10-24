"""
Video analysis API routes.
"""
from fastapi import APIRouter, HTTPException, UploadFile, File, Body
from typing import List, Dict, Any, Optional
import logging
from dataclasses import asdict

from ...services.pipeline_service import pipeline
from ...services.chat_service import video_chat_service
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


# ==================== Chat with Video API ====================

@router.post("/chat/start")
async def chat_start(payload: Dict[str, Any] = Body(...)):
    """
    启动视频聊天会话
    
    请求体:
        {
            "video_id": "视频ID",
            "metadata": {
                "transcript": {...},  # 转录元数据
                "keyframes": [...]   # 关键帧列表
            }
        }
    
    返回:
        {
            "status": "success",
            "session_id": "会话ID",
            "video_id": "视频ID",
            "keyframes_count": 10,
            "transcript_segments_count": 50
        }
    """
    try:
        video_id = payload.get("video_id")
        metadata = payload.get("metadata")
        
        if not video_id:
            raise HTTPException(status_code=400, detail="缺少 video_id")
        if not metadata:
            raise HTTPException(status_code=400, detail="缺少 metadata")
        
        result = video_chat_service.start_session(video_id, metadata)
        
        if result.get("status") == "success":
            return result
        else:
            raise HTTPException(
                status_code=500,
                detail=result.get("error", "会话创建失败")
            )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"启动聊天会话失败: {e}")
        raise HTTPException(status_code=500, detail=f"启动聊天会话失败: {str(e)}")


@router.post("/chat/message")
async def chat_message(
    session_id: str = Body(..., embed=True),
    question: str = Body(..., embed=True),
    keyframe_ids: Optional[List[int]] = Body(None, embed=True),
    top_k: int = Body(5, embed=True),
    auto_keyframes: bool = Body(True, embed=True)
):
    """
    在聊天会话中提问
    
    参数:
        session_id: 会话 ID
        question: 用户问题
        keyframe_ids: 可选，指定的关键帧 ID 列表（用于视觉问答）
        top_k: 检索的相关转录片段数量，默认 5
        auto_keyframes: 是否自动查找相关关键帧，默认 True
    
    返回:
        {
            "status": "success",
            "session_id": "会话ID",
            "answer": "AI 回答",
            "references": {
                "time_ranges": [{"start_time": 10.5, "end_time": 20.3, "text": "..."}],
                "keyframe_ids": [1, 3, 5],
                "keyframes": [{"frame_id": 1, "timestamp": 12.5, "oss_image_url": "..."}]
            },
            "history_length": 4
        }
    """
    try:
        result = await video_chat_service.ask_question(
            session_id=session_id,
            question=question,
            keyframe_ids=keyframe_ids,
            top_k=top_k,
            auto_keyframes=auto_keyframes
        )
        
        if result.get("status") == "success":
            return result
        else:
            raise HTTPException(
                status_code=500,
                detail=result.get("error", "提问失败")
            )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"聊天提问失败: {e}")
        raise HTTPException(status_code=500, detail=f"聊天提问失败: {str(e)}")


@router.get("/chat/session/{session_id}")
async def chat_session_info(session_id: str):
    """
    获取聊天会话信息
    
    返回:
        {
            "status": "success",
            "session_id": "会话ID",
            "video_id": "视频ID",
            "created_at": "2025-10-22T10:30:00",
            "history_length": 10,
            "recent_messages": [...],
            "keyframes_count": 8,
            "transcript_segments_count": 45
        }
    """
    try:
        result = video_chat_service.get_session_info(session_id)
        
        if result.get("status") == "success":
            return result
        else:
            raise HTTPException(
                status_code=404,
                detail=result.get("error", "会话不存在")
            )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"获取会话信息失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取会话信息失败: {str(e)}")


@router.delete("/chat/session/{session_id}")
async def chat_session_end(session_id: str):
    """
    结束并清理聊天会话
    
    返回:
        {
            "status": "success",
            "session_id": "会话ID",
            "message": "会话已结束"
        }
    """
    try:
        success = video_chat_service.end_session(session_id)
        
        if success:
            return {
                "status": "success",
                "session_id": session_id,
                "message": "会话已结束"
            }
        else:
            raise HTTPException(
                status_code=404,
                detail="会话不存在或已结束"
            )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"结束会话失败: {e}")
        raise HTTPException(status_code=500, detail=f"结束会话失败: {str(e)}")


@router.get("/chat/sessions")
async def chat_sessions_list():
    """
    列出所有活动的聊天会话
    
    返回:
        {
            "status": "success",
            "sessions": [
                {
                    "session_id": "...",
                    "video_id": "...",
                    "created_at": "...",
                    "history_length": 10
                }
            ],
            "total": 3
        }
    """
    try:
        result = video_chat_service.list_sessions()
        return result
    except Exception as e:
        logger.exception(f"列出会话失败: {e}")
        raise HTTPException(status_code=500, detail=f"列出会话失败: {str(e)}")