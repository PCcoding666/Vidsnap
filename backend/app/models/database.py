"""
SQLAlchemy 数据库模型
替代 Supabase，实现本地 PostgreSQL 数据持久化
"""
from datetime import datetime, timezone
from typing import Optional, List
from uuid import UUID, uuid4

from sqlalchemy import (
    Column, String, Boolean, Integer, BigInteger, Float, Text, Date,
    ForeignKey, DateTime, Index, CheckConstraint, UniqueConstraint,
    text
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import relationship, Mapped, mapped_column, DeclarativeBase
from sqlalchemy.ext.asyncio import AsyncAttrs, create_async_engine, async_sessionmaker, AsyncSession


# ============================================
# 基类
# ============================================
class Base(AsyncAttrs, DeclarativeBase):
    """SQLAlchemy 声明式基类"""
    pass


# ============================================
# 用户认证模型 (FastAPI-Users 要求)
# ============================================
class User(Base):
    """用户认证表 - FastAPI-Users 核心模型"""
    __tablename__ = "users"
    
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # OAuth 相关
    oauth_provider: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    oauth_account_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False
    )
    
    # 关系
    profile: Mapped[Optional["Profile"]] = relationship(
        "Profile", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    oauth_accounts: Mapped[List["OAuthAccount"]] = relationship(
        "OAuthAccount", back_populates="user", cascade="all, delete-orphan"
    )
    
    __table_args__ = (
        Index('idx_users_oauth', 'oauth_provider', 'oauth_account_id'),
    )


class OAuthAccount(Base):
    """OAuth 账号关联表"""
    __tablename__ = "oauth_accounts"
    
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), 
        ForeignKey("users.id", ondelete="CASCADE"), 
        nullable=False,
        index=True
    )
    oauth_name: Mapped[str] = mapped_column(String(100), nullable=False)
    access_token: Mapped[str] = mapped_column(String(1024), nullable=False)
    expires_at: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    refresh_token: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    account_id: Mapped[str] = mapped_column(String(320), nullable=False)
    account_email: Mapped[Optional[str]] = mapped_column(String(320), nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False
    )
    
    # 关系
    user: Mapped["User"] = relationship("User", back_populates="oauth_accounts")
    
    __table_args__ = (
        UniqueConstraint('oauth_name', 'account_id', name='uq_oauth_accounts_provider_account'),
    )


# ============================================
# 用户资料模型
# ============================================
class Profile(Base):
    """用户资料表"""
    __tablename__ = "profiles"
    
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), 
        ForeignKey("users.id", ondelete="CASCADE"), 
        primary_key=True
    )
    email: Mapped[str] = mapped_column(Text, nullable=False)
    username: Mapped[Optional[str]] = mapped_column(Text, unique=True, nullable=True)
    full_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    avatar_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    subscription_tier: Mapped[str] = mapped_column(
        Text, 
        default='free', 
        nullable=False
    )
    display_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    gender: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    birthday: Mapped[Optional[datetime]] = mapped_column(Date, nullable=True)
    language: Mapped[str] = mapped_column(Text, default='zh-CN', nullable=False)
    theme: Mapped[str] = mapped_column(Text, default='system', nullable=False)
    email_notifications: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notification_frequency: Mapped[str] = mapped_column(Text, default='realtime', nullable=False)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False
    )
    
    # 关系
    user: Mapped["User"] = relationship("User", back_populates="profile")
    quota: Mapped[Optional["UserQuota"]] = relationship(
        "UserQuota", back_populates="profile", uselist=False, cascade="all, delete-orphan"
    )
    videos: Mapped[List["Video"]] = relationship(
        "Video", back_populates="owner", cascade="all, delete-orphan"
    )
    subscriptions: Mapped[List["YouTubeSubscription"]] = relationship(
        "YouTubeSubscription", back_populates="owner", cascade="all, delete-orphan"
    )
    
    __table_args__ = (
        CheckConstraint(
            "subscription_tier IN ('free', 'pro', 'ultra', 'enterprise')",
            name='check_subscription_tier'
        ),
        CheckConstraint(
            "gender IN ('male', 'female', 'other', 'prefer_not_to_say') OR gender IS NULL",
            name='check_gender'
        ),
        CheckConstraint(
            "theme IN ('system', 'light', 'dark')",
            name='check_theme'
        ),
        CheckConstraint(
            "notification_frequency IN ('realtime', 'daily', 'weekly')",
            name='check_notification_frequency'
        ),
    )


