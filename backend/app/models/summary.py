from pydantic import BaseModel, Field, HttpUrl
from typing import Optional, List, Dict, Any
from datetime import datetime
import uuid

class SummaryBase(BaseModel):
    """摘要基本信息"""
    video_url: str
    language: str = "zh"  # 默认为中文
    granularity: str = "medium"  # short, medium, detailed
    use_audio: bool = True
    speaker_diarization: bool = False
    keyframe_method: str = "uniform"  # uniform, interval, scene
    num_frames: int = 5
    interval_seconds: int = 10

class SummaryCreate(SummaryBase):
    """创建摘要请求"""
    pass

class SummaryInDB(SummaryBase):
    """存储在数据库(JSON文件)中的摘要信息"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = None
    status: str = "pending"  # pending, processing, completed, failed
    video_id: Optional[str] = None
    video_title: Optional[str] = None
    video_thumbnail: Optional[str] = None
    video_duration: Optional[int] = None
    summary_text: Optional[str] = None
    keyframes: List[str] = []
    audio_transcript: Optional[str] = None
    error_message: Optional[str] = None
    is_favorite: bool = False
    metadata: Dict[str, Any] = Field(default_factory=dict)

class SummaryRead(SummaryBase):
    """API返回的摘要信息"""
    id: str
    user_id: str
    created_at: datetime
    status: str
    video_id: Optional[str]
    video_title: Optional[str]
    video_thumbnail: Optional[str]
    video_duration: Optional[int]
    summary_text: Optional[str]
    keyframes: List[str]
    is_favorite: bool
    
class SummaryReadDetailed(SummaryRead):
    """详细的摘要信息，包括音频转录和元数据"""
    audio_transcript: Optional[str]
    metadata: Dict[str, Any]

class SummaryUpdate(BaseModel):
    """更新摘要信息"""
    is_favorite: Optional[bool] = None 