"""
Data models for video processing.
"""
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional


@dataclass
class KeyframeInfo:
    """关键帧信息"""
    frame_id: int
    timestamp: float
    local_path: str
    oss_image_url: Optional[str] = None
    scene_description: str = ""


@dataclass
class VideoInfo:
    """视频基础信息"""
    video_id: str
    title: Optional[str] = None
    duration: float = 0.0
    oss_video_url: Optional[str] = None
    upload_time: datetime = None
    source_type: str = "upload"
    original_url: Optional[str] = None
