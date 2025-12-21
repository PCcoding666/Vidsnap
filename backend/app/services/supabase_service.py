"""
Supabase Service 兼容层
========================================
Supabase 已禁用，此模块作为兼容层代理到本地数据库

所有对 supabase_service 的调用都会被转发到本地 PostgreSQL
这样可以保持业务代码不变，同时使用本地数据库
"""
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
import uuid

from sqlalchemy import create_engine, text, select, update, delete
from sqlalchemy.orm import sessionmaker

logger = logging.getLogger(__name__)

# 全局同步引擎和会话工厂
_sync_engine = None
_sync_session_factory = None


def _get_sync_session():
    """获取同步数据库会话"""
    global _sync_engine, _sync_session_factory
    
    if _sync_engine is None:
        from app.core.config import settings
        sync_url = settings.DATABASE_URL.replace("+asyncpg", "").replace("postgresql+asyncpg", "postgresql")
        _sync_engine = create_engine(
            sync_url,
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,
            pool_recycle=3600
        )
        _sync_session_factory = sessionmaker(bind=_sync_engine)
    
    return _sync_session_factory()


def _get_models():
    """获取所有模型"""
    from app.models.database import (
        YouTubeSubscription, AutoAnalyzedVideo, Video, Profile, UserQuota,
        Keyframe, TranscriptSegment, VideoSummary, Transcript
    )
    return {
        "youtube_subscriptions": YouTubeSubscription,
        "auto_analyzed_videos": AutoAnalyzedVideo,
        "videos": Video,
        "profiles": Profile,
        "user_quotas": UserQuota,
        "keyframes": Keyframe,
        "transcript_segments": TranscriptSegment,
        "video_summaries": VideoSummary,
        "transcripts": Transcript,
    }


