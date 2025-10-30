"""
Configuration management for the video analysis platform.
Handles environment variables and application settings.
"""
import os
from typing import Optional
from pathlib import Path
from dotenv import load_dotenv

# 加载环境变量，优先从项目根目录的 .env 文件读取
# 项目根目录 = backend的父目录
project_root = Path(__file__).parent.parent.parent
env_file = project_root / ".env"
if env_file.exists():
    load_dotenv(env_file)
    print(f"✅ 已加载环境变量文件: {env_file}")
else:
    # 回退到 backend/.env
    backend_env = project_root / "backend" / ".env"
    if backend_env.exists():
        load_dotenv(backend_env)
        print(f"✅ 已加载环境变量文件: {backend_env}")
    else:
        print("⚠️ 未找到 .env 文件，将使用系统环境变量")


class Settings:
    # 阿里云访问密钥
    ALIYUN_ACCESS_KEY_ID: str = os.getenv("ALIYUN_ACCESS_KEY_ID", "")
    ALIYUN_ACCESS_KEY_SECRET: str = os.getenv("ALIYUN_ACCESS_KEY_SECRET", "")
    
    # OSS配置
    ALIYUN_OSS_ENDPOINT: str = os.getenv("ALIYUN_OSS_ENDPOINT", "")
    ALIYUN_OSS_BUCKET: str = os.getenv("ALIYUN_OSS_BUCKET", "")
    
    # DashScope配置 (使用 QWEN_API_KEY)
    QWEN_API_KEY: str = os.getenv("QWEN_API_KEY", "")
    
    # 音频转录服务 API Key（优先级最高）
    TRANSCRIPT_SERVICE_API_KEY: str = os.getenv("TRANSCRIPT_SERVICE_API_KEY", "")
    
    # Supabase 配置
    # ⚠️ 安全警告: SUPABASE_SERVICE_KEY 拥有绕过 RLS 的完全数据库访问权限
    # 仅在后端服务器环境使用,严禁暴露给前端或客户端
    # 应通过环境变量注入,禁止硬编码到代码中
    SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
    SUPABASE_ANON_KEY: str = os.getenv("SUPABASE_ANON_KEY", "")
    SUPABASE_SERVICE_KEY: str = os.getenv("SUPABASE_SERVICE_KEY", "")
    
    # 应用配置
    TEMP_DIR: str = os.getenv("TEMP_DIR", "/tmp/video_analysis")
    
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
        return all([
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
        """检查 Supabase 配置是否完整"""
        return all([
            self.SUPABASE_URL,
            self.SUPABASE_ANON_KEY,
            self.SUPABASE_SERVICE_KEY
        ])


# 创建配置实例
settings = Settings()