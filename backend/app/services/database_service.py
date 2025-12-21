"""
Database Service - 本地 PostgreSQL 数据持久化服务
替代 Supabase Service，提供用户认证和数据存储功能
保持 API 兼容性以便平滑迁移
"""
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone, timedelta
from dataclasses import asdict
from uuid import UUID

from sqlalchemy import select, update, delete, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert

from app.models.database import (
    User, Profile, UserQuota, Video, VideoSummary, 
    Transcript, TranscriptSegment, Keyframe,
    YouTubeSubscription, AutoAnalyzedVideo, OAuthAccount,
    get_db_config, init_database
)
from app.core.config import settings

logger = logging.getLogger(__name__)


class DatabaseService:
    """
    本地数据库服务类
    
    提供与 SupabaseService 兼容的接口，便于平滑迁移
    """
    
    def __init__(self):
        """初始化数据库服务"""
        self._initialized = False
        self._db_config = None
    
    async def initialize(self):
        """异步初始化数据库连接"""
        if self._initialized:
            return
        
        try:
            self._db_config = init_database(settings.DATABASE_URL)
            self._initialized = True
            logger.info(f"✅ 数据库服务初始化成功")
        except Exception as e:
            logger.error(f"❌ 数据库初始化失败: {e}")
            raise
    
    def is_available(self) -> bool:
        """检查数据库服务是否可用"""
        return self._initialized and self._db_config is not None
    
    async def _get_session(self) -> AsyncSession:
        """获取数据库会话"""
        if not self.is_available():
            raise RuntimeError("数据库服务未初始化")
        async with self._db_config.async_session_maker() as session:
            return session
    
    # ========================================================================
    # 用户认证相关方法
    # ========================================================================
    
    async def verify_token(self, token: str) -> Optional[Dict[str, Any]]:
        """
        验证 JWT Token
        
        Args:
            token: JWT Token
        
        Returns:
            {"id": "uuid", "email": "..."} 或 None(Token 无效)
        """
        from app.core.auth import verify_jwt_token
        return verify_jwt_token(token)
    
    async def get_user_profile(self, user_id: str) -> Optional[Dict[str, Any]]:
        """获取用户资料"""
        if not self.is_available():
            return None
        
        try:
            async with self._db_config.async_session_maker() as session:
                result = await session.execute(
                    select(Profile).where(Profile.id == UUID(user_id))
                )
                profile = result.scalar_one_or_none()
                
                if profile:
                    return {
                        "id": str(profile.id),
                        "email": profile.email,
                        "username": profile.username,
                        "full_name": profile.full_name,
                        "avatar_url": profile.avatar_url,
                        "subscription_tier": profile.subscription_tier,
                        "display_name": profile.display_name,
                        "gender": profile.gender,
                        "birthday": profile.birthday.isoformat() if profile.birthday else None,
                        "language": profile.language,
                        "theme": profile.theme,
                        "email_notifications": profile.email_notifications,
                        "notification_frequency": profile.notification_frequency,
                        "created_at": profile.created_at.isoformat(),
                        "updated_at": profile.updated_at.isoformat(),
                    }
                return None
        except Exception as e:
            logger.error(f"❌ 获取用户资料失败: {e}")
            return None
    
    async def update_user_profile(
        self, 
        user_id: str, 
        update_data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """更新用户资料"""
        if not self.is_available():
            return None
        
        try:
            async with self._db_config.async_session_maker() as session:
                # 过滤掉不能更新的字段
                allowed_fields = {
                    'username', 'full_name', 'avatar_url', 'display_name',
                    'gender', 'birthday', 'language', 'theme',
                    'email_notifications', 'notification_frequency'
                }
                filtered_data = {k: v for k, v in update_data.items() if k in allowed_fields}
                
                if filtered_data:
                    await session.execute(
                        update(Profile)
                        .where(Profile.id == UUID(user_id))
                        .values(**filtered_data)
                    )
                    await session.commit()
                
                return await self.get_user_profile(user_id)
        except Exception as e:
            logger.error(f"❌ 更新用户资料失败: {e}")
            return None
    
    # ========================================================================
    # 配额管理相关方法
    # ========================================================================
    
    async def check_user_quota(self, user_id: str) -> bool:
        """
        检查用户配额是否充足
        
        Args:
            user_id: 用户 ID
        
        Returns:
            True: 配额充足, False: 已达上限
        """
        if not self.is_available():
            return True  # 服务不可用时不限制
        
        try:
            async with self._db_config.async_session_maker() as session:
                result = await session.execute(
                    select(UserQuota).where(UserQuota.user_id == UUID(user_id))
                )
                quota = result.scalar_one_or_none()
                
                if not quota:
                    return True  # 没有配额记录时不限制
                
                videos_ok = quota.monthly_videos_used < quota.monthly_video_limit
                storage_ok = quota.used_storage_mb < quota.total_storage_mb
                
                if not videos_ok:
                    logger.warning(f"⚠️ 用户 {user_id} 已达视频处理上限")
                if not storage_ok:
                    logger.warning(f"⚠️ 用户 {user_id} 存储空间已满")
                
                return videos_ok and storage_ok
        except Exception as e:
            logger.error(f"❌ 检查配额失败: {e}")
            return True  # 出错时不限制
    
    async def get_user_quota(self, user_id: str) -> Optional[Dict[str, Any]]:
        """获取用户配额信息"""
        if not self.is_available():
            return None
        
        try:
            async with self._db_config.async_session_maker() as session:
                result = await session.execute(
                    select(UserQuota).where(UserQuota.user_id == UUID(user_id))
                )
                quota = result.scalar_one_or_none()
                
                if quota:
                    return {
                        "user_id": str(quota.user_id),
                        "monthly_video_limit": quota.monthly_video_limit,
                        "monthly_videos_used": quota.monthly_videos_used,
                        "total_storage_mb": quota.total_storage_mb,
                        "used_storage_mb": quota.used_storage_mb,
                        "reset_date": quota.reset_date.isoformat(),
                        "max_channel_subscriptions": quota.max_channel_subscriptions,
                        "max_video_duration_seconds": quota.max_video_duration_seconds,
                        "api_access_enabled": quota.api_access_enabled,
                        "priority_processing": quota.priority_processing,
                    }
                return None
        except Exception as e:
            logger.error(f"❌ 获取配额失败: {e}")
            return None
    
    async def increment_video_usage(self, user_id: str):
        """递增用户的视频使用次数"""
        if not self.is_available():
            return
        
        try:
            async with self._db_config.async_session_maker() as session:
                await session.execute(
                    update(UserQuota)
                    .where(UserQuota.user_id == UUID(user_id))
                    .values(monthly_videos_used=UserQuota.monthly_videos_used + 1)
                )
                await session.commit()
                logger.info(f"✅ 用户 {user_id} 视频使用次数 +1")
        except Exception as e:
            logger.error(f"❌ 递增视频使用次数失败: {e}")
    
    async def update_storage_usage(self, user_id: str, size_mb: int):
        """更新用户的存储使用量"""
        if not self.is_available():
            return
        
        try:
            async with self._db_config.async_session_maker() as session:
                await session.execute(
                    update(UserQuota)
                    .where(UserQuota.user_id == UUID(user_id))
                    .values(used_storage_mb=UserQuota.used_storage_mb + size_mb)
                )
                await session.commit()
                logger.info(f"✅ 用户 {user_id} 存储使用量 +{size_mb}MB")
        except Exception as e:
            logger.error(f"❌ 更新存储使用量失败: {e}")
    
    # ========================================================================
    # 视频记录管理
    # ========================================================================
    
    async def create_video_record(self, video_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        创建视频记录
        
        Args:
            video_data: 视频数据字典
        
        Returns:
            插入的完整记录
        """
        if not self.is_available():
            return None
        
        try:
            async with self._db_config.async_session_maker() as session:
                video = Video(
                    video_id=video_data.get('video_id'),
                    user_id=UUID(video_data.get('user_id')),
                    title=video_data.get('title'),
                    duration=video_data.get('duration'),
                    source_type=video_data.get('source_type'),
                    original_url=video_data.get('original_url'),
                    oss_video_url=video_data.get('oss_video_url'),
                    oss_audio_url=video_data.get('oss_audio_url'),
                    video_format=video_data.get('video_format'),
                    video_size=video_data.get('video_size'),
                    video_resolution=video_data.get('video_resolution'),
                    processing_status=video_data.get('processing_status', 'pending'),
                    processing_progress=video_data.get('processing_progress', 0),
                )
                session.add(video)
                await session.commit()
                await session.refresh(video)
                
                logger.info(f"✅ 创建视频记录: {video_data.get('video_id')}")
                return await self.get_video_by_id(video.video_id)
        except Exception as e:
            logger.error(f"❌ 创建视频记录失败: {e}")
            return None
    
    async def update_video_status(
        self, 
        video_id: str, 
        status: str, 
        progress: Optional[int] = None,
        error_message: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        更新视频处理状态
        
        Args:
            video_id: 视频 ID
            status: 处理状态 (pending/processing/completed/failed)
            progress: 处理进度 (0-100)
            error_message: 错误信息(仅 status='failed' 时)
        
        Returns:
            更新后的记录
        """
        if not self.is_available():
            return None
        
        try:
            async with self._db_config.async_session_maker() as session:
                update_data = {
                    "processing_status": status,
                }
                
                if progress is not None:
                    update_data["processing_progress"] = progress
                
                # 设置开始/完成时间
                if status == "processing":
                    update_data["processing_started_at"] = datetime.now(timezone.utc)
                elif status == "completed":
                    update_data["processing_completed_at"] = datetime.now(timezone.utc)
                elif status == "failed" and error_message:
                    update_data["error_message"] = error_message
                
                await session.execute(
                    update(Video)
                    .where(Video.video_id == video_id)
                    .values(**update_data)
                )
                await session.commit()
                
                logger.info(f"✅ 更新视频状态: {video_id} -> {status} ({progress}%)")
                return await self.get_video_by_id(video_id)
        except Exception as e:
            logger.error(f"❌ 更新视频状态失败: {e}")
            return None
    
    async def update_video_urls(
        self, 
        video_id: str, 
        oss_video_url: Optional[str] = None, 
        oss_audio_url: Optional[str] = None
    ):
        """更新视频的 OSS URL"""
        if not self.is_available():
            return
        
        try:
            async with self._db_config.async_session_maker() as session:
                update_data = {}
                if oss_video_url:
                    update_data["oss_video_url"] = oss_video_url
                if oss_audio_url:
                    update_data["oss_audio_url"] = oss_audio_url
                
                if update_data:
                    await session.execute(
                        update(Video)
                        .where(Video.video_id == video_id)
                        .values(**update_data)
                    )
                    await session.commit()
                    logger.info(f"✅ 更新视频 URL: {video_id}")
        except Exception as e:
            logger.error(f"❌ 更新视频 URL 失败: {e}")
    
    # ========================================================================
    # 批量数据保存
    # ========================================================================
    
    async def save_keyframes(self, video_id: str, keyframes: List[Any]) -> bool:
        """
        批量保存关键帧数据
        
        Args:
            video_id: 视频 ID
            keyframes: KeyframeInfo dataclass 列表
        
        Returns:
            是否保存成功
        """
        if not self.is_available():
            return False
        
        try:
            async with self._db_config.async_session_maker() as session:
                # 转换为 ORM 对象
                keyframe_objects = []
                for kf in keyframes:
                    kf_dict = asdict(kf) if hasattr(kf, '__dataclass_fields__') else kf
                    keyframe_objects.append(Keyframe(
                        video_id=video_id,
                        frame_id=kf_dict.get("frame_id"),
                        timestamp=kf_dict.get("timestamp"),
                        oss_image_url=kf_dict.get("oss_image_url"),
                        scene_description=kf_dict.get("scene_description", "")
                    ))
                
                session.add_all(keyframe_objects)
                await session.commit()
                
                logger.info(f"✅ 保存 {len(keyframe_objects)} 个关键帧: {video_id}")
                return True
        except Exception as e:
            logger.error(f"❌ 保存关键帧失败: {e}")
            return False
    
    async def save_transcript_segments(self, video_id: str, segments: List[Any]) -> bool:
        """
        批量保存转录段落
        
        Args:
            video_id: 视频 ID
            segments: TranscriptSegment 列表
        
        Returns:
            是否保存成功
        """
        if not self.is_available():
            logger.warning(f"[DEBUG] 数据库不可用，无法保存转录段落: {video_id}")
            return False
        
        try:
            logger.info(f"[DEBUG] 开始保存 {len(segments)} 个转录段落: {video_id}")
            
            async with self._db_config.async_session_maker() as session:
                # 转换为 ORM 对象
                segment_objects = []
                for i, seg in enumerate(segments):
                    seg_dict = asdict(seg) if hasattr(seg, '__dataclass_fields__') else seg
                    segment_objects.append(TranscriptSegment(
                        video_id=video_id,
                        segment_index=i,
                        text=seg_dict.get("text"),
                        start_time=seg_dict.get("start_time"),
                        end_time=seg_dict.get("end_time"),
                        confidence=seg_dict.get("confidence"),
                        speaker_id=seg_dict.get("speaker_id")
                    ))
                
                logger.info(f"[DEBUG] 准备插入 {len(segment_objects)} 条记录")
                
                session.add_all(segment_objects)
                await session.commit()
                
                logger.info(f"[DEBUG] 插入结果: True")
                
                # 更新或创建 transcripts 表记录
                transcript = Transcript(
                    video_id=video_id,
                    total_segments=len(segment_objects)
                )
                await session.merge(transcript)
                await session.commit()
                
                logger.info(f"✅ 保存 {len(segment_objects)} 个转录段落: {video_id}")
                return True
        except Exception as e:
            logger.error(f"❌ 保存转录段落失败: {e}")
            logger.exception(e)
            return False
    
    async def save_video_summary(
        self, 
        video_id: str, 
        summary_type: str, 
        content: str,
        model_used: str = "qwen3-vl-flash"
    ) -> bool:
        """
        保存视频总结(使用 UPSERT 避免重复)
        
        Args:
            video_id: 视频 ID
            summary_type: 总结类型 (brief/standard/detailed)
            content: 总结内容
            model_used: 使用的 AI 模型
        
        Returns:
            是否保存成功
        """
        if not self.is_available():
            return False
        
        try:
            async with self._db_config.async_session_maker() as session:
                # 先查找是否存在
                result = await session.execute(
                    select(VideoSummary)
                    .where(VideoSummary.video_id == video_id)
                    .where(VideoSummary.summary_type == summary_type)
                )
                existing = result.scalar_one_or_none()
                
                if existing:
                    # 更新
                    existing.content = content
                    existing.model_used = model_used
                else:
                    # 插入
                    summary = VideoSummary(
                        video_id=video_id,
                        summary_type=summary_type,
                        content=content,
                        model_used=model_used
                    )
                    session.add(summary)
                
                await session.commit()
                logger.info(f"✅ 保存视频总结: {video_id} ({summary_type})")
                return True
        except Exception as e:
            logger.error(f"❌ 保存视频总结失败: {e}")
            return False
    
    # ========================================================================
    # 查询方法
    # ========================================================================
    
    async def get_video_by_id(self, video_id: str) -> Optional[Dict[str, Any]]:
        """根据 ID 查询视频信息"""
        if not self.is_available():
            return None
        
        try:
            async with self._db_config.async_session_maker() as session:
                result = await session.execute(
                    select(Video).where(Video.video_id == video_id)
                )
                video = result.scalar_one_or_none()
                
                if video:
                    return {
                        "video_id": video.video_id,
                        "user_id": str(video.user_id),
                        "title": video.title,
                        "duration": video.duration,
                        "source_type": video.source_type,
                        "original_url": video.original_url,
                        "oss_video_url": video.oss_video_url,
                        "oss_audio_url": video.oss_audio_url,
                        "video_format": video.video_format,
                        "video_size": video.video_size,
                        "video_resolution": video.video_resolution,
                        "processing_status": video.processing_status,
                        "processing_progress": video.processing_progress,
                        "error_message": video.error_message,
                        "upload_time": video.upload_time.isoformat(),
                        "processing_started_at": video.processing_started_at.isoformat() if video.processing_started_at else None,
                        "processing_completed_at": video.processing_completed_at.isoformat() if video.processing_completed_at else None,
                        "created_at": video.created_at.isoformat(),
                        "updated_at": video.updated_at.isoformat(),
                    }
                return None
        except Exception as e:
            logger.error(f"❌ 查询视频失败: {e}")
            return None
    
    async def get_user_videos(self, user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """查询用户的视频列表"""
        if not self.is_available():
            return []
        
        try:
            async with self._db_config.async_session_maker() as session:
                result = await session.execute(
                    select(Video)
                    .where(Video.user_id == UUID(user_id))
                    .order_by(Video.created_at.desc())
                    .limit(limit)
                )
                videos = result.scalars().all()
                
                return [
                    {
                        "video_id": v.video_id,
                        "user_id": str(v.user_id),
                        "title": v.title,
                        "duration": v.duration,
                        "source_type": v.source_type,
                        "original_url": v.original_url,
                        "oss_video_url": v.oss_video_url,
                        "processing_status": v.processing_status,
                        "processing_progress": v.processing_progress,
                        "created_at": v.created_at.isoformat(),
                    }
                    for v in videos
                ]
        except Exception as e:
            logger.error(f"❌ 查询用户视频列表失败: {e}")
            return []
    
    async def get_keyframes(self, video_id: str) -> List[Dict[str, Any]]:
        """获取指定视频的关键帧列表"""
        if not self.is_available():
            return []
        try:
            async with self._db_config.async_session_maker() as session:
                result = await session.execute(
                    select(Keyframe)
                    .where(Keyframe.video_id == video_id)
                    .order_by(Keyframe.timestamp)
                )
                keyframes = result.scalars().all()
                
                return [
                    {
                        "frame_id": kf.frame_id,
                        "timestamp": kf.timestamp,
                        "oss_image_url": kf.oss_image_url,
                        "scene_description": kf.scene_description,
                    }
                    for kf in keyframes
                ]
        except Exception as e:
            logger.error(f"❌ 获取关键帧失败: {e}")
            return []
    
    async def get_transcript_segments(self, video_id: str) -> List[Dict[str, Any]]:
        """获取指定视频的转录段落列表"""
        if not self.is_available():
            return []
        try:
            async with self._db_config.async_session_maker() as session:
                result = await session.execute(
                    select(TranscriptSegment)
                    .where(TranscriptSegment.video_id == video_id)
                    .order_by(TranscriptSegment.segment_index)
                )
                segments = result.scalars().all()
                
                return [
                    {
                        "segment_index": seg.segment_index,
                        "text": seg.text,
                        "start_time": seg.start_time,
                        "end_time": seg.end_time,
                        "confidence": seg.confidence,
                    }
                    for seg in segments
                ]
        except Exception as e:
            logger.error(f"❌ 获取转录段落失败: {e}")
            return []
    
    async def get_video_summaries(self, video_id: str) -> Dict[str, str]:
        """获取指定视频的各粒度总结内容"""
        if not self.is_available():
            return {}
        try:
            async with self._db_config.async_session_maker() as session:
                result = await session.execute(
                    select(VideoSummary)
                    .where(VideoSummary.video_id == video_id)
                )
                summaries = result.scalars().all()
                
                return {s.summary_type: s.content for s in summaries}
        except Exception as e:
            logger.error(f"❌ 获取视频总结失败: {e}")
            return {}
    
    async def get_compiled_metadata(self, video_id: str) -> Optional[Dict[str, Any]]:
        """
        汇聚视频完整上下文：关键帧、转录文本、视频元数据、AI总结
        确保聊天对话中VL模型能访问完整的分析历史信息
        
        Returns:
            {
              "transcript": { oss_audio_url, language, overall_confidence, segments: [...] },
              "keyframes": [...],
              "video": { title, duration, oss_video_url, original_url, source_type },
              "summaries": { brief?, standard?, detailed? }
            }
        """
        if not self.is_available():
            logger.warning(f"[DEBUG] 数据库不可用，无法编译metadata: {video_id}")
            return None
        try:
            logger.info(f"[DEBUG] 开始编译视频上下文: {video_id}")
            video = await self.get_video_by_id(video_id) or {}
            logger.info(f"[DEBUG] 获取video: {bool(video)}")
            
            keyframes = await self.get_keyframes(video_id)
            logger.info(f"[DEBUG] 获取keyframes: {len(keyframes)}")
            
            segments = await self.get_transcript_segments(video_id)
            logger.info(f"[DEBUG] 获取segments: {len(segments)} 个转录段")
            if segments:
                logger.info(f"[DEBUG] 第一个segment示例: {segments[0]}")
            
            summaries = await self.get_video_summaries(video_id)
            logger.info(f"[DEBUG] 获取summaries: {list(summaries.keys()) if summaries else []}")

            transcript = {
                "oss_audio_url": video.get("oss_audio_url") or "",
                "language": "zh-CN",
                "overall_confidence": 0.0,
                "segments": [
                    {
                        "text": s.get("text") or "",
                        "start_time": float(s.get("start_time") or 0.0),
                        "end_time": float(s.get("end_time") or 0.0),
                        "confidence": float(s.get("confidence") or 0.0),
                    } for s in segments
                ],
            }
            logger.info(f"[DEBUG] 组装transcript: segments={len(transcript['segments'])}")

            video_meta = {
                "title": video.get("title") or "未知标题",
                "duration": float(video.get("duration") or 0.0),
                "oss_video_url": video.get("oss_video_url") or "",
                "original_url": video.get("original_url") or "",
                "source_type": video.get("source_type") or "unknown",
            }

            compiled = {
                "transcript": transcript,
                "keyframes": keyframes,
                "video": video_meta,
                "summaries": summaries,
            }
            logger.info(f"✅ 编译视频上下文成功: {video_id} | 关键帧={len(keyframes)} 转录段={len(segments)}")
            return compiled
        except Exception as e:
            logger.error(f"❌ 编译视频上下文失败: {e}")
            logger.exception(e)
            return None
    
    # ========================================================================
    # YouTube 订阅相关方法
    # ========================================================================
    
    async def get_user_subscriptions(self, user_id: str) -> List[Dict[str, Any]]:
        """获取用户的 YouTube 订阅列表"""
        if not self.is_available():
            return []
        
        try:
            async with self._db_config.async_session_maker() as session:
                result = await session.execute(
                    select(YouTubeSubscription)
                    .where(YouTubeSubscription.user_id == UUID(user_id))
                    .order_by(YouTubeSubscription.created_at.desc())
                )
                subs = result.scalars().all()
                
                return [
                    {
                        "id": str(s.id),
                        "user_id": str(s.user_id),
                        "channel_id": s.channel_id,
                        "channel_name": s.channel_name,
                        "channel_avatar": s.channel_avatar,
                        "channel_description": s.channel_description,
                        "subscriber_count": s.subscriber_count,
                        "video_count": s.video_count,
                        "is_active": s.is_active,
                        "last_checked_at": s.last_checked_at.isoformat() if s.last_checked_at else None,
                        "last_video_id": s.last_video_id,
                        "check_interval_minutes": s.check_interval_minutes,
                        "created_at": s.created_at.isoformat(),
                    }
                    for s in subs
                ]
        except Exception as e:
            logger.error(f"❌ 获取订阅列表失败: {e}")
            return []
    
    async def create_subscription(self, subscription_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """创建 YouTube 订阅"""
        if not self.is_available():
            return None
        
        try:
            async with self._db_config.async_session_maker() as session:
                sub = YouTubeSubscription(
                    user_id=UUID(subscription_data.get('user_id')),
                    channel_id=subscription_data.get('channel_id'),
                    channel_name=subscription_data.get('channel_name'),
                    channel_avatar=subscription_data.get('channel_avatar'),
                    channel_description=subscription_data.get('channel_description'),
                    subscriber_count=subscription_data.get('subscriber_count'),
                    video_count=subscription_data.get('video_count'),
                )
                session.add(sub)
                await session.commit()
                await session.refresh(sub)
                
                logger.info(f"✅ 创建订阅: {subscription_data.get('channel_name')}")
                return {"id": str(sub.id)}
        except Exception as e:
            logger.error(f"❌ 创建订阅失败: {e}")
            return None
    
    async def delete_subscription(self, subscription_id: str) -> bool:
        """删除 YouTube 订阅"""
        if not self.is_available():
            return False
        
        try:
            async with self._db_config.async_session_maker() as session:
                await session.execute(
                    delete(YouTubeSubscription)
                    .where(YouTubeSubscription.id == UUID(subscription_id))
                )
                await session.commit()
                logger.info(f"✅ 删除订阅: {subscription_id}")
                return True
        except Exception as e:
            logger.error(f"❌ 删除订阅失败: {e}")
            return False


# 创建全局实例
database_service = DatabaseService()


# ============================================
# 兼容层：提供与 supabase_service 相同的同步接口
# ============================================
class SyncDatabaseServiceWrapper:
    """
    同步包装器，用于兼容旧代码
    注意：这些方法实际上是同步的，但内部使用 asyncio.run()
    """
    
    def __init__(self, async_service: DatabaseService):
        self._async_service = async_service
    
    def is_available(self) -> bool:
        return self._async_service.is_available()
    
    def verify_token(self, token: str) -> Optional[Dict[str, Any]]:
        import asyncio
        return asyncio.get_event_loop().run_until_complete(
            self._async_service.verify_token(token)
        )
    
    def get_user_profile(self, user_id: str) -> Optional[Dict[str, Any]]:
        import asyncio
        return asyncio.get_event_loop().run_until_complete(
            self._async_service.get_user_profile(user_id)
        )
    
    def check_user_quota(self, user_id: str) -> bool:
        import asyncio
        return asyncio.get_event_loop().run_until_complete(
            self._async_service.check_user_quota(user_id)
        )
    
    def increment_video_usage(self, user_id: str):
        import asyncio
        asyncio.get_event_loop().run_until_complete(
            self._async_service.increment_video_usage(user_id)
        )
    
    def update_storage_usage(self, user_id: str, size_mb: int):
        import asyncio
        asyncio.get_event_loop().run_until_complete(
            self._async_service.update_storage_usage(user_id, size_mb)
        )
    
    def create_video_record(self, video_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        import asyncio
        return asyncio.get_event_loop().run_until_complete(
            self._async_service.create_video_record(video_data)
        )
    
    def update_video_status(
        self, 
        video_id: str, 
        status: str, 
        progress: Optional[int] = None,
        error_message: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        import asyncio
        return asyncio.get_event_loop().run_until_complete(
            self._async_service.update_video_status(video_id, status, progress, error_message)
        )
    
    def update_video_urls(
        self, 
        video_id: str, 
        oss_video_url: Optional[str] = None, 
        oss_audio_url: Optional[str] = None
    ):
        import asyncio
        asyncio.get_event_loop().run_until_complete(
            self._async_service.update_video_urls(video_id, oss_video_url, oss_audio_url)
        )
    
    def save_keyframes(self, video_id: str, keyframes: List[Any]) -> bool:
        import asyncio
        return asyncio.get_event_loop().run_until_complete(
            self._async_service.save_keyframes(video_id, keyframes)
        )
    
    def save_transcript_segments(self, video_id: str, segments: List[Any]) -> bool:
        import asyncio
        return asyncio.get_event_loop().run_until_complete(
            self._async_service.save_transcript_segments(video_id, segments)
        )
    
    def save_video_summary(
        self, 
        video_id: str, 
        summary_type: str, 
        content: str,
        model_used: str = "qwen3-vl-flash"
    ) -> bool:
        import asyncio
        return asyncio.get_event_loop().run_until_complete(
            self._async_service.save_video_summary(video_id, summary_type, content, model_used)
        )
    
    def get_video_by_id(self, video_id: str) -> Optional[Dict[str, Any]]:
        import asyncio
        return asyncio.get_event_loop().run_until_complete(
            self._async_service.get_video_by_id(video_id)
        )
    
    def get_user_videos(self, user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        import asyncio
        return asyncio.get_event_loop().run_until_complete(
            self._async_service.get_user_videos(user_id, limit)
        )
    
    def get_keyframes(self, video_id: str) -> List[Dict[str, Any]]:
        import asyncio
        return asyncio.get_event_loop().run_until_complete(
            self._async_service.get_keyframes(video_id)
        )
    
    def get_transcript_segments(self, video_id: str) -> List[Dict[str, Any]]:
        import asyncio
        return asyncio.get_event_loop().run_until_complete(
            self._async_service.get_transcript_segments(video_id)
        )
    
    def get_video_summaries(self, video_id: str) -> Dict[str, str]:
        import asyncio
        return asyncio.get_event_loop().run_until_complete(
            self._async_service.get_video_summaries(video_id)
        )
    
    def get_compiled_metadata(self, video_id: str) -> Optional[Dict[str, Any]]:
        import asyncio
        return asyncio.get_event_loop().run_until_complete(
            self._async_service.get_compiled_metadata(video_id)
        )

