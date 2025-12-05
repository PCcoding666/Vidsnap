"""
Main application entry point.
"""
import os
import logging
import time
import psutil
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from collections import defaultdict
from datetime import datetime

from .core.logging import logger, get_context_logger

from .api.routes import video, analysis, auth  # 添加 auth 路由


# ==================== 性能分析数据收集 ====================
class PerformanceMonitor:
    """性能监控器 - 收集API性能指标"""
    
    def __init__(self):
        self.request_count = 0
        self.error_count = 0
        self.total_duration = 0
        self.endpoint_stats = defaultdict(lambda: {
            'count': 0,
            'total_time': 0,
            'min_time': float('inf'),
            'max_time': 0,
            'errors': 0
        })
        self.status_codes = defaultdict(int)
        self.start_time = datetime.now()
    
    def record_request(self, method: str, path: str, duration: float, status_code: int):
        """记录请求性能数据"""
        self.request_count += 1
        self.total_duration += duration
        
        # 记录端点统计
        endpoint_key = f"{method} {path}"
        stats = self.endpoint_stats[endpoint_key]
        stats['count'] += 1
        stats['total_time'] += duration
        stats['min_time'] = min(stats['min_time'], duration)
        stats['max_time'] = max(stats['max_time'], duration)
        
        if status_code >= 400:
            stats['errors'] += 1
            self.error_count += 1
        
        # 记录状态码
        self.status_codes[status_code] += 1
    
    def get_stats(self) -> dict:
        """获取统计数据"""
        uptime = (datetime.now() - self.start_time).total_seconds()
        avg_duration = self.total_duration / max(self.request_count, 1)
        
        # 计算每个端点的平均时间
        endpoint_summary = {}
        for endpoint, stats in self.endpoint_stats.items():
            endpoint_summary[endpoint] = {
                'count': stats['count'],
                'avg_time': stats['total_time'] / max(stats['count'], 1),
                'min_time': stats['min_time'] if stats['min_time'] != float('inf') else 0,
                'max_time': stats['max_time'],
                'error_rate': (stats['errors'] / max(stats['count'], 1)) * 100
            }
        
        return {
            'uptime_seconds': uptime,
            'total_requests': self.request_count,
            'total_errors': self.error_count,
            'error_rate': (self.error_count / max(self.request_count, 1)) * 100,
            'avg_response_time': avg_duration,
            'requests_per_second': self.request_count / max(uptime, 1),
            'status_codes': dict(self.status_codes),
            'endpoints': endpoint_summary,
            'system_resources': self._get_system_resources()
        }
    
    @staticmethod
    def _get_system_resources() -> dict:
        """获取系统资源使用情况"""
        try:
            process = psutil.Process()
            memory_info = process.memory_info()
            
            return {
                'memory_rss_mb': round(memory_info.rss / 1024 / 1024, 2),
                'memory_vms_mb': round(memory_info.vms / 1024 / 1024, 2),
                'cpu_percent': process.cpu_percent(interval=0.1),
                'num_threads': process.num_threads(),
                'open_files': len(process.open_files()),
            }
        except Exception:
            return {}


# 创建全局性能监控器
perf_monitor = PerformanceMonitor()


# 创建FastAPI应用
app = FastAPI(
    title="阿里云视频分析平台",
    description="支持视频处理、音频转录和内容分析的API服务",
    version="1.0.0"
)

# 添加性能监控中间件
@app.middleware("http")
async def performance_monitoring_middleware(request: Request, call_next):
    """性能监控和日志记录中间件"""
    start_time = time.time()
    
    # 创建带请求ID的日志记录器
    ctx_logger = get_context_logger()
    
    # 记录请求开始
    ctx_logger.info(
        f"🔵 收到请求: {request.method} {request.url.path}",
        method=request.method,
        path=request.url.path,
        client_host=request.client.host if request.client else 'unknown',
        query_params=dict(request.query_params),
    )
    
    # 记录请求开始时的资源使用
    ctx_logger.log_resource_usage("请求开始")
    
    # 处理请求
    try:
        response = await call_next(request)
        
        # 计算处理时间
        process_time = time.time() - start_time
        process_time_ms = process_time * 1000
        
        # 记录到性能监控器
        perf_monitor.record_request(
            request.method,
            request.url.path,
            process_time,
            response.status_code
        )
        
        # 记录请求完成
        ctx_logger.log_performance(
            f"请求完成: {request.method} {request.url.path}",
            status_code=response.status_code,
            duration_ms=process_time_ms
        )
        
        # 记录请求结束时的资源使用
        ctx_logger.log_resource_usage("请求完成")
        
        # 添加性能头到响应
        response.headers["X-Process-Time"] = f"{process_time:.4f}"
        response.headers["X-Request-ID"] = ctx_logger.request_id
        
        return response
    
    except Exception as e:
        # 记录异常
        process_time = time.time() - start_time
        
        ctx_logger.exception(
            f"❌ 请求处理失败: {request.method} {request.url.path}",
            error_type=type(e).__name__,
            error_message=str(e),
            duration_ms=process_time * 1000
        )
        
        # 记录到性能监控器（500错误）
        perf_monitor.record_request(
            request.method,
            request.url.path,
            process_time,
            500
        )
        
        # 重新抛出异常让FastAPI处理
        raise

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


@app.get("/metrics")
async def get_metrics():
    """
    获取API性能指标
    
    返回系统性能统计数据，包括：
    - 请求统计
    - 响应时间
    - 错误率
    - 端点性能
    - 系统资源使用
    """
    return perf_monitor.get_stats()

if __name__ == "__main__":
    import uvicorn
    
    # 从环境变量获取端口，默认为8000
    port = int(os.getenv("PORT", 8000))
    
    logger.info(f"启动服务器在端口 {port}")
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=True)