class UserQuota(Base):
    """用户配额表"""
    __tablename__ = "user_quotas"
    
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), 
        ForeignKey("profiles.id", ondelete="CASCADE"), 
        primary_key=True
    )
    monthly_video_limit: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    monthly_videos_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_storage_mb: Mapped[int] = mapped_column(Integer, default=1000, nullable=False)
    used_storage_mb: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reset_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    max_channel_subscriptions: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    max_video_duration_seconds: Mapped[int] = mapped_column(Integer, default=600, nullable=False)
    api_access_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    priority_processing: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False
    )
    
    # 关系
    profile: Mapped["Profile"] = relationship("Profile", back_populates="quota")
    
    __table_args__ = (
        CheckConstraint('monthly_videos_used >= 0', name='check_monthly_videos_used'),
        CheckConstraint('used_storage_mb >= 0', name='check_used_storage_mb'),
    )


# ============================================
# 视频相关模型
# ============================================
class Video(Base):
    """视频表"""
    __tablename__ = "videos"
    
    video_id: Mapped[str] = mapped_column(Text, primary_key=True)
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), 
        ForeignKey("profiles.id", ondelete="CASCADE"), 
        nullable=False,
        index=True
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    duration: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    source_type: Mapped[str] = mapped_column(Text, nullable=False)
    original_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    oss_video_url: Mapped[str] = mapped_column(Text, nullable=False)
    oss_audio_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    video_format: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    video_size: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    video_resolution: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    processing_status: Mapped[str] = mapped_column(Text, default='pending', nullable=False)
    processing_progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    upload_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )
    processing_started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    processing_completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False
    )
    
    # 关系
    owner: Mapped["Profile"] = relationship("Profile", back_populates="videos")
    summaries: Mapped[List["VideoSummary"]] = relationship(
        "VideoSummary", back_populates="video", cascade="all, delete-orphan"
    )
    transcript: Mapped[Optional["Transcript"]] = relationship(
        "Transcript", back_populates="video", uselist=False, cascade="all, delete-orphan"
    )
    segments: Mapped[List["TranscriptSegment"]] = relationship(
        "TranscriptSegment", back_populates="video", cascade="all, delete-orphan"
    )
    keyframes: Mapped[List["Keyframe"]] = relationship(
        "Keyframe", back_populates="video", cascade="all, delete-orphan"
    )
    
    __table_args__ = (
        Index('idx_videos_status', 'processing_status'),
        Index('idx_videos_created_at', 'created_at'),
        CheckConstraint(
            "source_type IN ('youtube', 'upload', 'youtube_transcript')",
            name='check_source_type'
        ),
        CheckConstraint(
            "processing_status IN ('pending', 'processing', 'completed', 'failed')",
            name='check_processing_status'
        ),
        CheckConstraint(
            'processing_progress >= 0 AND processing_progress <= 100',
            name='check_processing_progress'
        ),
    )


class VideoSummary(Base):
    """视频总结表"""
    __tablename__ = "video_summaries"
    
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    video_id: Mapped[str] = mapped_column(
        Text, 
        ForeignKey("videos.video_id", ondelete="CASCADE"), 
        nullable=False,
        index=True
    )
    summary_type: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    model_used: Mapped[str] = mapped_column(Text, default='qwen3-vl-flash', nullable=False)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )
    
    # 关系
    video: Mapped["Video"] = relationship("Video", back_populates="summaries")
    
    __table_args__ = (
        CheckConstraint(
            "summary_type IN ('brief', 'standard', 'detailed')",
            name='check_summary_type'
        ),
    )


class Transcript(Base):
    """转录记录表"""
    __tablename__ = "transcripts"
    
    video_id: Mapped[str] = mapped_column(
        Text, 
        ForeignKey("videos.video_id", ondelete="CASCADE"), 
        primary_key=True
    )
    language: Mapped[str] = mapped_column(Text, default='zh-CN', nullable=False)
    overall_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    total_segments: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )
    
    # 关系
    video: Mapped["Video"] = relationship("Video", back_populates="transcript")


class TranscriptSegment(Base):
    """转录段落表"""
    __tablename__ = "transcript_segments"
    
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    video_id: Mapped[str] = mapped_column(
        Text, 
        ForeignKey("videos.video_id", ondelete="CASCADE"), 
        nullable=False,
        index=True
    )
    segment_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    start_time: Mapped[float] = mapped_column(Float, nullable=False)
    end_time: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    speaker_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )
    
    # 关系
    video: Mapped["Video"] = relationship("Video", back_populates="segments")


