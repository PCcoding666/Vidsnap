"""
Configuration management for the video analysis platform.
Handles environment variables and application settings.
"""
import os
from typing import Optional


class Settings:
    #阿里云访问密钥
    ALIYUN_ACCESS_KEY_ID: str = os.getenv("ALIYUN_ACCESS_KEY_ID", "")
    ALIYUN_ACCESS_KEY_SECRET: str = os.getenv("ALIYUN_ACCESS_KEY_SECRET", "")
    
    # OSS配置
    ALIYUN_OSS_ENDPOINT: str = os.getenv("ALIYUN_OSS_ENDPOINT", "")
    ALIYUN_OSS_BUCKET: str = os.getenv("ALIYUN_OSS_BUCKET", "")
    
    # OpenAI配置
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    
    # 应用配置
    TEMP_DIR: str = os.getenv("TEMP_DIR", "/tmp/video_analysis")
    
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
    def openai_available(self) -> bool:
        return bool(self.OPENAI_API_KEY)


# 创建配置实例
settings = Settings()