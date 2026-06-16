"""
Celery应用配置
用于后台任务处理
"""
import os
import logging
from celery import Celery
from kombu import Queue

# 禁用冗余的第三方库日志
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)

# 从环境变量获取Redis配置
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", REDIS_URL)
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", REDIS_URL)

# 创建Celery应用
celery_app = Celery(
    "vidsnap",
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND,
    include=[]
)

# Celery配置
celery_app.conf.update(
    # 任务序列化
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    
    # 时区配置
    timezone="Asia/Shanghai",
    enable_utc=True,
    
    # 任务执行配置
    task_acks_late=True,  # 任务完成后才确认
    task_reject_on_worker_lost=True,  # Worker丢失时拒绝任务
    worker_prefetch_multiplier=1,  # 每次只取一个任务
    
    # 结果配置
    result_expires=3600,  # 结果1小时后过期
    
    # 队列配置
    task_queues=(
        Queue("default", routing_key="default"),
    ),
    task_default_queue="default",
    task_default_routing_key="default",
    task_routes={},
    beat_schedule={},
    
    # 并发配置
    worker_concurrency=4,  # 每个Worker的并发数
    
    # 内存限制（防止内存泄漏）
    worker_max_tasks_per_child=100,  # 每个子进程处理100个任务后重启
)

# 任务优先级配置
celery_app.conf.task_queue_max_priority = 10
celery_app.conf.task_default_priority = 5


def get_celery_app():
    """获取Celery应用实例"""
    return celery_app


# Worker 初始化钩子 - 初始化数据库服务
@celery_app.on_after_configure.connect
def setup_database(sender, **kwargs):
    """Celery 配置完成后初始化数据库"""
    import asyncio
    import threading
    from ..services.database_service import database_service
    
    def init_db():
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(database_service.initialize())
            logging.info("✅ Celery: 数据库服务已初始化")
        except Exception as e:
            logging.error(f"❌ Celery: 数据库初始化失败: {e}")
        finally:
            loop.close()
    
    # 在新线程中初始化避免事件循环冲突
    thread = threading.Thread(target=init_db)
    thread.start()
    thread.join(timeout=10)


# 用于测试的配置
class CeleryTestConfig:
    """测试环境Celery配置"""
    task_always_eager = True
    task_eager_propagates = True
    broker_url = "memory://"
    result_backend = "cache+memory://"


def configure_for_testing():
    """配置Celery为测试模式"""
    celery_app.conf.update(
        task_always_eager=True,
        task_eager_propagates=True,
    )
