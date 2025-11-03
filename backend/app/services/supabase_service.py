"""
Supabase Service - 用户认证和数据持久化服务
提供用户注册、登录、Token 验证、视频元数据存储等功能
"""
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
from dataclasses import asdict

try:
    from supabase import create_client, Client
    from supabase.lib.client_options import ClientOptions
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False
    Client = None

from app.core.config import settings

logger = logging.getLogger(__name__)


class SupabaseService:
    """Supabase 服务类"""
    
    def __init__(self):
        """初始化 Supabase 客户端"""
        self.anon_client: Optional[Client] = None
        self.admin_client: Optional[Client] = None
        
        if not SUPABASE_AVAILABLE:
            logger.warning("⚠️ Supabase 库未安装,相关功能不可用")
            return
        
        if not settings.supabase_available:
            logger.warning("⚠️ Supabase 配置不完整,跳过初始化")
            return
        
        try:
            # 创建匿名客户端(用于前端认证和用户数据访问)
            self.anon_client = create_client(
                settings.SUPABASE_URL,
                settings.SUPABASE_ANON_KEY
            )
            
            # 创建管理客户端(用于后端管理操作,绕过 RLS)
            options = ClientOptions(
                auto_refresh_token=False,
                persist_session=False
            )
            self.admin_client = create_client(
                settings.SUPABASE_URL,
                settings.SUPABASE_SERVICE_KEY,
                options
            )
            
            logger.info(f"✅ Supabase 服务初始化成功: {settings.SUPABASE_URL}")
        except Exception as e:
            logger.error(f"❌ Supabase 初始化失败: {e}")
    
    def is_available(self) -> bool:
        """检查 Supabase 服务是否可用"""
        return (
            SUPABASE_AVAILABLE and 
            settings.supabase_available and 
            self.anon_client is not None and 
            self.admin_client is not None
        )
    
    # ========================================================================
    # 用户认证相关方法
    # ========================================================================
    
    def sign_up_user(
        self, 
        email: str, 
        password: str, 
        username: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        用户注册
        
        Args:
            email: 用户邮箱
            password: 密码(明文,由 Supabase 加密)
            username: 用户名(可选,未提供则自动生成)
        
        Returns:
            {
                "user": {"id": "uuid", "email": "...", "username": "..."},
                "access_token": "...",
                "refresh_token": "..."
            }
        
        Raises:
            Exception: 邮箱已存在或其他错误
        """
        if not self.is_available():
            raise Exception("Supabase 服务不可用")
        
        try:
            # 使用管理员客户端创建用户(绕过邮箱验证)
            auth_response = self.admin_client.auth.admin.create_user({
                "email": email,
                "password": password,
                "email_confirm": True
            })
            
            user_id = auth_response.user.id
            logger.info(f"✅ 创建用户成功: {email} (ID: {user_id})")
            
            # 触发器会自动创建 profiles 和 user_quotas 记录
            # 如果需要自定义 username,更新 profiles
            if username:
                self.admin_client.table("profiles").update({
                    "username": username
                }).eq("id", user_id).execute()
            
            # 使用匿名客户端登录获取 Token
            sign_in_response = self.anon_client.auth.sign_in_with_password({
                "email": email,
                "password": password
            })
            
            # 查询用户资料
            profile = self.admin_client.table("profiles").select("*").eq("id", user_id).single().execute()
            
            return {
                "user": {
                    "id": user_id,
                    "email": email,
                    "username": profile.data.get("username"),
                    "subscription_tier": profile.data.get("subscription_tier", "free")
                },
                "access_token": sign_in_response.session.access_token,
                "refresh_token": sign_in_response.session.refresh_token
            }
        except Exception as e:
            error_msg = str(e)
            if "already been registered" in error_msg.lower() or "duplicate" in error_msg.lower():
                raise Exception("该邮箱已被注册")
            logger.error(f"❌ 用户注册失败: {e}")
            raise
    
    def sign_in_user(self, email: str, password: str) -> Dict[str, Any]:
        """
        用户登录
        
        Args:
            email: 用户邮箱
            password: 密码
        
        Returns:
            {
                "user": {...},
                "access_token": "...",
                "refresh_token": "..."
            }
        
        Raises:
            Exception: 认证失败
        """
        if not self.is_available():
            raise Exception("Supabase 服务不可用")
        
        try:
            # 使用匿名客户端登录
            response = self.anon_client.auth.sign_in_with_password({
                "email": email,
                "password": password
            })
            
            user_id = response.user.id
            
            # 查询用户资料
            profile = self.admin_client.table("profiles").select("*").eq("id", user_id).single().execute()
            
            return {
                "user": {
                    "id": user_id,
                    "email": email,
                    "username": profile.data.get("username"),
                    "subscription_tier": profile.data.get("subscription_tier", "free")
                },
                "access_token": response.session.access_token,
                "refresh_token": response.session.refresh_token
            }
        except Exception as e:
            logger.error(f"❌ 用户登录失败: {e}")
            raise Exception("邮箱或密码错误")
    
    def get_google_oauth_url(self, redirect_url: str) -> str:
        """
        获取 Google OAuth 登录 URL
        
        Args:
            redirect_url: OAuth 回调 URL (前端处理回调的地址)
        
        Returns:
            Google OAuth 登录链接
        """
        if not self.is_available():
            raise Exception("Supabase 服务不可用")
        
        try:
            # Supabase 会自动处理 OAuth 流程
            # 返回 OAuth URL 供前端使用
            data = self.anon_client.auth.sign_in_with_oauth({
                "provider": "google",
                "options": {
                    "redirect_to": redirect_url
                }
            })
            
            logger.info(f"✅ 生成 Google OAuth URL: {redirect_url}")
            return data.url
        except Exception as e:
            logger.error(f"❌ 生成 Google OAuth URL 失败: {e}")
            raise Exception(f"OAuth 初始化失败: {str(e)}")
    
    def exchange_oauth_code(self, code: str) -> Dict[str, Any]:
        """
        交换 OAuth 授权码获取用户信息和 Token
        
        Args:
            code: OAuth 授权码(从回调 URL 参数获取)
        
        Returns:
            {
                "user": {...},
                "access_token": "...",
                "refresh_token": "..."
            }
        """
        if not self.is_available():
            raise Exception("Supabase 服务不可用")
        
        try:
            # 使用授权码交换 session
            response = self.anon_client.auth.exchange_code_for_session(code)
            
            # 检查响应类型
            if not hasattr(response, 'user') or not hasattr(response, 'session'):
                logger.error(f"❌ OAuth 响应格式错误: {type(response)}, {response}")
                raise Exception(f"OAuth 响应格式错误: 期望对象包含 user 和 session 属性,实际收到: {type(response)}")
            
            if not response.user or not response.session:
                raise Exception("OAuth 认证失败: 用户信息或会话为空")
            
            user_id = response.user.id
            email = response.user.email
            
            # 查询或创建用户资料
            # Google OAuth 用户首次登录时,Supabase 会自动创建 auth.users 记录
            # 但需要确保 profiles 表也有对应记录(通过触发器自动创建)
            try:
                profile = self.admin_client.table("profiles").select("*").eq("id", user_id).single().execute()
            except Exception:
                # 如果 profile 不存在,手动创建(作为备用方案)
                username = email.split("@")[0]
                self.admin_client.table("profiles").insert({
                    "id": user_id,
                    "email": email,
                    "username": username,
                    "subscription_tier": "free"
                }).execute()
                profile = self.admin_client.table("profiles").select("*").eq("id", user_id).single().execute()
            
            logger.info(f"✅ Google OAuth 登录成功: {email}")
            
            return {
                "user": {
                    "id": user_id,
                    "email": email,
                    "username": profile.data.get("username"),
                    "subscription_tier": profile.data.get("subscription_tier", "free")
                },
                "access_token": response.session.access_token,
                "refresh_token": response.session.refresh_token
            }
        except Exception as e:
            logger.error(f"❌ OAuth 授权码交换失败: {e}")
            raise Exception(f"OAuth 认证失败: {str(e)}")
    
    def verify_token(self, token: str) -> Optional[Dict[str, Any]]:
        """
        验证 JWT Token
        
        Args:
            token: JWT Token
        
        Returns:
            {"id": "uuid", "email": "..."} 或 None(Token 无效)
        """
        if not self.is_available():
            return None
        
        try:
            response = self.anon_client.auth.get_user(token)
            return {
                "id": response.user.id,
                "email": response.user.email
            }
        except Exception as e:
            logger.warning(f"⚠️ Token 验证失败: {e}")
            return None
    
    def get_user_profile(self, user_id: str) -> Optional[Dict[str, Any]]:
        """获取用户资料"""
        if not self.is_available():
            return None
        
        try:
            response = self.admin_client.table("profiles").select("*").eq("id", user_id).single().execute()
            return response.data
        except Exception as e:
            logger.error(f"❌ 获取用户资料失败: {e}")
            return None
    
    # ========================================================================
    # 配额管理相关方法
    # ========================================================================
    
    def check_user_quota(self, user_id: str) -> bool:
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
            quota = self.admin_client.table("user_quotas").select("*").eq("user_id", user_id).single().execute()
            data = quota.data
            
            videos_ok = data["monthly_videos_used"] < data["monthly_video_limit"]
            storage_ok = data["used_storage_mb"] < data["total_storage_mb"]
            
            if not videos_ok:
                logger.warning(f"⚠️ 用户 {user_id} 已达视频处理上限")
            if not storage_ok:
                logger.warning(f"⚠️ 用户 {user_id} 存储空间已满")
            
            return videos_ok and storage_ok
        except Exception as e:
            logger.error(f"❌ 检查配额失败: {e}")
            return True  # 出错时不限制
    
    def increment_video_usage(self, user_id: str):
        """递增用户的视频使用次数"""
        if not self.is_available():
            return
        
        try:
            self.admin_client.rpc("increment_monthly_videos", {"p_user_id": user_id}).execute()
            logger.info(f"✅ 用户 {user_id} 视频使用次数 +1")
        except Exception as e:
            logger.error(f"❌ 递增视频使用次数失败: {e}")
    
    def update_storage_usage(self, user_id: str, size_mb: int):
        """更新用户的存储使用量"""
        if not self.is_available():
            return
        
        try:
            self.admin_client.rpc("update_storage_usage", {
                "p_user_id": user_id, 
                "p_size_mb": size_mb
            }).execute()
            logger.info(f"✅ 用户 {user_id} 存储使用量 +{size_mb}MB")
        except Exception as e:
            logger.error(f"❌ 更新存储使用量失败: {e}")
    
    # ========================================================================
    # 视频记录管理
    # ========================================================================
    
    def create_video_record(self, video_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
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
            response = self.admin_client.table("videos").insert(video_data).execute()
            logger.info(f"✅ 创建视频记录: {video_data.get('video_id')}")
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"❌ 创建视频记录失败: {e}")
            return None
    
    def update_video_status(
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
            update_data = {
                "processing_status": status,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
            
            if progress is not None:
                update_data["processing_progress"] = progress
            
            # 设置开始/完成时间
            if status == "processing":
                update_data["processing_started_at"] = datetime.now(timezone.utc).isoformat()
            elif status == "completed":
                update_data["processing_completed_at"] = datetime.now(timezone.utc).isoformat()
            elif status == "failed" and error_message:
                update_data["error_message"] = error_message
            
            response = self.admin_client.table("videos").update(update_data).eq("video_id", video_id).execute()
            logger.info(f"✅ 更新视频状态: {video_id} -> {status} ({progress}%)")
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"❌ 更新视频状态失败: {e}")
            return None
    
    def update_video_urls(self, video_id: str, oss_video_url: Optional[str] = None, oss_audio_url: Optional[str] = None):
        """更新视频的 OSS URL"""
        if not self.is_available():
            return
        
        try:
            update_data = {}
            if oss_video_url:
                update_data["oss_video_url"] = oss_video_url
            if oss_audio_url:
                update_data["oss_audio_url"] = oss_audio_url
            
            if update_data:
                self.admin_client.table("videos").update(update_data).eq("video_id", video_id).execute()
                logger.info(f"✅ 更新视频 URL: {video_id}")
        except Exception as e:
            logger.error(f"❌ 更新视频 URL 失败: {e}")
    
    # ========================================================================
    # 批量数据保存
    # ========================================================================
    
    def save_keyframes(self, video_id: str, keyframes: List[Any]) -> bool:
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
            # 转换为字典列表
            keyframes_data = []
            for kf in keyframes:
                kf_dict = asdict(kf) if hasattr(kf, '__dataclass_fields__') else kf
                keyframes_data.append({
                    "video_id": video_id,
                    "frame_id": kf_dict.get("frame_id"),
                    "timestamp": kf_dict.get("timestamp"),
                    "oss_image_url": kf_dict.get("oss_image_url"),
                    "scene_description": kf_dict.get("scene_description", "")
                })
            
            # 批量插入
            self.admin_client.table("keyframes").insert(keyframes_data).execute()
            logger.info(f"✅ 保存 {len(keyframes_data)} 个关键帧: {video_id}")
            return True
        except Exception as e:
            logger.error(f"❌ 保存关键帧失败: {e}")
            return False
    
    def save_transcript_segments(self, video_id: str, segments: List[Any]) -> bool:
        """
        批量保存转录段落
        
        Args:
            video_id: 视频 ID
            segments: TranscriptSegment 列表
        
        Returns:
            是否保存成功
        """
        if not self.is_available():
            logger.warning(f"[DEBUG] Supabase不可用，无法保存转录段落: {video_id}")
            return False
        
        try:
            logger.info(f"[DEBUG] 开始保存 {len(segments)} 个转录段落: {video_id}")
            
            # 转换为字典列表
            segments_data = []
            for i, seg in enumerate(segments):
                seg_dict = asdict(seg) if hasattr(seg, '__dataclass_fields__') else seg
                segments_data.append({
                    "video_id": video_id,
                    "segment_index": i,
                    "text": seg_dict.get("text"),
                    "start_time": seg_dict.get("start_time"),
                    "end_time": seg_dict.get("end_time"),
                    "confidence": seg_dict.get("confidence"),
                    "speaker_id": seg_dict.get("speaker_id")
                })
            
            logger.info(f"[DEBUG] 准备插入 {len(segments_data)} 条记录")
            
            # 批量插入
            result = self.admin_client.table("transcript_segments").insert(segments_data).execute()
            logger.info(f"[DEBUG] 插入结果: {bool(result.data)}")
            
            # 更新 transcripts 表的 total_segments
            self.admin_client.table("transcripts").upsert({
                "video_id": video_id,
                "total_segments": len(segments_data)
            }).execute()
            
            logger.info(f"✅ 保存 {len(segments_data)} 个转录段落: {video_id}")
            return True
        except Exception as e:
            logger.error(f"❌ 保存转录段落失败: {e}")
            logger.exception(e)
            return False
    
    def save_video_summary(
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
            self.admin_client.table("video_summaries").upsert({
                "video_id": video_id,
                "summary_type": summary_type,
                "content": content,
                "model_used": model_used
            }).execute()
            logger.info(f"✅ 保存视频总结: {video_id} ({summary_type})")
            return True
        except Exception as e:
            logger.error(f"❌ 保存视频总结失败: {e}")
            return False
    
    # ========================================================================
    # 查询方法
    # ========================================================================
    
    def get_video_by_id(self, video_id: str) -> Optional[Dict[str, Any]]:
        """根据 ID 查询视频信息"""
        if not self.is_available():
            return None
        
        try:
            response = self.admin_client.table("videos").select("*").eq("video_id", video_id).single().execute()
            return response.data
        except Exception as e:
            logger.error(f"❌ 查询视频失败: {e}")
            return None
    
    def get_user_videos(self, user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """查询用户的视频列表"""
        if not self.is_available():
            return []
        
        try:
            response = self.admin_client.table("videos").select("*").eq("user_id", user_id).order("created_at", desc=True).limit(limit).execute()
            return response.data
        except Exception as e:
            logger.error(f"❌ 查询用户视频列表失败: {e}")
            return []
    
    def get_keyframes(self, video_id: str) -> List[Dict[str, Any]]:
        """获取指定视频的关键帧列表"""
        if not self.is_available():
            return []
        try:
            res = self.admin_client.table("keyframes") \
                .select("frame_id,timestamp,oss_image_url,scene_description") \
                .eq("video_id", video_id) \
                .order("timestamp", desc=False) \
                .execute()
            return res.data or []
        except Exception as e:
            logger.error(f"❌ 获取关键帧失败: {e}")
            return []

    def get_transcript_segments(self, video_id: str) -> List[Dict[str, Any]]:
        """获取指定视频的转录段落列表"""
        if not self.is_available():
            return []
        try:
            res = self.admin_client.table("transcript_segments") \
                .select("segment_index,text,start_time,end_time,confidence") \
                .eq("video_id", video_id) \
                .order("segment_index", desc=False) \
                .execute()
            return res.data or []
        except Exception as e:
            logger.error(f"❌ 获取转录段落失败: {e}")
            return []
    
    def get_video_summaries(self, video_id: str) -> Dict[str, str]:
        """获取指定视频的各粒度总结内容"""
        if not self.is_available():
            return {}
        try:
            res = self.admin_client.table("video_summaries") \
                .select("summary_type,content") \
                .eq("video_id", video_id) \
                .execute()
            summaries = {}
            for row in res.data or []:
                summaries[row.get("summary_type")] = row.get("content") or ""
            return summaries
        except Exception as e:
            logger.error(f"❌ 获取视频总结失败: {e}")
            return {}

    def get_compiled_metadata(self, video_id: str) -> Optional[Dict[str, Any]]:
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
            logger.warning(f"[DEBUG] Supabase不可用，无法编译metadata: {video_id}")
            return None
        try:
            logger.info(f"[DEBUG] 开始编译视频上下文: {video_id}")
            video = self.get_video_by_id(video_id) or {}
            logger.info(f"[DEBUG] 获取video: {bool(video)}")
            
            keyframes = self.get_keyframes(video_id)
            logger.info(f"[DEBUG] 获取keyframes: {len(keyframes)}")
            
            segments = self.get_transcript_segments(video_id)
            logger.info(f"[DEBUG] 获取segments: {len(segments)} 个转录段")
            if segments:
                logger.info(f"[DEBUG] 第一个segment示例: {segments[0]}")
            
            summaries = self.get_video_summaries(video_id)
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


# 创建全局实例
supabase_service = SupabaseService()
