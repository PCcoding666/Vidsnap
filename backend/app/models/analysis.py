"""
Data models for video analysis results.
"""
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class TranscriptSegment:
    """转录段落元数据"""
    text: str
    start_time: float
    end_time: float
    confidence: float
    chunk_id: Optional[str] = None
    provider: Optional[str] = None


# 为了兼容性保留旧名称
TranscriptSegmentMetadata = TranscriptSegment


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
class KeyframeDescription:
    """单个关键帧的 LLM 分析描述"""
    frame_id: int
    timestamp: float
    description: str
    oss_image_url: str
    confidence: float


@dataclass
class SummarySection:
    """基于时间线的总结段落"""
    start_time: float
    end_time: float
    title: str
    content: str
    keyframe_ids: List[int]  # 关联的关键帧ID


@dataclass
class VideoSummary:
    """视频总结（由 LLM 生成）- v0.2.0 精简版"""
    video_id: str
    detailed_summary: str  # 详细总结内容


@dataclass
class VideoMetadata:
    """完整的视频元数据"""
    # 基本信息
    video_id: str
    title: str
    duration: float
    oss_video_url: str
    source_type: str
    upload_time: str
    processing_completed_time: str
    keyframes: List[KeyframeMetadata]
    transcript: TranscriptMetadata
    processing_status: str
    
    # 可选字段
    original_url: Optional[str] = None
    metadata_oss_url: Optional[str] = None
    
    # 技术信息
    video_format: Optional[str] = None
    video_size: Optional[int] = None
    video_resolution: Optional[str] = None
