"""
Main application entry point.
本地数据库模式 - Supabase 已禁用
"""
import os
import logging
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from .core.logging import logger
from .core.config import settings
from .api.routes import video, analysis, auth, user, websocket


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时初始化
    logger.info("🚀 应用启动中...")
    
    # 初始化本地 PostgreSQL 数据库
    logger.info("📦 使用本地 PostgreSQL 数据库")
    try:
        from .services.database_service import database_service
        await database_service.initialize()
        logger.info("✅ 本地数据库初始化成功")
    except Exception as e:
        logger.error(f"❌ 本地数据库初始化失败: {e}")
        # 数据库初始化失败时继续运行，但某些功能可能不可用
    
    # ============================================
    # Supabase 初始化代码已禁用
    # ============================================
    # if settings.use_local_database:
    #     ...
    # else:
    #     logger.info("☁️ 使用 Supabase 云数据库")
    
    yield
    
    # 关闭时清理
    logger.info("👋 应用关闭中...")


# 创建FastAPI应用
app = FastAPI(
    title="VidSnap 视频分析平台",
    description="支持视频处理、音频转录和内容分析的API服务（本地数据库模式）",
    version="2.0.0",
    lifespan=lifespan
)

# 添加请求日志中间件（简洁版）
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    path = request.url.path
    method = request.method
    
    # 跳过健康检查等高频请求的日志
    skip_log = path in ["/health", "/", "/favicon.ico"]
    
    # 处理请求
    response = await call_next(request)
    
    # 只记录一行简洁日志
    if not skip_log:
        process_time = time.time() - start_time
        status_icon = "✅" if response.status_code < 400 else "❌"
        logger.info(f"{status_icon} {method} {path} → {response.status_code} ({process_time:.2f}s)")
    
    return response

# 添加CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 在生产环境中应该指定具体的域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API 路由前缀
API_PREFIX = "/api/v1"

# 包含路由 - 统一添加 /api/v1 前缀
app.include_router(auth.router, prefix=API_PREFIX)  # 认证路由
app.include_router(video.router, prefix=API_PREFIX)  # 视频路由
app.include_router(analysis.router, prefix=API_PREFIX)  # 分析路由
app.include_router(user.router, prefix=API_PREFIX)  # 用户路由

# WebSocket 路由
app.include_router(websocket.router, prefix=API_PREFIX)  # WebSocket 实时推送

# 注意：FastAPI-Users 路由已在 auth.router 中包含，无需重复注册

# ============================================
# Supabase 认证路由代码已禁用
# ============================================
# if settings.use_local_database:
#     try:
#         from .core.auth import get_auth_router
#         auth_router = get_auth_router()
#         app.include_router(auth_router, prefix=f"{API_PREFIX}/auth", tags=["auth"])
#         logger.info("✅ FastAPI-Users 认证路由已加载")
#     except Exception as e:
#         logger.warning(f"⚠️ FastAPI-Users 认证路由加载失败: {e}")


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "VidSnap 视频分析平台API服务正在运行",
        "version": "2.0.0",
        "database_mode": "本地 PostgreSQL"
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "database_mode": "local"
    }


if __name__ == "__main__":
    import uvicorn
    
    # 从环境变量获取端口，默认为8000
    port = int(os.getenv("PORT", 8000))
    
    logger.info(f"启动服务器在端口 {port}")
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=True)
