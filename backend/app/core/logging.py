"""
Logging configuration for the video analysis platform.
增强版日志系统 - 支持结构化日志、请求追踪、性能监控
"""
import logging
import sys
import json
import time
import traceback
import uuid
import psutil
from typing import Optional, Dict, Any
from datetime import datetime
from pathlib import Path


class StructuredFormatter(logging.Formatter):
    """结构化日志格式化器 - 支持JSON格式输出"""
    
    def format(self, record: logging.LogRecord) -> str:
        """格式化日志记录为结构化格式"""
        # 基础日志信息
        log_data = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        
        # 添加额外的上下文信息
        if hasattr(record, "request_id"):
            log_data["request_id"] = record.request_id
        
        if hasattr(record, "user_id"):
            log_data["user_id"] = record.user_id
        
        if hasattr(record, "video_id"):
            log_data["video_id"] = record.video_id
        
        if hasattr(record, "duration_ms"):
            log_data["duration_ms"] = record.duration_ms
        
        if hasattr(record, "file_size"):
            log_data["file_size"] = record.file_size
        
        if hasattr(record, "extra_data"):
            log_data["extra"] = record.extra_data
        
        # 异常信息
        if record.exc_info:
            log_data["exception"] = {
                "type": record.exc_info[0].__name__,
                "message": str(record.exc_info[1]),
                "traceback": traceback.format_exception(*record.exc_info)
            }
        
        # 在控制台输出时使用彩色格式，文件输出时使用JSON
        if hasattr(record, "console_output") and record.console_output:
            # 彩色控制台输出
            color_codes = {
                "DEBUG": "\033[0;36m",    # 青色
                "INFO": "\033[0;32m",     # 绿色
                "WARNING": "\033[1;33m",  # 黄色
                "ERROR": "\033[0;31m",    # 红色
                "CRITICAL": "\033[1;31m", # 亮红色
            }
            reset_code = "\033[0m"
            
            color = color_codes.get(record.levelname, "")
            request_id = f"[{record.request_id}]" if hasattr(record, "request_id") else ""
            
            return f"{color}[{log_data['timestamp']}] {request_id} {record.levelname}{reset_code} - {record.getMessage()}"
        else:
            # JSON格式（用于文件日志）
            return json.dumps(log_data, ensure_ascii=False)


class ContextLogger:
    """上下文日志记录器 - 自动添加请求ID和性能指标"""
    
    def __init__(self, base_logger: logging.Logger, request_id: Optional[str] = None):
        self.base_logger = base_logger
        self.request_id = request_id or self._generate_request_id()
        self.start_time = time.time()
    
    @staticmethod
    def _generate_request_id() -> str:
        """生成唯一的请求ID（8位短ID）"""
        return str(uuid.uuid4())[:8]
    
    def _add_context(self, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """添加上下文信息到日志"""
        context = {
            "request_id": self.request_id,
            "console_output": True,  # 启用彩色控制台输出
        }
        if extra:
            context.update(extra)
        return context
    
    def debug(self, message: str, **kwargs):
        """记录DEBUG级别日志"""
        self.base_logger.debug(message, extra=self._add_context(kwargs))
    
    def info(self, message: str, **kwargs):
        """记录INFO级别日志"""
        self.base_logger.info(message, extra=self._add_context(kwargs))
    
    def warning(self, message: str, **kwargs):
        """记录WARNING级别日志"""
        self.base_logger.warning(message, extra=self._add_context(kwargs))
    
    def error(self, message: str, **kwargs):
        """记录ERROR级别日志"""
        self.base_logger.error(message, extra=self._add_context(kwargs))
    
    def critical(self, message: str, **kwargs):
        """记录CRITICAL级别日志"""
        self.base_logger.critical(message, extra=self._add_context(kwargs))
    
    def exception(self, message: str, **kwargs):
        """记录异常信息"""
        self.base_logger.exception(message, extra=self._add_context(kwargs))
    
    def log_performance(self, operation: str, **metrics):
        """记录性能指标"""
        duration_ms = (time.time() - self.start_time) * 1000
        perf_data = {
            "operation": operation,
            "duration_ms": round(duration_ms, 2),
            **metrics
        }
        self.info(f"⏱️ 性能指标 - {operation}: {duration_ms:.2f}ms", extra_data=perf_data)
    
    def log_resource_usage(self, stage: str):
        """记录系统资源使用情况"""
        process = psutil.Process()
        memory_info = process.memory_info()
        
        resource_data = {
            "stage": stage,
            "memory_rss_mb": round(memory_info.rss / 1024 / 1024, 2),
            "memory_vms_mb": round(memory_info.vms / 1024 / 1024, 2),
            "cpu_percent": process.cpu_percent(interval=0.1),
            "num_threads": process.num_threads(),
        }
        
        self.info(
            f"📊 资源使用 - {stage}: "
            f"内存={resource_data['memory_rss_mb']}MB, "
            f"CPU={resource_data['cpu_percent']}%",
            extra_data=resource_data
        )
    
    def log_file_operation(self, operation: str, file_path: str, file_size: Optional[int] = None, **kwargs):
        """记录文件操作"""
        file_data = {
            "operation": operation,
            "file_path": file_path,
            "file_name": Path(file_path).name,
        }
        
        if file_size:
            file_data["file_size"] = file_size
            file_data["file_size_mb"] = round(file_size / 1024 / 1024, 2)
        
        file_data.update(kwargs)
        
        self.info(
            f"📁 文件操作 - {operation}: {Path(file_path).name}" +
            (f" ({file_data['file_size_mb']}MB)" if file_size else ""),
            extra_data=file_data
        )


def setup_logging(
    level: int = logging.INFO,
    log_file: Optional[str] = None,
    enable_structured: bool = True
) -> logging.Logger:
    """
    设置应用程序日志
    
    Args:
        level: 日志级别
        log_file: 日志文件路径（可选）
        enable_structured: 是否启用结构化日志格式
    
    Returns:
        配置好的logger实例
    """
    # 创建logger
    logger = logging.getLogger("video_analysis")
    logger.setLevel(level)
    
    # 如果已经有处理器，先清除
    if logger.handlers:
        logger.handlers.clear()
    
    # 创建控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    
    # 设置格式化器
    if enable_structured:
        formatter = StructuredFormatter()
    else:
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
    
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # 添加文件处理器（如果指定）
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(level)
        
        # 文件日志使用JSON格式
        json_formatter = StructuredFormatter()
        file_handler.setFormatter(json_formatter)
        logger.addHandler(file_handler)
        
        # 添加错误日志单独文件
        error_log_file = str(log_path.parent / "error.log")
        error_handler = logging.FileHandler(error_log_file, encoding='utf-8')
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(json_formatter)
        logger.addHandler(error_handler)
    
    return logger


def get_context_logger(request_id: Optional[str] = None) -> ContextLogger:
    """
    获取上下文日志记录器
    
    Args:
        request_id: 请求ID（可选，如果不提供则自动生成）
    
    Returns:
        ContextLogger实例
    """
    return ContextLogger(logger, request_id)


# 创建全局logger实例（自动启用文件日志）
import os
log_file = os.getenv('LOG_FILE', 'logs/app.log')
logger = setup_logging(log_file=log_file)


__all__ = ['logger', 'setup_logging', 'get_context_logger', 'ContextLogger']