import os
import sys
from dotenv import load_dotenv
from pydantic_settings import BaseSettings
from typing import Optional, List, ClassVar, Dict, Any
from pathlib import Path
import logging

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 尝试多个可能的.env文件路径
possible_env_paths = [
    ".env",
    "../.env",
    "../../.env",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "../..", ".env"),
    os.path.join(os.getcwd(), ".env")
]

# 依次尝试加载不同路径的.env文件
env_loaded = False
for env_path in possible_env_paths:
    if os.path.exists(env_path):
        logger.info(f"找到并加载.env文件: {env_path}")
        load_dotenv(dotenv_path=env_path, verbose=True)
        env_loaded = True
        break

if not env_loaded:
    logger.warning("未找到.env文件，将使用默认环境变量")
    
# 打印环境变量调试信息
logger.info(f"config模块: 当前工作目录: {os.getcwd()}")
logger.info(f"config模块: QWEN_API_KEY 存在: {'是' if os.getenv('QWEN_API_KEY') else '否'}")
logger.info(f"config模块: OPENAI_API_KEY 存在: {'是' if os.getenv('OPENAI_API_KEY') else '否'}")
logger.info(f"config模块: HF_TOKEN 存在: {'是' if os.getenv('HF_TOKEN') else '否'}")

class Settings(BaseSettings):
    # 基本配置
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "YouTube视频摘要工具"
    
    # 安全配置
    SECRET_KEY: str = os.getenv("SECRET_KEY", "your-secret-key-for-jwt")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7天
    
    # 文件存储配置
    STORAGE_DIR: Path = Path(os.getenv("STORAGE_DIR", "./storage"))
    VIDEOS_DIR: Path = STORAGE_DIR / "videos"
    AUDIOS_DIR: Path = STORAGE_DIR / "audios"
    KEYFRAMES_DIR: Path = STORAGE_DIR / "keyframes"
    
    # API密钥配置
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    QWEN_API_KEY: str = os.getenv("QWEN_API_KEY", "")
    HF_TOKEN: str = os.getenv("HF_TOKEN", "")
    
    # 千问 API 配置
    QWEN_API_BASE: str = os.getenv("QWEN_API_BASE", "https://dashscope-intl.aliyuncs.com/compatible-mode/v1/chat/completions")
    QWEN_MODEL: str = os.getenv("QWEN_MODEL", "qwen-max")
    
    # Google Cloud Storage 配置
    GCS_BUCKET_NAME: str = os.getenv("GCS_BUCKET_NAME", "") # 从环境变量读取 GCS 存储桶名称
    GCS_CREDENTIALS_PATH: Optional[str] = os.getenv("GOOGLE_APPLICATION_CREDENTIALS") # 尝试从标准环境变量读取凭证路径
    
    # 日志配置
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    
    # 用户数据和摘要数据存储路径
    USERS_DATA_FILE: Path = STORAGE_DIR / "users.json"
    SUMMARIES_DATA_FILE: Path = STORAGE_DIR / "summaries.json"
    SUBSCRIPTIONS_DATA_FILE: Path = STORAGE_DIR / "subscriptions.json"
    
    # 订阅计划
    SUBSCRIPTION_PLANS: ClassVar[Dict[str, Dict[str, Any]]] = {
        "free": {
            "name": "免费版",
            "price": 0,
            "videos_per_month": 3,
            "features": ["基本摘要生成", "支持YouTube链接"]
        },
        "basic": {
            "name": "基础版",
            "price": 9.99,
            "videos_per_month": 20,
            "features": ["详细摘要生成", "支持YouTube链接", "说话人分离", "多种关键帧提取方法"]
        },
        "premium": {
            "name": "高级版",
            "price": 29.99,
            "videos_per_month": 100,
            "features": ["所有基础版功能", "优先处理", "无广告体验", "支持本地视频上传"]
        }
    }
    
    # CORS设置
    BACKEND_CORS_ORIGINS: List[str] = [
        "http://localhost",
        "http://localhost:3000",  # React默认端口
        "http://localhost:8000",  # FastAPI默认端口
    ]
    
    class Config:
        env_file = ".env"
        case_sensitive = True

settings = Settings()

# 确保所需目录存在
os.makedirs(settings.VIDEOS_DIR, exist_ok=True)
os.makedirs(settings.AUDIOS_DIR, exist_ok=True)
os.makedirs(settings.KEYFRAMES_DIR, exist_ok=True) 