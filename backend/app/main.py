"""
Main application entry point.
"""
import os
import logging
import time
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from .core.logging import logger
from .api.routes import video, analysis, auth  # 添加 auth 路由

# 创建FastAPI应用
app = FastAPI(
    title="阿里云视频分析平台",
    description="支持视频处理、音频转录和内容分析的API服务",
    version="1.0.0"
)

# 添加请求日志中间件
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()

    # 记录请求开始
    logger.info(f"🔵 收到请求: {request.method} {request.url.path}")
    logger.info(f"   客户端: {request.client.host if request.client else 'Unknown'}")
    logger.info(f"   Headers: {dict(request.headers)}")

    # 处理请求
    response = await call_next(request)

    # 记录请求完成
    process_time = time.time() - start_time
    logger.info(f"✅ 请求完成: {request.method} {request.url.path} - 状态码: {response.status_code} - 耗时: {process_time:.2f}s")

    return response

# 添加CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 在生产环境中应该指定具体的域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 包含路由
app.include_router(auth.router)  # 认证路由(无需认证)
app.include_router(video.router)  # 视频路由(需要认证)
app.include_router(analysis.router)  # 分析路由

@app.get("/")
async def root():
    """Root endpoint."""
    return {"message": "阿里云视频分析平台API服务正在运行"}

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    
    # 从环境变量获取端口，默认为8000
    port = int(os.getenv("PORT", 8000))
    
    logger.info(f"启动服务器在端口 {port}")
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=True)