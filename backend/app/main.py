from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
import logging
import os
from dotenv import load_dotenv
import sys

# 在最开始就加载环境变量
load_dotenv(dotenv_path=".env", verbose=True)

# 打印环境变量值以便调试
print(f"环境变量加载状态:")
print(f"QWEN_API_KEY 存在: {'是' if os.getenv('QWEN_API_KEY') else '否'}")
print(f"QWEN_API_BASE: {os.getenv('QWEN_API_BASE', '未设置')}")
print(f"QWEN_MODEL: {os.getenv('QWEN_MODEL', '未设置')}")
print(f"OPENAI_API_KEY 存在: {'是' if os.getenv('OPENAI_API_KEY') else '否'}")
print(f"HF_TOKEN 存在: {'是' if os.getenv('HF_TOKEN') else '否'}")
print(f"SECRET_KEY 存在: {'是' if os.getenv('SECRET_KEY') else '否'}")
print(f"STORAGE_DIR: {os.getenv('STORAGE_DIR', '未设置')}")
print(f"当前工作目录: {os.getcwd()}")

from app.core.config import settings
from app.api.api_v1.api import api_router

# 配置日志
log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
logging.basicConfig(level=log_level)
logger = logging.getLogger(__name__)

# 记录生效的日志级别
logger.info(f"日志级别设置为: {settings.LOG_LEVEL}")

# 创建FastAPI应用
app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json"
)

# 配置CORS
if settings.BACKEND_CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[str(origin) for origin in settings.BACKEND_CORS_ORIGINS],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# 配置异常处理
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request, exc):
    """处理HTTP异常"""
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc):
    """处理请求验证异常"""
    return JSONResponse(
        status_code=422,
        content={"detail": str(exc)},
    )

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """处理全局异常"""
    logger.error(f"未处理的异常: {str(exc)}")
    return JSONResponse(
        status_code=500,
        content={"detail": "服务器内部错误"},
    )

# 添加API路由
app.include_router(api_router, prefix=settings.API_V1_STR)

# 健康检查端点
@app.get("/health")
async def health_check():
    """健康检查"""
    return {"status": "ok"} 