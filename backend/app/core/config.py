"""
Configuration management for the video analysis platform.
Handles environment variables and application settings.
"""
import os
from typing import Optional


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


# 创建配置实例
settings = Settings()