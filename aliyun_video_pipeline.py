"""
阿里云视频处理管道
协调视频处理、音频转录、关键帧提取和OSS存储的完整流程
支持并行处理和统一metadata格式
"""
import logging
import asyncio
import json
from datetime import datetime
from typing import Dict, List, Any, Optional, Union
from dataclasses import dataclass, asdict
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class KeyframeMetadata:
    """关键帧元数据"""
    frame_id: int
    timestamp: float
    oss_image_url: str
    scene_description: str


@dataclass
class TranscriptSegmentMetadata:
    """转录段落元数据"""
    text: str
    start_time: float
    end_time: float
    confidence: float


@dataclass
class TranscriptMetadata:
    """音频转录元数据"""
    oss_audio_url: str
    language: str
    overall_confidence: float
    segments: List[TranscriptSegmentMetadata]


@dataclass
class VideoMetadata:
    """完整的视频元数据"""
    # 基本信息
    video_id: str
    title: str
    duration: float
    oss_video_url: str
    source_type: str  # "upload" 或 "youtube"
    original_url: Optional[str]
    
    # 处理时间
    upload_time: str
    processing_completed_time: str
    
    # 媒体内容
    keyframes: List[KeyframeMetadata]
    transcript: TranscriptMetadata
    
    # 处理状态
    processing_status: str
    metadata_oss_url: Optional[str] = None
    
    # 技术信息
    video_format: Optional[str] = None
    video_size: Optional[int] = None
    video_resolution: Optional[str] = None


class AliyunVideoProcessingPipeline:
    """阿里云视频处理管道"""
    
    def __init__(self):
        """初始化处理管道"""
        from aliyun_video_service import video_service
        from openai_speech_service import speech_service  # 使用OpenAI语音服务
        from aliyun_oss_service import oss_service
        
        self.video_service = video_service
        self.speech_service = speech_service
        self.oss_service = oss_service
        
        logger.info("阿里云视频处理管道初始化完成（使用OpenAI语音服务）")
    
    async def process_video(self, 
                          video_file: Optional[str] = None,
                          youtube_url: Optional[str] = None,
                          progress_callback: Optional[callable] = None) -> Dict[str, Any]:
        """
        处理视频的完整流程
        
        Args:
            video_file: 上传的视频文件路径
            youtube_url: YouTube视频URL
            progress_callback: 进度回调函数
            
        Returns:
            处理结果
        """
        if progress_callback:
            progress_callback("开始处理视频...")
        
        try:
            # 步骤1: 视频下载/上传和关键帧提取
            if progress_callback:
                progress_callback("处理视频文件和提取关键帧...")
            
            video_result = await self.video_service.process_video_dual_source(
                video_file=video_file,
                youtube_url=youtube_url
            )
            
            if video_result["status"] != "success":
                return video_result
            
            video_id = video_result["video_id"]
            video_info = video_result["video_info"]
            keyframes = video_result["keyframes"]
            video_metadata = video_result["video_metadata"]
            session_temp_dir = video_result["session_temp_dir"]
            
            # 确定视频文件路径
            if youtube_url:
                # 查找下载的视频文件
                session_path = Path(session_temp_dir)
                video_path = None
                for file_path in session_path.iterdir():
                    if file_path.suffix.lower() in ['.mp4', '.avi', '.mov', '.mkv']:
                        video_path = str(file_path)
                        break
            else:
                video_path = video_file
            
            if not video_path:
                return {
                    "status": "error",
                    "error": "找不到视频文件用于音频提取",
                    "video_id": video_id
                }
            
            # 步骤2: 并行处理音频转录
            if progress_callback:
                progress_callback("提取音频并进行转录...")
            
            # 启动音频转录任务
            audio_task = asyncio.create_task(
                self.speech_service.extract_and_transcribe_audio(video_path, video_id)
            )
            
            # 等待音频转录完成
            transcript_result = await audio_task
            
            if not transcript_result:
                logger.warning("音频转录失败，继续处理其他部分")
                transcript_result = self._create_empty_transcript()
            
            # 步骤3: 生成统一metadata
            if progress_callback:
                progress_callback("生成metadata...")
            
            metadata = await self._generate_unified_metadata(
                video_info, keyframes, transcript_result, video_metadata
            )
            
            # 步骤4: 上传metadata到OSS
            if progress_callback:
                progress_callback("上传metadata到OSS...")
            
            metadata_oss_url = await self.oss_service.upload_metadata(
                asdict(metadata), video_id
            )
            
            if metadata_oss_url:
                metadata.metadata_oss_url = metadata_oss_url
            
            # 步骤5: 清理临时文件
            if progress_callback:
                progress_callback("清理临时文件...")
            
            self.video_service.cleanup_session(session_temp_dir)
            
            # 完成
            if progress_callback:
                progress_callback("处理完成！")
            
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
            
            if progress_callback:
                progress_callback(f"处理失败: {error_msg}")
            
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
                    segment_meta = TranscriptSegmentMetadata(
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
    
    def check_services_availability(self) -> Dict[str, bool]:
        """检查所有服务的可用性"""
        return {
            "video_service": True,  # 视频服务总是可用
            "speech_service": self.speech_service.is_available(),
            "oss_service": self.oss_service.is_available()
        }


# 创建单例实例
pipeline = AliyunVideoProcessingPipeline()