class SupabaseServiceProxy:
    """
    Supabase 服务代理类
    
    将所有调用转发到本地 PostgreSQL
    保持与原 SupabaseService 相同的接口
    """
    
    def __init__(self):
        """初始化"""
        self._available = True
        logger.info("⚠️ Supabase 已禁用，使用本地数据库代理")
    
    def is_available(self) -> bool:
        """检查数据库服务是否可用"""
        return self._available
    
    # ========================================================================
    # 兼容属性 - 模拟 Supabase 客户端
    # ========================================================================
    
    @property
    def admin_client(self):
        """模拟 admin_client 属性，返回链式调用代理"""
        return _AdminClientProxy()
    
    @property
    def anon_client(self):
        """模拟 anon_client 属性"""
        return self.admin_client
    
    # ========================================================================
    # 用户认证相关方法
    # ========================================================================
    
    def verify_token(self, token: str) -> Optional[Dict[str, Any]]:
        """验证 JWT Token"""
        from app.core.auth import verify_jwt_token
        return verify_jwt_token(token)
    
    def get_user_profile(self, user_id: str) -> Optional[Dict[str, Any]]:
        """获取用户资料"""
        try:
            with _get_sync_session() as session:
                models = _get_models()
                Profile = models["profiles"]
                result = session.execute(
                    select(Profile).where(Profile.id == user_id)
                )
                profile = result.scalar_one_or_none()
                if profile:
                    return _model_to_dict(profile)
                return None
        except Exception as e:
            logger.error(f"获取用户资料失败: {e}")
            return None
    
    # ========================================================================
    # 配额管理相关方法
    # ========================================================================
    
    def check_user_quota(self, user_id: str) -> bool:
        """检查用户配额"""
        # 如果 user_id 为空，直接返回 True（允许处理）
        if not user_id:
            logger.warning("⚠️ user_id 为空，跳过配额检查")
            return True
        
        try:
            # 确保 user_id 是有效的 UUID 字符串
            from uuid import UUID
            try:
                UUID(str(user_id))
            except ValueError:
                logger.warning(f"⚠️ user_id 格式无效: {user_id}，跳过配额检查")
                return True
            
            with _get_sync_session() as session:
                models = _get_models()
                UserQuota = models["user_quotas"]
                result = session.execute(
                    select(UserQuota).where(UserQuota.user_id == user_id)
                )
                quota = result.scalar_one_or_none()
                if quota:
                    # 使用正确的字段名：monthly_videos_used, monthly_video_limit
                    return quota.monthly_videos_used < quota.monthly_video_limit
                return True
        except Exception as e:
            logger.error(f"检查配额失败: {e}")
            return True
    
    def increment_video_usage(self, user_id: str):
        """递增视频使用次数"""
        try:
            with _get_sync_session() as session:
                models = _get_models()
                UserQuota = models["user_quotas"]
                result = session.execute(
                    select(UserQuota).where(UserQuota.user_id == user_id)
                )
                quota = result.scalar_one_or_none()
                if quota:
                    quota.monthly_videos_used += 1
                    quota.updated_at = datetime.now(timezone.utc)
                    session.commit()
        except Exception as e:
            logger.error(f"递增视频使用失败: {e}")
    
    def update_storage_usage(self, user_id: str, size_mb: int):
        """更新存储使用量"""
        try:
            with _get_sync_session() as session:
                models = _get_models()
                UserQuota = models["user_quotas"]
                result = session.execute(
                    select(UserQuota).where(UserQuota.user_id == user_id)
                )
                quota = result.scalar_one_or_none()
                if quota:
                    quota.storage_used_mb += size_mb
                    quota.updated_at = datetime.now(timezone.utc)
                    session.commit()
        except Exception as e:
            logger.error(f"更新存储使用失败: {e}")
    
    # ========================================================================
    # 视频记录管理
    # ========================================================================
    
    def create_video_record(self, video_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """创建或更新视频记录 (UPSERT)"""
        try:
            with _get_sync_session() as session:
                models = _get_models()
                Video = models["videos"]
                
                if "video_id" not in video_data:
                    video_data["video_id"] = str(uuid.uuid4())
                
                video_id = video_data["video_id"]
                
                # 检查是否已存在
                existing = session.execute(
                    select(Video).where(Video.video_id == video_id)
                ).scalar_one_or_none()
                
                if existing:
                    # 更新现有记录
                    for key, value in video_data.items():
                        if key not in ("video_id", "created_at") and hasattr(existing, key):
                            setattr(existing, key, value)
                    existing.updated_at = datetime.now(timezone.utc)
                    session.commit()
                    session.refresh(existing)
                    logger.info(f"✅ 更新视频记录: {video_id}")
                    return _model_to_dict(existing)
                else:
                    # 创建新记录
                    video_data["created_at"] = datetime.now(timezone.utc)
                    video_data["updated_at"] = datetime.now(timezone.utc)
                    video = Video(**video_data)
                    session.add(video)
                    session.commit()
                    session.refresh(video)
                    logger.info(f"✅ 创建视频记录: {video_id}")
                    return _model_to_dict(video)
        except Exception as e:
            logger.error(f"创建/更新视频记录失败: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def update_video_status(
        self, 
        video_id: str, 
        status: str, 
        progress: Optional[int] = None,
        error_message: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """更新视频处理状态"""
        try:
            with _get_sync_session() as session:
                models = _get_models()
                Video = models["videos"]
                result = session.execute(
                    select(Video).where(Video.video_id == video_id)
                )
                video = result.scalar_one_or_none()
                if video:
                    video.status = status
                    if progress is not None:
                        video.progress = progress
                    if error_message is not None:
                        video.error_message = error_message
                    video.updated_at = datetime.now(timezone.utc)
                    session.commit()
                    return _model_to_dict(video)
                return None
        except Exception as e:
            logger.error(f"更新视频状态失败: {e}")
            return None
    
    def update_video_urls(
        self, 
        video_id: str, 
        oss_video_url: Optional[str] = None, 
        oss_audio_url: Optional[str] = None
    ):
        """更新视频的 OSS URL"""
        try:
            with _get_sync_session() as session:
                models = _get_models()
                Video = models["videos"]
                result = session.execute(
                    select(Video).where(Video.video_id == video_id)
                )
                video = result.scalar_one_or_none()
                if video:
                    if oss_video_url:
                        video.oss_video_url = oss_video_url
                    if oss_audio_url:
                        video.oss_audio_url = oss_audio_url
                    video.updated_at = datetime.now(timezone.utc)
                    session.commit()
        except Exception as e:
            logger.error(f"更新视频URL失败: {e}")
    
    # ========================================================================
    # 批量数据保存
    # ========================================================================
    
    def save_keyframes(self, video_id: str, keyframes: List[Any]) -> bool:
        """批量保存关键帧数据"""
        try:
            with _get_sync_session() as session:
                models = _get_models()
                Keyframe = models["keyframes"]
                
                for kf in keyframes:
                    # 支持 dataclass 和 dict 两种格式
                    if hasattr(kf, '__dict__'):
                        kf_data = vars(kf) if hasattr(kf, '__dict__') else kf
                    else:
                        kf_data = kf
                    
                    keyframe = Keyframe(
                        video_id=video_id,
                        frame_id=kf_data.get("frame_id", 0),
                        timestamp=kf_data.get("timestamp", 0.0),
                        oss_image_url=kf_data.get("oss_image_url", ""),
                        scene_description=kf_data.get("scene_description")
                    )
                    session.add(keyframe)
                
                session.commit()
                logger.info(f"✅ 保存关键帧: {video_id}, 数量: {len(keyframes)}")
                return True
        except Exception as e:
            logger.error(f"保存关键帧失败: {e}")
            return False
    
    def save_transcript_segments(self, video_id: str, segments: List[Any]) -> bool:
        """批量保存转录段落"""
        try:
            with _get_sync_session() as session:
                models = _get_models()
                TranscriptSegment = models["transcript_segments"]
                Transcript = models["transcripts"]
                
                # 先创建或更新 transcripts 表记录
                existing = session.execute(
                    select(Transcript).where(Transcript.video_id == video_id)
                ).scalar_one_or_none()
                
                if not existing:
                    transcript_record = Transcript(
                        video_id=video_id,
                        language="zh-CN",
                        total_segments=len(segments)
                    )
                    session.add(transcript_record)
                else:
                    existing.total_segments = len(segments)
                
                # 保存转录段落
                for idx, seg in enumerate(segments):
                    # 支持 dataclass 和 dict 两种格式
                    if hasattr(seg, '__dict__'):
                        seg_data = vars(seg) if not isinstance(seg, dict) else seg
                    else:
                        seg_data = seg
                    
                    segment = TranscriptSegment(
                        video_id=video_id,
                        segment_index=idx,
                        text=seg_data.get("text", ""),
                        start_time=seg_data.get("start_time", seg_data.get("start", 0.0)),
                        end_time=seg_data.get("end_time", seg_data.get("end", 0.0)),
                        confidence=seg_data.get("confidence")
                    )
                    session.add(segment)
                
                session.commit()
                logger.info(f"✅ 保存转录段落: {video_id}, 数量: {len(segments)}")
                return True
        except Exception as e:
            logger.error(f"保存转录段落失败: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def save_video_summary(
        self, 
        video_id: str, 
        summary_type: str, 
        content: str,
        model_used: str = "qwen3-vl-flash"
    ) -> bool:
        """保存视频总结"""
        try:
            with _get_sync_session() as session:
                models = _get_models()
                VideoSummary = models["video_summaries"]
                
                # 检查是否已存在
                existing = session.execute(
                    select(VideoSummary).where(
                        VideoSummary.video_id == video_id,
                        VideoSummary.summary_type == summary_type
                    )
                ).scalar_one_or_none()
                
                if existing:
                    # 更新现有记录
                    existing.content = content
                    existing.model_used = model_used
                    existing.updated_at = datetime.now(timezone.utc)
                else:
                    # 创建新记录
                    summary = VideoSummary(
                        video_id=video_id,
                        summary_type=summary_type,
                        content=content,
                        model_used=model_used
                    )
                    session.add(summary)
                
                session.commit()
                logger.info(f"✅ 保存视频总结: {video_id}, 类型: {summary_type}")
                return True
        except Exception as e:
            logger.error(f"保存视频总结失败: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    # ========================================================================
    # 查询方法
    # ========================================================================
    
    def get_video_by_id(self, video_id: str) -> Optional[Dict[str, Any]]:
        """根据 ID 查询视频信息"""
        try:
            with _get_sync_session() as session:
                models = _get_models()
                Video = models["videos"]
                result = session.execute(
                    select(Video).where(Video.video_id == video_id)
                )
                video = result.scalar_one_or_none()
                if video:
                    return _model_to_dict(video)
                return None
        except Exception as e:
            logger.error(f"查询视频失败: {e}")
            return None
    
    def get_user_videos(self, user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """查询用户的视频列表"""
        try:
            with _get_sync_session() as session:
                models = _get_models()
                Video = models["videos"]
                result = session.execute(
                    select(Video).where(Video.user_id == user_id).limit(limit)
                )
                videos = result.scalars().all()
                return [_model_to_dict(v) for v in videos]
        except Exception as e:
            logger.error(f"查询用户视频失败: {e}")
            return []
    
    def get_keyframes(self, video_id: str) -> List[Dict[str, Any]]:
        """获取指定视频的关键帧列表"""
        try:
            with _get_sync_session() as session:
                models = _get_models()
                Keyframe = models["keyframes"]
                result = session.execute(
                    select(Keyframe).where(Keyframe.video_id == video_id).order_by(Keyframe.frame_id)
                )
                keyframes = result.scalars().all()
                return [_model_to_dict(k) for k in keyframes]
        except Exception as e:
            logger.error(f"获取关键帧失败: {e}")
            return []
    
    def get_transcript_segments(self, video_id: str) -> List[Dict[str, Any]]:
        """获取指定视频的转录段落列表"""
        try:
            with _get_sync_session() as session:
                models = _get_models()
                TranscriptSegment = models["transcript_segments"]
                result = session.execute(
                    select(TranscriptSegment).where(TranscriptSegment.video_id == video_id).order_by(TranscriptSegment.segment_index)
                )
                segments = result.scalars().all()
                return [_model_to_dict(s) for s in segments]
        except Exception as e:
            logger.error(f"获取转录段落失败: {e}")
            return []
    
    def get_video_summaries(self, video_id: str) -> Dict[str, str]:
        """获取指定视频的各粒度总结内容"""
        try:
            with _get_sync_session() as session:
                models = _get_models()
                VideoSummary = models["video_summaries"]
                result = session.execute(
                    select(VideoSummary).where(VideoSummary.video_id == video_id)
                )
                summaries = result.scalars().all()
                return {s.summary_type: s.content for s in summaries}
        except Exception as e:
            logger.error(f"获取视频总结失败: {e}")
            return {}
    
    def get_compiled_metadata(self, video_id: str) -> Optional[Dict[str, Any]]:
        """汇聚视频完整上下文"""
        try:
            # 获取视频信息
            video = self.get_video_by_id(video_id)
            if not video:
                return None
            
            # 获取关键帧
            keyframes = self.get_keyframes(video_id)
            
            # 获取转录段落
            segments = self.get_transcript_segments(video_id)
            
            # 获取转录元信息
            transcript_info = {}
            try:
                with _get_sync_session() as session:
                    models = _get_models()
                    Transcript = models["transcripts"]
                    result = session.execute(
                        select(Transcript).where(Transcript.video_id == video_id)
                    )
                    transcript = result.scalar_one_or_none()
                    if transcript:
                        transcript_info = {
                            "language": transcript.language,
                            "overall_confidence": transcript.overall_confidence,
                            "total_segments": transcript.total_segments
                        }
            except Exception as e:
                logger.warning(f"获取转录元信息失败: {e}")
            
            # 获取总结
            summaries = self.get_video_summaries(video_id)
            
            return {
                "video": {
                    "title": video.get("title", ""),
                    "duration": video.get("duration"),
                    "oss_video_url": video.get("oss_video_url", ""),
                    "original_url": video.get("original_url", ""),
                    "source_type": video.get("source_type", "")
                },
                "transcript": {
                    "oss_audio_url": video.get("oss_audio_url", ""),
                    "language": transcript_info.get("language", "zh-CN"),
                    "overall_confidence": transcript_info.get("overall_confidence"),
                    "segments": segments
                },
                "keyframes": keyframes,
                "summaries": summaries
            }
        except Exception as e:
            logger.error(f"获取编译元数据失败: {e}")
            import traceback
            traceback.print_exc()
            return None


class _AdminClientProxy:
    """
    模拟 Supabase admin_client 的链式调用
    支持 .table().select().eq().execute() 等调用链
    """
    
    def __init__(self):
        self._table_name = None
        self._operation = None
        self._columns = "*"
        self._filters = {}
        self._data = None
        self._order_by = None
        self._limit_val = None
        self._single = False
    
    def table(self, name: str):
        """选择表"""
        self._table_name = name
        return self
    
    def select(self, columns: str = "*"):
        """SELECT 操作"""
        self._operation = "select"
        self._columns = columns
        return self
    
    def insert(self, data: Dict[str, Any]):
        """INSERT 操作"""
        self._operation = "insert"
        self._data = data.copy()
        return self
    
    def update(self, data: Dict[str, Any]):
        """UPDATE 操作"""
        self._operation = "update"
        self._data = data.copy()
        return self
    
    def upsert(self, data: Dict[str, Any]):
        """UPSERT 操作"""
        self._operation = "upsert"
        self._data = data.copy()
        return self
    
    def delete(self):
        """DELETE 操作"""
        self._operation = "delete"
        return self
    
    def eq(self, column: str, value: Any):
        """等于条件"""
        self._filters[column] = ("eq", value)
        return self
    
    def neq(self, column: str, value: Any):
        """不等于条件"""
        self._filters[column] = ("neq", value)
        return self
    
    def in_(self, column: str, values: List[Any]):
        """IN 条件"""
        self._filters[column] = ("in", values)
        return self
    
    def gte(self, column: str, value: Any):
        """大于等于条件"""
        self._filters[column] = ("gte", value)
        return self
    
    def lte(self, column: str, value: Any):
        """小于等于条件"""
        self._filters[column] = ("lte", value)
        return self
    
    def gt(self, column: str, value: Any):
        """大于条件"""
        self._filters[column] = ("gt", value)
        return self
    
    def lt(self, column: str, value: Any):
        """小于条件"""
        self._filters[column] = ("lt", value)
        return self
    
    def order(self, column: str, desc: bool = False):
        """排序"""
        self._order_by = (column, desc)
        return self
    
    def limit(self, count: int):
        """限制数量"""
        self._limit_val = count
        return self
    
    def single(self):
        """返回单条记录"""
        self._single = True
        return self
    
    def execute(self):
        """执行查询"""
        try:
            result = self._execute_sync()
            return _MockResponse(result)
        except Exception as e:
            logger.error(f"数据库操作失败: {self._table_name}.{self._operation}: {e}")
            return _MockResponse([])
    
    def _execute_sync(self):
        """同步执行数据库操作"""
        models = _get_models()
        model = models.get(self._table_name)
        
        if not model:
            logger.warning(f"未知表名: {self._table_name}")
            return []
        
        with _get_sync_session() as session:
            try:
                if self._operation == "select":
                    return self._do_select(session, model)
                elif self._operation == "insert":
                    return self._do_insert(session, model)
                elif self._operation == "update":
                    return self._do_update(session, model)
                elif self._operation == "delete":
                    return self._do_delete(session, model)
                elif self._operation == "upsert":
                    return self._do_upsert(session, model)
            except Exception as e:
                session.rollback()
                raise
        
        return []
    
    def _apply_filters(self, stmt, model):
        """应用过滤条件"""
        for col, (op, val) in self._filters.items():
            # 处理关联查询的过滤条件（如 youtube_subscriptions.user_id）
            if "." in col:
                # 忽略关联表的过滤条件，在 select 中单独处理
                continue
            
            if hasattr(model, col):
                column = getattr(model, col)
                if op == "eq":
                    stmt = stmt.where(column == val)
                elif op == "neq":
                    stmt = stmt.where(column != val)
                elif op == "in":
                    stmt = stmt.where(column.in_(val))
                elif op == "gte":
                    stmt = stmt.where(column >= val)
                elif op == "lte":
                    stmt = stmt.where(column <= val)
                elif op == "gt":
                    stmt = stmt.where(column > val)
                elif op == "lt":
                    stmt = stmt.where(column < val)
        return stmt
    
    def _do_select(self, session, model):
        """执行 SELECT"""
        # 检查是否是关联查询
        if "!" in self._columns or "youtube_subscriptions" in self._columns:
            return self._do_select_with_join(session, model)
        
        stmt = select(model)
        stmt = self._apply_filters(stmt, model)
        
        if self._order_by:
            col_name, desc = self._order_by
            if hasattr(model, col_name):
                order_col = getattr(model, col_name)
                stmt = stmt.order_by(order_col.desc() if desc else order_col)
        
        if self._limit_val:
            stmt = stmt.limit(self._limit_val)
        
        result = session.execute(stmt)
        rows = result.scalars().all()
        return [_model_to_dict(r) for r in rows]
    
    def _do_select_with_join(self, session, model):
        """执行带关联的 SELECT"""
        models = _get_models()
        YouTubeSubscription = models["youtube_subscriptions"]
        AutoAnalyzedVideo = models["auto_analyzed_videos"]
        
        if self._table_name == "auto_analyzed_videos":
            # 构建带 JOIN 的查询
            stmt = select(
                AutoAnalyzedVideo,
                YouTubeSubscription.channel_id,
                YouTubeSubscription.channel_name,
                YouTubeSubscription.channel_avatar,
                YouTubeSubscription.user_id.label("sub_user_id")
            ).join(
                YouTubeSubscription,
                AutoAnalyzedVideo.subscription_id == YouTubeSubscription.id
            )
            
            # 应用过滤条件
            for col, (op, val) in self._filters.items():
                if col == "youtube_subscriptions.user_id":
                    if op == "eq":
                        stmt = stmt.where(YouTubeSubscription.user_id == val)
                elif col == "youtube_subscriptions.is_active":
                    if op == "eq":
                        stmt = stmt.where(YouTubeSubscription.is_active == val)
                elif col == "analysis_status":
                    if op == "eq":
                        stmt = stmt.where(AutoAnalyzedVideo.analysis_status == val)
                elif hasattr(AutoAnalyzedVideo, col):
                    column = getattr(AutoAnalyzedVideo, col)
                    if op == "eq":
                        stmt = stmt.where(column == val)
            
            if self._order_by:
                col_name, desc = self._order_by
                if hasattr(AutoAnalyzedVideo, col_name):
                    order_col = getattr(AutoAnalyzedVideo, col_name)
                    stmt = stmt.order_by(order_col.desc() if desc else order_col)
            
            if self._limit_val:
                stmt = stmt.limit(self._limit_val)
            
            result = session.execute(stmt)
            rows = result.all()
            
            results = []
            for row in rows:
                video = row[0]
                item = _model_to_dict(video)
                item["channel_id"] = row.channel_id
                item["channel_name"] = row.channel_name
                item["channel_avatar"] = row.channel_avatar
                # 添加嵌套的 youtube_subscriptions 对象
                item["youtube_subscriptions"] = {
                    "channel_id": row.channel_id,
                    "channel_name": row.channel_name,
                    "channel_avatar": row.channel_avatar,
                    "user_id": str(row.sub_user_id) if row.sub_user_id else None
                }
                results.append(item)
            
            return results
        
        return []
    
    def _do_insert(self, session, model):
        """执行 INSERT"""
        if "id" not in self._data:
            self._data["id"] = str(uuid.uuid4())
        if "created_at" not in self._data:
            self._data["created_at"] = datetime.now(timezone.utc)
        if "updated_at" not in self._data:
            self._data["updated_at"] = datetime.now(timezone.utc)
        
        obj = model(**self._data)
        session.add(obj)
        session.commit()
        session.refresh(obj)
        return [_model_to_dict(obj)]
    
    def _do_update(self, session, model):
        """执行 UPDATE"""
        if not self._filters:
            logger.warning("UPDATE 操作缺少过滤条件")
            return []
        
        self._data["updated_at"] = datetime.now(timezone.utc)
        
        stmt = select(model)
        stmt = self._apply_filters(stmt, model)
        result = session.execute(stmt)
        rows = result.scalars().all()
        
        for row in rows:
            for key, val in self._data.items():
                if hasattr(row, key):
                    setattr(row, key, val)
        session.commit()
        return [_model_to_dict(r) for r in rows]
    
    def _do_delete(self, session, model):
        """执行 DELETE"""
        if not self._filters:
            logger.warning("DELETE 操作缺少过滤条件")
            return []
        
        stmt = delete(model)
        for col, (op, val) in self._filters.items():
            if "." in col:
                continue
            if hasattr(model, col):
                column = getattr(model, col)
                if op == "eq":
                    stmt = stmt.where(column == val)
        
        session.execute(stmt)
        session.commit()
        return []
    
    def _do_upsert(self, session, model):
        """执行 UPSERT"""
        stmt = select(model)
        stmt = self._apply_filters(stmt, model)
        result = session.execute(stmt)
        existing = result.scalar_one_or_none()
        
        if existing:
            for key, val in self._data.items():
                if hasattr(existing, key):
                    setattr(existing, key, val)
            existing.updated_at = datetime.now(timezone.utc)
            session.commit()
            return [_model_to_dict(existing)]
        else:
            if "id" not in self._data:
                self._data["id"] = str(uuid.uuid4())
            self._data["created_at"] = datetime.now(timezone.utc)
            self._data["updated_at"] = datetime.now(timezone.utc)
            obj = model(**self._data)
            session.add(obj)
            session.commit()
            session.refresh(obj)
            return [_model_to_dict(obj)]
    
    def rpc(self, function_name: str, params: Dict[str, Any] = None):
        """调用数据库函数"""
        try:
            result = self._execute_rpc(function_name, params or {})
            return _MockResponse(result)
        except Exception as e:
            logger.error(f"RPC 调用失败: {function_name}: {e}")
            return _MockResponse([])
    
    def _execute_rpc(self, function_name: str, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        """执行数据库函数"""
        with _get_sync_session() as session:
            if function_name == "get_subscriptions_to_check":
                limit = params.get("p_limit", 100)
                result = session.execute(
                    text("SELECT * FROM get_subscriptions_to_check(:limit)"),
                    {"limit": limit}
                )
                rows = result.fetchall()
                columns = result.keys()
                return [dict(zip(columns, row)) for row in rows]
            
            elif function_name == "get_user_subscription_stats":
                user_id = params.get("p_user_id")
                result = session.execute(
                    text("""
                        SELECT 
                            (SELECT COUNT(*) FROM youtube_subscriptions WHERE user_id = :user_id) as total_subscriptions,
                            (SELECT COUNT(*) FROM youtube_subscriptions WHERE user_id = :user_id AND is_active = true) as active_subscriptions,
                            (SELECT COUNT(*) FROM auto_analyzed_videos aav 
                             JOIN youtube_subscriptions ys ON aav.subscription_id = ys.id 
                             WHERE ys.user_id = :user_id) as total_analyzed_videos,
                            (SELECT COUNT(*) FROM auto_analyzed_videos aav 
                             JOIN youtube_subscriptions ys ON aav.subscription_id = ys.id 
                             WHERE ys.user_id = :user_id AND aav.analysis_status = 'pending') as pending_videos,
                            (SELECT COUNT(*) FROM auto_analyzed_videos aav 
                             JOIN youtube_subscriptions ys ON aav.subscription_id = ys.id 
                             WHERE ys.user_id = :user_id AND aav.analysis_status = 'failed') as failed_videos
                    """),
                    {"user_id": user_id}
                )
                row = result.fetchone()
                if row:
                    columns = result.keys()
                    return [dict(zip(columns, row))]
                return []
            
            else:
                logger.warning(f"未实现的 RPC 函数: {function_name}")
                return []


def _model_to_dict(obj) -> Dict[str, Any]:
    """将 SQLAlchemy 模型转换为字典"""
    result = {}
    for column in obj.__table__.columns:
        val = getattr(obj, column.name)
        if hasattr(val, 'isoformat'):
            val = val.isoformat()
        elif hasattr(val, '__str__') and type(val).__name__ == 'UUID':
            val = str(val)
        result[column.name] = val
    return result


class _MockResponse:
    """模拟 Supabase 响应对象"""
    
    def __init__(self, data):
        self.data = data if data is not None else []
    
    def execute(self):
        return self


# 创建全局实例
supabase_service = SupabaseServiceProxy()
