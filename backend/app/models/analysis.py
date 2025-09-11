"""
Data models for video analysis results.
"""
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class TranscriptSegment:
    """转录段落"""
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
    segments: List[TranscriptSegment]


@dataclass
class KeyframeMetadata:
    """关键帧元数据"""
    frame_id: int
    timestamp: float
    oss_image_url: str
    scene_description: str


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