class Keyframe(Base):
    """关键帧表"""
    __tablename__ = "keyframes"
    
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    video_id: Mapped[str] = mapped_column(
        Text, 
        ForeignKey("videos.video_id", ondelete="CASCADE"), 
        nullable=False,
        index=True
    )
    frame_id: Mapped[int] = mapped_column(Integer, nullable=False)
    timestamp: Mapped[float] = mapped_column(Float, nullable=False)
    oss_image_url: Mapped[str] = mapped_column(Text, nullable=False)
    scene_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )
    
    # 关系
    video: Mapped["Video"] = relationship("Video", back_populates="keyframes")


# ============================================
# YouTube 订阅相关模型
# ============================================
class YouTubeSubscription(Base):
    """YouTube 订阅表"""
    __tablename__ = "youtube_subscriptions"
    
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), 
        ForeignKey("profiles.id", ondelete="CASCADE"), 
        nullable=False,
        index=True
    )
    channel_id: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    channel_name: Mapped[str] = mapped_column(Text, nullable=False)
    channel_avatar: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    channel_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    subscriber_count: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    video_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_checked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_video_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    last_video_published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    check_interval_minutes: Mapped[int] = mapped_column(Integer, default=5, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False
    )
    
    # 关系
    owner: Mapped["Profile"] = relationship("Profile", back_populates="subscriptions")
    auto_analyzed_videos: Mapped[List["AutoAnalyzedVideo"]] = relationship(
        "AutoAnalyzedVideo", back_populates="subscription", cascade="all, delete-orphan"
    )
    
    __table_args__ = (
        UniqueConstraint('user_id', 'channel_id', name='uq_user_channel'),
    )


class AutoAnalyzedVideo(Base):
    """自动分析视频表"""
    __tablename__ = "auto_analyzed_videos"
    
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    subscription_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), 
        ForeignKey("youtube_subscriptions.id", ondelete="CASCADE"), 
        nullable=False,
        index=True
    )
    video_id: Mapped[Optional[str]] = mapped_column(
        Text, 
        ForeignKey("videos.video_id", ondelete="SET NULL"), 
        nullable=True
    )
    youtube_video_id: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    youtube_video_title: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    youtube_video_thumbnail: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    youtube_video_duration: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    youtube_video_published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )
    analysis_status: Mapped[str] = mapped_column(Text, default='pending', nullable=False)
    analysis_started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    analysis_completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False
    )
    
    # 关系
    subscription: Mapped["YouTubeSubscription"] = relationship(
        "YouTubeSubscription", back_populates="auto_analyzed_videos"
    )
    
    __table_args__ = (
        Index('idx_auto_analyzed_videos_status', 'analysis_status'),
        CheckConstraint(
            "analysis_status IN ('pending', 'processing', 'completed', 'failed', 'skipped')",
            name='check_analysis_status'
        ),
    )


class SchemaVersion(Base):
    """Schema 版本控制表"""
    __tablename__ = "schema_versions"
    
    version: Mapped[str] = mapped_column(Text, primary_key=True)
    applied_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


# ============================================
# 数据库连接配置
# ============================================
class DatabaseConfig:
    """数据库配置管理"""
    
    def __init__(self, database_url: str):
        self.database_url = database_url
        self.engine = create_async_engine(
            database_url,
            echo=False,  # 生产环境关闭 SQL 日志
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,
        )
        self.async_session_maker = async_sessionmaker(
            self.engine, 
            class_=AsyncSession, 
            expire_on_commit=False
        )
    
    async def get_async_session(self) -> AsyncSession:
        """获取异步数据库会话"""
        async with self.async_session_maker() as session:
            yield session
    
    async def create_all_tables(self):
        """创建所有表（仅用于测试）"""
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    
    async def drop_all_tables(self):
        """删除所有表（仅用于测试）"""
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)


# 全局数据库配置实例（将在 app 启动时初始化）
db_config: DatabaseConfig = None


def init_database(database_url: str) -> DatabaseConfig:
    """初始化数据库配置"""
    global db_config
    db_config = DatabaseConfig(database_url)
    return db_config


def get_db_config() -> DatabaseConfig:
    """获取数据库配置"""
    if db_config is None:
        raise RuntimeError("数据库未初始化，请先调用 init_database()")
    return db_config

