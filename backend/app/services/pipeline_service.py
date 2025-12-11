"""
阿里云视频处理管道
协调视频处理、音频转录、关键帧提取和OSS存储的完整流程
支持并行处理和统一metadata格式
"""
import logging
import asyncio
import json
import time  # 新增：用于性能监控
from datetime import datetime
from typing import Dict, List, Any, Optional, Union
from dataclasses import asdict
from pathlib import Path

from ..core.logging import logger
from ..models.video import VideoInfo
from ..models.analysis import (
    KeyframeMetadata, 
    TranscriptSegment, 
    TranscriptMetadata, 
    VideoMetadata,
    VideoSummary
)
from .video_service import video_service
from .paraformer_service import paraformer_service  # 使用 Paraformer-v2 替代 SenseVoice
from .oss_service import oss_service
from .llm_service import llm_service
from .supabase_service import supabase_service


class AliyunVideoProcessingPipeline:
    """阿里云视频处理管道"""
    
    def __init__(self):
        """初始化处理管道"""
        self.video_service = video_service
        self.speech_service = paraformer_service  # 使用 Paraformer-v2
        self.oss_service = oss_service
        self.llm_service = llm_service
        
        logger.info("阿里云视频处理管道初始化完成（使用 Paraformer-v2 语音服务 + Qwen VL 视频总结服务）")
    
    async def process_video(self, 
                          video_file: Optional[str] = None,
                          youtube_url: Optional[str] = None,
                          progress_callback: Optional[callable] = None) -> Dict[str, Any]:
        """
        处理视频的完整流程（不包含 LLM 总结）
        
        Args:
            video_file: 上传的视频文件路径
            youtube_url: YouTube视频URL
            progress_callback: 进度回调函数（可选，主要用于日志记录）
            
        Returns:
            处理结果
        """
        self._log_progress("开始处理视频...", progress_callback)
        
        video_id = None
        
        try:
            # 步骤1: 视频下载/上传（不包含关键帧提取）
            self._log_progress("处理视频文件...", progress_callback)
            
            video_result = await self.video_service.process_video_dual_source(
                video_file=video_file,
                youtube_url=youtube_url
            )
            
            if video_result["status"] != "success":
                return video_result
            
            video_id = video_result["video_id"]
            video_info = video_result["video_info"]
            video_path = video_result["video_path"]
            video_metadata = video_result["video_metadata"]
            session_temp_dir = video_result["session_temp_dir"]
            
            # 步骤2: 并发执行关键帧提取和音频转录
            self._log_progress("并发执行关键帧提取和音频转录...", progress_callback)
            
            # 记录并发执行开始时间
            concurrent_start_time = time.time()
            
            try:
                # 使用 asyncio.gather() 并发执行两个任务
                logger.info(f"开始并发任务: 关键帧提取 + 音频转录 (video_id={video_id})")
                
                keyframes, transcript_result = await asyncio.gather(
                    self.video_service.extract_keyframes_scene_detection(
                        video_path, video_id, Path(session_temp_dir)
                    ),
                    self.speech_service.extract_and_transcribe_audio(
                        video_path, video_id, None
                    ),
                    return_exceptions=False  # 任何异常会立即抛出
                )
                
                # 计算并发执行总耗时
                concurrent_duration = time.time() - concurrent_start_time
                
                logger.info(
                    f"并发执行完成 - 总耗时: {concurrent_duration:.2f}s | "
                    f"关键帧数量: {len(keyframes) if keyframes else 0} | "
                    f"转录段落: {len(transcript_result.segments) if transcript_result and hasattr(transcript_result, 'segments') else 0}"
                )
                
            except Exception as e:
                error_msg = f"并发任务执行失败: {str(e)}"
                logger.error(error_msg)
                logger.exception(e)
                
                return {
                    "status": "error",
                    "error": error_msg,
                    "video_id": video_id
                }
            
            # 步骤3: 验证并发结果并降级处理
            if not keyframes:
                logger.warning("关键帧提取失败，使用空列表继续")
                keyframes = []
            
            if not transcript_result:
                logger.warning("音频转录失败，使用空转录对象继续")
                transcript_result = self._create_empty_transcript()
            
            # 步骤3: 生成统一metadata
            self._log_progress("生成metadata...", progress_callback)
            
            metadata = await self._generate_unified_metadata(
                video_info, keyframes, transcript_result, video_metadata
            )
            
            # 步骤4: 上传metadata到OSS
            self._log_progress("上传metadata到OSS...", progress_callback)
            
            metadata_oss_url = await self.oss_service.upload_metadata(
                asdict(metadata), video_id
            )
            
            if metadata_oss_url:
                metadata.metadata_oss_url = metadata_oss_url
            
            # 步骤5: 清理临时文件
            self._log_progress("清理临时文件...", progress_callback)
            
            self.video_service.cleanup_session(session_temp_dir)
            
            # 完成
            self._log_progress("处理完成！", progress_callback)
            
            logger.info(f"视频处理完成: {video_id}")
            
            return {
                "status": "success",
                "video_id": video_id,
                "metadata": metadata,
                "keyframes_count": len(keyframes),
                "transcript_segments_count": len(transcript_result.segments) if transcript_result.segments else 0
            }
            
        except Exception as e:
            error_msg = f"视频处理管道异常: {str(e)}"
            logger.exception(error_msg)
            
            self._log_progress(f"处理失败: {error_msg}", progress_callback)
            
            return {
                "status": "error",
                "error": error_msg,
                "video_id": video_id if 'video_id' in locals() else None
            }
    
    async def _generate_unified_metadata(self, video_info, keyframes, transcript_result, video_metadata) -> VideoMetadata:
        """生成统一的metadata格式"""
        try:
            # 转换关键帧数据
            keyframes_metadata = []
            for keyframe in keyframes:
                keyframe_meta = KeyframeMetadata(
                    frame_id=keyframe.frame_id,
                    timestamp=keyframe.timestamp,
                    oss_image_url=keyframe.oss_image_url or "",
                    scene_description=keyframe.scene_description
                )
                keyframes_metadata.append(keyframe_meta)
            
            # 转换转录数据
            if transcript_result and transcript_result.segments:
                transcript_segments = []
                for segment in transcript_result.segments:
                    segment_meta = TranscriptSegment(
                        text=segment.text,
                        start_time=segment.start_time,
                        end_time=segment.end_time,
                        confidence=segment.confidence
                    )
                    transcript_segments.append(segment_meta)
                
                transcript_metadata = TranscriptMetadata(
                    oss_audio_url=transcript_result.audio_oss_url,
                    language=transcript_result.language,
                    overall_confidence=transcript_result.confidence,
                    segments=transcript_segments
                )
            else:
                transcript_metadata = TranscriptMetadata(
                    oss_audio_url="",
                    language="zh-CN",
                    overall_confidence=0.0,
                    segments=[]
                )
            
            # 生成完整metadata
            metadata = VideoMetadata(
                video_id=video_info.video_id,
                title=video_info.title or "未知标题",
                duration=video_info.duration,
                oss_video_url=video_info.oss_video_url or "",
                source_type=video_info.source_type,
                original_url=video_info.original_url,
                upload_time=video_info.upload_time.isoformat() if video_info.upload_time else datetime.now().isoformat(),
                processing_completed_time=datetime.now().isoformat(),
                keyframes=keyframes_metadata,
                transcript=transcript_metadata,
                processing_status="completed",
                video_format=video_metadata.get("format_name", "unknown"),
                video_size=video_metadata.get("size", 0),
                video_resolution=f"{video_metadata.get('width', 0)}x{video_metadata.get('height', 0)}"
            )
            
            return metadata
            
        except Exception as e:
            logger.exception(f"生成metadata失败: {e}")
            raise
    
    def _create_empty_transcript(self):
        """创建空的转录结果"""
        class EmptyTranscript:
            def __init__(self):
                self.segments = []
                self.language = "zh-CN"
                self.confidence = 0.0
                self.audio_oss_url = ""
        
        return EmptyTranscript()
    
    async def get_video_metadata(self, video_id: str) -> Optional[VideoMetadata]:
        """
        获取视频的metadata
        
        Args:
            video_id: 视频ID
            
        Returns:
            视频metadata或None
        """
        try:
            # 这里应该从数据库或OSS获取metadata
            # 暂时返回None，后续可以扩展
            logger.info(f"获取视频metadata: {video_id}")
            return None
            
        except Exception as e:
            logger.exception(f"获取视频metadata失败: {e}")
            return None
    
    async def search_in_transcript(self, video_id: str, keyword: str) -> List[Dict[str, Any]]:
        """
        在转录文本中搜索关键词
        
        Args:
            video_id: 视频ID
            keyword: 搜索关键词
            
        Returns:
            搜索结果列表
        """
        try:
            # 获取视频metadata
            metadata = await self.get_video_metadata(video_id)
            
            if not metadata or not metadata.transcript.segments:
                return []
            
            results = []
            for i, segment in enumerate(metadata.transcript.segments):
                if keyword.lower() in segment.text.lower():
                    results.append({
                        "segment_index": i,
                        "text": segment.text,
                        "start_time": segment.start_time,
                        "end_time": segment.end_time,
                        "confidence": segment.confidence
                    })
            
            logger.info(f"在视频{video_id}中找到{len(results)}个关键词匹配")
            return results
            
        except Exception as e:
            logger.exception(f"转录搜索失败: {e}")
            return []
    
    def _log_progress(self, message: str, callback: Optional[callable] = None):
        """
        记录处理进度
        
        Args:
            message: 进度消息
            callback: 可选的回调函数（用于外部集成）
        """
        logger.info(f"[进度] {message}")
        if callback:
            try:
                callback(message)
            except Exception as e:
                logger.warning(f"进度回调执行失败: {e}")
    
    def check_services_availability(self) -> Dict[str, bool]:
        """检查所有服务的可用性"""
        return {
            "video_service": True,  # 视频服务总是可用
            "speech_service": self.speech_service.is_available(),
            "oss_service": self.oss_service.is_available(),
            "llm_service": self.llm_service.is_available()
        }
    
    async def process_video_with_summary(
        self,
        video_file: Optional[str] = None,
        youtube_url: Optional[str] = None,
        user_id: Optional[str] = None,
        progress_callback: Optional[callable] = None
    ) -> Dict[str, Any]:
        """
        处理视频的完整流程（包含 LLM 总结）
        
        Args:
            video_file: 上传的视频文件路径
            youtube_url: YouTube视频URL
            user_id: 用户 ID(用于 Supabase 数据持久化)
            progress_callback: 进度回调函数（可选，主要用于日志记录）
            
        Returns:
            处理结果（包含视频总结）
        """
        self._log_progress("开始处理视频...", progress_callback)
        
        video_id = None
        
        try:
            # 步骤1: 视频下载/上传（不包含关键帧提取）
            self._log_progress("处理视频文件...", progress_callback)
            
            video_result = await self.video_service.process_video_dual_source(
                video_file=video_file,
                youtube_url=youtube_url
            )
            
            if video_result["status"] != "success":
                return video_result
            
            video_id = video_result["video_id"]
            video_info = video_result["video_info"]
            video_path = video_result["video_path"]  # 新增：用于并发任务
            audio_path = video_result.get("audio_path")  # 分离的音频路径(如果有)
            audio_oss_url = video_result.get("audio_oss_url")  # 分离的音频OSS URL(如果有)
            video_metadata = video_result["video_metadata"]
            session_temp_dir = video_result["session_temp_dir"]
            
            # 【Supabase 集成点1】创建视频记录 (0% 初始化)
            if supabase_service.is_available() and user_id:
                try:
                    video_data = {
                        "video_id": video_id,
                        "user_id": user_id,
                        "title": video_info.title or "处理中...",
                        "duration": video_info.duration,
                        "source_type": "youtube" if youtube_url else "upload",
                        "original_url": youtube_url or "",
                        "oss_video_url": video_info.oss_video_url or "",
                        "processing_status": "processing",
                        "processing_progress": 0
                    }
                    supabase_service.create_video_record(video_data)
                    logger.info(f"✅ Supabase: 创建视频记录 {video_id}")
                except Exception as e:
                    logger.error(f"⚠️ Supabase: 创建视频记录失败: {e}")
            
            # 【Supabase 集成点2】更新视频状态 (15% 视频上传完成)
            if supabase_service.is_available() and user_id:
                try:
                    supabase_service.update_video_status(video_id, "processing", 15)
                    supabase_service.update_video_urls(video_id, oss_video_url=video_info.oss_video_url)
                except Exception as e:
                    logger.error(f"⚠️ Supabase: 更新视频状态失败: {e}")
            
            # 步骤2: 并发执行关键帧提取和音频转录
            self._log_progress("并发执行关键帧提取和音频转录...", progress_callback)
            
            # 【Supabase 集成点3】更新进度 (20% 准备并发执行)
            if supabase_service.is_available() and user_id:
                try:
                    supabase_service.update_video_status(video_id, "processing", 20)
                except Exception as e:
                    logger.error(f"⚠️ Supabase: 更新进度失败: {e}")
            
            # 记录并发执行开始时间
            concurrent_start_time = time.time()
            
            try:
                # 使用 asyncio.gather() 并发执行两个任务
                logger.info(f"开始并发任务: 关键帧提取 + 音频转录 (video_id={video_id})")
                
                keyframes, transcript_result = await asyncio.gather(
                    self.video_service.extract_keyframes_scene_detection(
                        video_path, video_id, Path(session_temp_dir)
                    ),
                    self.speech_service.extract_and_transcribe_audio(
                        audio_path if audio_path else video_path, video_id, audio_oss_url
                    ),
                    return_exceptions=False  # 任何异常会立即抛出
                )
                
                # 计算并发执行总耗时
                concurrent_duration = time.time() - concurrent_start_time
                
                logger.info(
                    f"并发执行完成 - 总耗时: {concurrent_duration:.2f}s | "
                    f"关键帧数量: {len(keyframes) if keyframes else 0} | "
                    f"转录段落: {len(transcript_result.segments) if transcript_result and hasattr(transcript_result, 'segments') else 0}"
                )
                
            except Exception as e:
                error_msg = f"并发任务执行失败: {str(e)}"
                logger.error(error_msg)
                logger.exception(e)
                
                # 【Supabase 集成点7】并发任务失败
                if supabase_service.is_available() and user_id and video_id:
                    try:
                        supabase_service.update_video_status(video_id, "failed", error_message=error_msg)
                        logger.info(f"⚠️ Supabase: 标记视频处理失败 {video_id}")
                    except Exception as se:
                        logger.error(f"⚠️ Supabase: 更新失败状态失败: {se}")
                
                return {
                    "status": "error",
                    "error": error_msg,
                    "video_id": video_id
                }
            
            # 步骤3: 验证并发结果并降级处理
            if not keyframes:
                logger.warning("关键帧提取失败，使用空列表继续")
                keyframes = []
            
            if not transcript_result:
                logger.warning("音频转录失败，使用空转录对象继续")
                transcript_result = self._create_empty_transcript()
            
            # 【Supabase 集成点4】并发任务完成 (60%)
            if supabase_service.is_available() and user_id:
                try:
                    supabase_service.update_video_status(video_id, "processing", 60)
                    
                    # 保存关键帧
                    if keyframes:
                        supabase_service.save_keyframes(video_id, keyframes)
                        logger.info(f"✅ Supabase: 保存 {len(keyframes)} 个关键帧")
                    
                    # 保存转录数据
                    if transcript_result and hasattr(transcript_result, 'segments') and transcript_result.segments:
                        supabase_service.save_transcript_segments(video_id, transcript_result.segments)
                        logger.info(f"✅ Supabase: 保存 {len(transcript_result.segments)} 个转录段落")
                except Exception as e:
                    logger.error(f"⚠️ Supabase: 保存并发结果失败: {e}")
            
            # 步骤3: 生成统一metadata
            self._log_progress("生成metadata...", progress_callback)
            
            metadata = await self._generate_unified_metadata(
                video_info, keyframes, transcript_result, video_metadata
            )
            
            # 步骤4: 生成 LLM 视频总结
            video_summary = None
            if self.llm_service.is_available():
                self._log_progress("生成视频 AI 总结...", progress_callback)
                
                try:
                    video_summary = await self.llm_service.generate_text_based_summary(
                        transcript=metadata.transcript,
                        video_metadata=video_metadata,
                        video_id=video_id
                    )
                    
                    if video_summary:
                        logger.info(f"LLM 视频总结生成成功: {len(video_summary.detailed_summary)} 字符")
                        
                        # 【Supabase 集成点5】LLM 总结完成 (80%)
                        if supabase_service.is_available() and user_id:
                            try:
                                supabase_service.update_video_status(video_id, "processing", 80)
                                # 保存三种粒度的总结
                                if hasattr(video_summary, 'brief_summary'):
                                    supabase_service.save_video_summary(video_id, "brief", video_summary.brief_summary)
                                if hasattr(video_summary, 'standard_summary'):
                                    supabase_service.save_video_summary(video_id, "standard", video_summary.standard_summary)
                                if hasattr(video_summary, 'detailed_summary') and video_summary.detailed_summary:
                                    supabase_service.save_video_summary(video_id, "detailed", video_summary.detailed_summary)
                                logger.info(f"✅ Supabase: 保存视频总结(三种粒度)")
                            except Exception as e:
                                logger.error(f"⚠️ Supabase: 保存视频总结失败: {e}")
                        
                        # 将总结上传到 OSS
                        summary_oss_url = await self.oss_service.upload_metadata(
                            asdict(video_summary), 
                            f"{video_id}_summary"
                        )
                        if summary_oss_url:
                            logger.info(f"视频总结已上传到 OSS: {summary_oss_url}")
                    else:
                        logger.warning("LLM 视频总结生成失败")
                        
                except Exception as e:
                    logger.exception(f"LLM 总结生成异常: {e}")
            else:
                logger.warning("LLM 服务不可用，跳过视频总结生成")
            
            # 步骤5: 上传metadata到OSS
            self._log_progress("上传metadata到OSS...", progress_callback)
            
            metadata_oss_url = await self.oss_service.upload_metadata(
                asdict(metadata), video_id
            )
            
            if metadata_oss_url:
                metadata.metadata_oss_url = metadata_oss_url
            
            # 步骤6: 清理临时文件
            self._log_progress("清理临时文件...", progress_callback)
            
            self.video_service.cleanup_session(session_temp_dir)
            
            # 完成
            self._log_progress("处理完成！", progress_callback)
            
            # 【Supabase 集成点6】处理完成 (100%)
            if supabase_service.is_available() and user_id:
                try:
                    supabase_service.update_video_status(video_id, "completed", 100)
                    logger.info(f"✅ Supabase: 视频处理完成 {video_id}")
                except Exception as e:
                    logger.error(f"⚠️ Supabase: 更新完成状态失败: {e}")
            
            logger.info(f"视频处理完成: {video_id}")
            
            return {
                "status": "success",
                "video_id": video_id,
                "metadata": metadata,
                "video_summary": video_summary,
                "keyframes_count": len(keyframes),
                "transcript_segments_count": len(transcript_result.segments) if transcript_result.segments else 0,
                "summary_generated": video_summary is not None
            }
            
        except Exception as e:
            error_msg = f"视频处理管道异常: {str(e)}"
            logger.exception(error_msg)
            
            # 【Supabase 集成点7】处理失败
            if supabase_service.is_available() and user_id and video_id:
                try:
                    supabase_service.update_video_status(video_id, "failed", error_message=error_msg)
                    logger.info(f"⚠️ Supabase: 标记视频处理失败 {video_id}")
                except Exception as se:
                    logger.error(f"⚠️ Supabase: 更新失败状态失败: {se}")
            
            self._log_progress(f"处理失败: {error_msg}", progress_callback)
            
            return {
                "status": "error",
                "error": error_msg,
                "video_id": video_id
            }


# 创建单例实例
pipeline = AliyunVideoProcessingPipeline()