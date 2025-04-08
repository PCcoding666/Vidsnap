import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
import os
import aiohttp

from app.models.summary import SummaryInDB
from app.models.user import UserInDB
from app.services.summary.video_service import video_downloader, create_summary, update_summary, get_summary_by_id
from app.services.summary.whisper_service import whisper_service
from app.services.summary.qwen_service_part2 import qwen_service
from app.services.auth.user_service import check_user_quota, update_user_usage

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def process_video_summary(
    self,
    video_url: str,
    language: str = "zh",
    granularity: str = "medium",
    format_markdown: bool = True
) -> Dict[str, Any]:
    """处理视频摘要请求"""
    try:
        # 检查千问服务可用性并获取详细状态
        service_status = await self._check_qwen_service()
        if not service_status["available"]:
            logger.error(f"千问API服务不可用: {service_status['error']}")
            return {
                "status": "error",
                "error": f"千问API服务不可用: {service_status['error']}",
                "summary": None,
                "keyframes": []
            }

        # 其他处理逻辑保持不变...
        
    except Exception as e:
        logger.error(f"处理视频摘要时出错: {str(e)}")
        return {
            "status": "error",
            "error": str(e),
            "summary": None,
            "keyframes": []
        }

async def _check_qwen_service(self) -> Dict[str, Any]:
    """检查千问服务可用性并返回详细状态"""
    try:
        # 创建测试消息（OpenAI兼容格式）
        test_payload = {
            "model": "qwen-max",
            "messages": [
                {
                    "role": "user",
                    "content": "测试消息"
                }
            ],
            "max_tokens": 10
        }
        
        # 获取API配置
        api_key = os.getenv("QWEN_API_KEY")
        api_base = os.getenv(
            "QWEN_API_BASE", 
            "https://dashscope-intl.aliyuncs.com/compatible-mode/v1/chat/completions"
        )
        
        if not api_key:
            return {
                "available": False,
                "error": "未设置QWEN_API_KEY环境变量"
            }
            
        # 发送测试请求
        async with aiohttp.ClientSession() as session:
            async with session.post(
                api_base,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                },
                json=test_payload,
                ssl=False  # 禁用SSL验证以处理证书问题
            ) as response:
                if response.status == 200:
                    return {
                        "available": True,
                        "error": None
                    }
                else:
                    error_text = await response.text()
                    return {
                        "available": False,
                        "error": f"API测试失败: HTTP {response.status} - {error_text}"
                    }
                    
    except aiohttp.ClientError as e:
        return {
            "available": False,
            "error": f"API连接错误: {str(e)}"
        }
    except Exception as e:
        return {
            "available": False,
            "error": f"服务检查时出错: {str(e)}"
        }

async def process_video_summary(summary_id: str) -> SummaryInDB:
    """
    处理视频摘要请求
    
    Args:
        summary_id: 摘要ID
        
    Returns:
        SummaryInDB: 更新后的摘要对象
    """
    # 获取摘要信息
    summary = get_summary_by_id(summary_id)
    if not summary:
        raise ValueError(f"未找到ID为{summary_id}的摘要")
    
    try:
        # 更新摘要状态为处理中
        update_summary(summary_id, {"status": "processing"})
        
        # 提取视频ID
        video_id = summary.video_id
        
        # 下载视频
        logger.info(f"开始下载视频: {video_id}")
        download_result = video_downloader.download_video(
            video_id=video_id,
            resolution="720p",
            extract_audio=True  # 默认启用音频
        )
        
        video_url = download_result.get("video_url")
        audio_url = download_result.get("audio_url")
        video_metadata = download_result.get("metadata", {})
        
        if not video_url:
            raise ValueError("视频下载失败")
        
        # 更新视频信息
        update_data = {
            "video_title": video_metadata.get("title", ""),
            "video_thumbnail": video_metadata.get("thumbnail", ""),
            "video_duration": video_metadata.get("duration", 0),
            "metadata": video_metadata
        }
        
        # 处理音频转录
        audio_transcript = None
        transcription_result = None
        
        if audio_url and whisper_service.is_available():
            logger.info(f"开始转录音频")
            # 使用普通转录
            transcription_result = whisper_service.transcribe_audio(
                audio_url,
                language="zh"  # 默认使用中文
            )
            audio_transcript = transcription_result.get("text", "")
            logger.info(f"音频转录完成 (普通转录)")
            
            # 更新音频转录信息
            update_data["audio_transcript"] = audio_transcript
        
        # 调用千问API生成摘要
        if qwen_service.is_available():
            logger.info(f"开始生成摘要")
            
            summary_result = qwen_service.generate_summary_from_video(
                video_url=video_url,
                audio_url=None,  # 不再使用音频URL，因为我们已经有了转录结果
                granularity="medium",  # 默认使用中等粒度
                format_markdown=True,  # 始终使用Markdown格式
                video_metadata=video_metadata,
                audio_transcript=audio_transcript,
                transcription_result=transcription_result,
                keyframe_method="interval",  # 默认使用间隔采样
                num_frames=10,  # 默认10帧
                interval_seconds=30,  # 默认30秒间隔
                language="zh"  # 默认使用中文
            )
            
            if "error" not in summary_result and summary_result.get("status") == "success":
                # 正确从 Qwen API 的响应结构中提取摘要内容
                qwen_response_data = summary_result.get("summary", {})
                summary_text = ""
                if qwen_response_data.get("choices") and qwen_response_data["choices"][0].get("message"):
                    summary_text = qwen_response_data["choices"][0]["message"].get("content", "")
                
                if not summary_text:
                    logger.warning("从Qwen服务获取的摘要内容为空")
                    # 可以选择抛出错误或设置一个默认值
                    # raise ValueError("从Qwen服务获取的摘要内容为空") 
                    summary_text = "摘要生成成功，但内容为空。" # 或者保留为空
                
                # 更新摘要文本和关键帧
                update_data["summary_text"] = summary_text
                # 注意：keyframes 的提取逻辑也需要确认 qwen_service 是否正确返回了 gcs_image_urls
                # 假设 qwen_service 在返回的 summary_result 中添加了 keyframes 列表
                update_data["keyframes"] = summary_result.get("keyframes", []) # 如果 qwen_service 没加，需要修改 qwen_service
                update_data["status"] = "completed"
                update_data["updated_at"] = datetime.utcnow()
                logger.info(f"摘要生成完成")
            elif "error" in summary_result:
                 error_detail = summary_result.get("error", "未知错误")
                 logger.error(f"Qwen服务返回错误: {error_detail}")
                 raise ValueError(f"摘要生成失败: {error_detail}")
            else:
                # 处理 status 不是 success 但也没有 error 的情况
                logger.error(f"Qwen服务返回了意外的状态: {summary_result.get('status')}")
                raise ValueError(f"摘要生成失败: Qwen服务返回了意外的状态 {summary_result.get('status')}")
        else:
            raise ValueError("千问API服务不可用")
        
        # 更新摘要
        updated_summary = update_summary(summary_id, update_data)
        return updated_summary
        
    except Exception as e:
        # 更新摘要状态为失败
        error_message = str(e)
        logger.error(f"处理视频摘要失败: {error_message}")
        update_summary(summary_id, {
            "status": "failed",
            "error_message": error_message,
            "updated_at": datetime.utcnow()
        })
        raise 