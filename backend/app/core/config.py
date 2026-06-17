"""
Configuration management for the video analysis platform.
Handles environment variables and application settings.

本地数据库模式 - Supabase 已禁用
"""
import os
from typing import Optional
from pathlib import Path
from dotenv import load_dotenv

# 加载环境变量：项目根目录 .env 优先，backend/.env 作为兼容补充。
backend_dir = Path(__file__).resolve().parents[2]
project_root = backend_dir.parent
env_files = [project_root / ".env", backend_dir / ".env"]
loaded_env_files = []

for env_file in env_files:
    if env_file.exists():
        load_dotenv(env_file, override=False)
        loaded_env_files.append(env_file)

if loaded_env_files:
    print(f"✅ 已加载环境变量文件: {', '.join(str(path) for path in loaded_env_files)}")
else:
    print("⚠️ 未找到 .env 文件，将使用系统环境变量")


class Settings:
    # 阿里云访问密钥
    ALIYUN_ACCESS_KEY_ID: str = os.getenv("ALIYUN_ACCESS_KEY_ID", "")
    ALIYUN_ACCESS_KEY_SECRET: str = os.getenv("ALIYUN_ACCESS_KEY_SECRET", "")
    
    # OSS配置
    ALIYUN_OSS_ENDPOINT: str = os.getenv("ALIYUN_OSS_ENDPOINT", "")
    ALIYUN_OSS_BUCKET: str = os.getenv("ALIYUN_OSS_BUCKET", "")
    ENABLE_OSS_UPLOADS: bool = os.getenv("ENABLE_OSS_UPLOADS", "false").lower() in {"1", "true", "yes", "on"}
    OSS_USE_SIGNED_URLS: bool = os.getenv("OSS_USE_SIGNED_URLS", "true").lower() in {"1", "true", "yes", "on"}
    OSS_SIGNED_URL_EXPIRES_SECONDS: int = int(os.getenv("OSS_SIGNED_URL_EXPIRES_SECONDS", str(24 * 60 * 60)))
    
    # DashScope配置 (使用 QWEN_API_KEY)
    QWEN_API_KEY: str = os.getenv("QWEN_API_KEY", "")

    # 各环节使用的模型 ID（集中配置，便于切换）
    # 注意：必须是 DashScope 支持的有效模型 ID，否则对应环节会失败
    LLM_SUMMARY_MODEL: str = os.getenv("LLM_SUMMARY_MODEL", "qwen3.7-max")         # 摘要生成
    LLM_FRAME_SELECT_MODEL: str = os.getenv("LLM_FRAME_SELECT_MODEL", "qwen3.7-max")  # 模型选帧
    ASR_MODEL: str = os.getenv("ASR_MODEL", "fun-asr")                             # 语音转录（DashScope FunASR）
    
    # 音频转录服务 API Key（优先级最高）
    TRANSCRIPT_SERVICE_API_KEY: str = os.getenv("TRANSCRIPT_SERVICE_API_KEY", "")
    PARAFORMER_TRANSCRIPTION_SUBMIT_RETRIES: int = int(os.getenv("PARAFORMER_TRANSCRIPTION_SUBMIT_RETRIES", "3"))
    PARAFORMER_TRANSCRIPTION_FETCH_RETRIES: int = int(os.getenv("PARAFORMER_TRANSCRIPTION_FETCH_RETRIES", "5"))
    PARAFORMER_TRANSCRIPTION_RETRY_BASE_SECONDS: float = float(os.getenv("PARAFORMER_TRANSCRIPTION_RETRY_BASE_SECONDS", "2"))
    PARAFORMER_MAX_WAIT_SECONDS: int = int(os.getenv("PARAFORMER_MAX_WAIT_SECONDS", "1800"))
    PARAFORMER_POLL_INTERVAL_SECONDS: int = int(os.getenv("PARAFORMER_POLL_INTERVAL_SECONDS", "5"))
    DASHSCOPE_HTTP_BASE_URL: str = os.getenv("DASHSCOPE_HTTP_BASE_URL", "").rstrip("/")
    PARAFORMER_AUDIO_FORMAT: str = os.getenv("PARAFORMER_AUDIO_FORMAT", "flac").lower()
    PARAFORMER_CHUNK_SECONDS: int = int(os.getenv("PARAFORMER_CHUNK_SECONDS", "1800"))
    PARAFORMER_MAX_PARALLEL_CHUNKS: int = int(os.getenv("PARAFORMER_MAX_PARALLEL_CHUNKS", "2"))
    LOCAL_ASR_ENABLED: bool = os.getenv("LOCAL_ASR_ENABLED", "false").lower() in {"1", "true", "yes", "on"}
    
    # ============================================
    # Supabase 配置 - 已禁用
    # ============================================
    # SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
    # SUPABASE_ANON_KEY: str = os.getenv("SUPABASE_ANON_KEY", "")
    # SUPABASE_SERVICE_KEY: str = os.getenv("SUPABASE_SERVICE_KEY", "")
    SUPABASE_URL: str = ""
    SUPABASE_ANON_KEY: str = ""
    SUPABASE_SERVICE_KEY: str = ""
    
    # 本地 PostgreSQL 数据库配置
    # 格式: postgresql+asyncpg://user:password@host:port/database
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL", 
        "postgresql+asyncpg://vidsnap:vidsnap_secret_2024@localhost:5432/vidsnap"
    )
    
    # JWT 认证配置
    JWT_SECRET: str = os.getenv("JWT_SECRET", "your-super-secret-jwt-key-change-in-production")
    JWT_LIFETIME_SECONDS: int = int(os.getenv("JWT_LIFETIME_SECONDS", str(3600 * 24 * 7)))  # 7天
    
    # Google OAuth 配置
    GOOGLE_OAUTH_CLIENT_ID: str = os.getenv("GOOGLE_OAUTH_CLIENT_ID", "")
    GOOGLE_OAUTH_CLIENT_SECRET: str = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", "")
    
    # 数据库模式 - 强制使用本地数据库
    # DATABASE_MODE: str = os.getenv("DATABASE_MODE", "local")
    DATABASE_MODE: str = "local"  # Supabase 已禁用，强制使用本地
    
    # 应用配置
    TEMP_DIR: str = os.getenv("TEMP_DIR", "/tmp/video_analysis")
    MAX_UPLOAD_BYTES: int = int(os.getenv("MAX_UPLOAD_BYTES", str(500 * 1024 * 1024)))
    MAX_MEDIA_DURATION_SECONDS: int = int(os.getenv("MAX_MEDIA_DURATION_SECONDS", str(4 * 3600)))
    MAX_CONCURRENT_WORKSPACE_JOBS: int = int(os.getenv("MAX_CONCURRENT_WORKSPACE_JOBS", "2"))

    # 产物/帧存储目录（截帧 JPEG 落盘于 STORAGE_DIR/frames/{video_id}/）
    STORAGE_DIR: str = os.getenv("STORAGE_DIR", "./storage")
    # ExtractFrames：当 plan 含 ExtractFrames 步骤时，由模型在转录时间轴上挑选关键时间点截帧
    WORKSPACE_FRAMES_ENABLED: bool = os.getenv("WORKSPACE_FRAMES_ENABLED", "true").lower() == "true"
    MAX_FRAMES_PER_NOTE: int = int(os.getenv("MAX_FRAMES_PER_NOTE", "4"))

    # Gmail SMTP 配置
    # 用于发送邮件通知给用户
    GMAIL_SMTP_USER: str = os.getenv("GMAIL_SMTP_USER", "")
    GMAIL_SMTP_PASSWORD: str = os.getenv("GMAIL_SMTP_PASSWORD", "")  # 使用 App Password
    GMAIL_SMTP_HOST: str = os.getenv("GMAIL_SMTP_HOST", "smtp.gmail.com")
    GMAIL_SMTP_PORT: int = int(os.getenv("GMAIL_SMTP_PORT", "587"))
    GMAIL_SMTP_FROM: str = os.getenv("GMAIL_SMTP_FROM", "")  # 发送者名称，如 "VidSnap <noreply@vidsnap.space>"
    
    # 应用 URL（用于邮件中的链接）
    APP_URL: str = os.getenv("APP_URL", "https://vidsnap.space")
    
    @property
    def DASHSCOPE_API_KEY(self) -> str:
        """
        将 QWEN_API_KEY 映射到 DASHSCOPE_API_KEY，以保持 SDK 兼容性
        优先级: TRANSCRIPT_SERVICE_API_KEY > QWEN_API_KEY > 原始 DASHSCOPE_API_KEY
        """
        return (
            self.TRANSCRIPT_SERVICE_API_KEY or 
            self.QWEN_API_KEY or 
            os.getenv("DASHSCOPE_API_KEY", "")
        )
    
    # 服务可用性检查
    @property
    def oss_available(self) -> bool:
        return self.ENABLE_OSS_UPLOADS and all([
            self.ALIYUN_ACCESS_KEY_ID,
            self.ALIYUN_ACCESS_KEY_SECRET,
            self.ALIYUN_OSS_ENDPOINT,
            self.ALIYUN_OSS_BUCKET
        ])
    
    @property
    def dashscope_available(self) -> bool:
        return bool(self.QWEN_API_KEY)
    
    @property
    def supabase_available(self) -> bool:
        """检查 Supabase 配置是否完整 - 已禁用，始终返回 False"""
        # ============================================
        # Supabase 已禁用
        # ============================================
        # return all([
        #     self.SUPABASE_URL,
        #     self.SUPABASE_ANON_KEY,
        #     self.SUPABASE_SERVICE_KEY
        # ])
        return False
    
    @property
    def local_db_available(self) -> bool:
        """检查本地数据库配置是否完整"""
        return bool(self.DATABASE_URL)
    
    @property
    def google_oauth_available(self) -> bool:
        """检查 Google OAuth 配置是否完整"""
        return all([
            self.GOOGLE_OAUTH_CLIENT_ID,
            self.GOOGLE_OAUTH_CLIENT_SECRET
        ])
    
    @property
    def use_local_database(self) -> bool:
        """是否使用本地数据库 - 强制使用本地"""
        # return self.DATABASE_MODE == "local" and self.local_db_available
        return True  # Supabase 已禁用，强制使用本地数据库
    
    @property
    def email_available(self) -> bool:
        """检查邮件服务配置是否完整"""
        return all([
            self.GMAIL_SMTP_USER,
            self.GMAIL_SMTP_PASSWORD
        ])


# 创建配置实例
settings = Settings()
