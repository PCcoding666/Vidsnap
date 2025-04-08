import logging
import json
import os
import datetime
import time
from typing import Dict, Any, Optional

# 创建专用的API调试日志记录器
api_logger = logging.getLogger("qwen_api_debug")
api_logger.setLevel(logging.DEBUG)

# 确保日志目录存在
log_dir = "logs"
os.makedirs(log_dir, exist_ok=True)

# 添加文件处理器，按日期生成日志文件
log_file = os.path.join(log_dir, f"qwen_api_debug_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
file_handler = logging.FileHandler(log_file)
file_handler.setLevel(logging.DEBUG)

# 设置日志格式
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)
api_logger.addHandler(file_handler)

def log_api_request(payload: Dict[str, Any], headers: Optional[Dict[str, str]] = None) -> None:
    """记录API请求的详细信息"""
    api_logger.info("===== API请求开始 =====")
    
    # 创建安全的有效负载副本（移除敏感信息）
    safe_payload = _sanitize_payload(payload)
    
    # 记录有效负载
    api_logger.info(f"请求有效负载: {json.dumps(safe_payload, ensure_ascii=False, indent=2)}")
    
    # 记录请求头（排除授权信息）
    if headers:
        safe_headers = headers.copy()
        if "Authorization" in safe_headers:
            auth_value = safe_headers["Authorization"]
            if auth_value.startswith("Bearer "):
                token = auth_value[7:]  # 移除 "Bearer " 前缀
                # 只展示令牌的一小部分
                if len(token) > 10:
                    masked_token = token[:4] + "..." + token[-4:]
                else:
                    masked_token = "***"
                safe_headers["Authorization"] = f"Bearer {masked_token}"
        
        api_logger.info(f"请求头: {json.dumps(safe_headers, ensure_ascii=False, indent=2)}")

def log_api_response(api_base, status_code, response_text, duration=None):
    """记录API响应信息"""
    api_logger.info(f"API端点: {api_base}")
    api_logger.info(f"状态码: {status_code}")
    
    # 处理duration参数的类型问题
    if duration is not None:
        try:
            # 尝试将duration转换为浮点数并格式化
            duration_float = float(duration)
            api_logger.info(f"响应时间: {duration_float:.2f} 秒")
        except (ValueError, TypeError):
            # 如果转换失败，则直接输出原始值
            api_logger.info(f"响应时间: {duration}")
    
    # 尝试解析JSON响应
    try:
        response_json = json.loads(response_text)
        api_logger.info(f"响应内容: {json.dumps(response_json, ensure_ascii=False, indent=2)}")
    except Exception as e:
        api_logger.info(f"响应内容: {response_text[:1000]}...")
        if len(response_text) > 1000:
            api_logger.info("(响应内容过长，已截断)")

def log_api_error(error: Exception, context: str = "") -> None:
    """记录API错误信息"""
    api_logger.error(f"===== API错误: {context} =====")
    api_logger.error(f"错误类型: {error.__class__.__name__}")
    api_logger.error(f"错误消息: {str(error)}")
    api_logger.error(f"===== 错误详情结束 =====")

def _sanitize_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """创建安全的有效负载副本，移除敏感信息如图像数据"""
    if not isinstance(payload, dict):
        return payload
    
    result = payload.copy()
    
    # 处理messages数组
    if "messages" in result and isinstance(result["messages"], list):
        for message in result["messages"]:
            if isinstance(message, dict) and "content" in message and isinstance(message["content"], list):
                for content_item in message["content"]:
                    if isinstance(content_item, dict) and content_item.get("type") == "image_url":
                        image_url = content_item.get("image_url", {}).get("url", "")
                        if image_url.startswith("data:image"):
                            # 截断图像URL以避免日志文件过大
                            parts = image_url.split(",")
                            if len(parts) > 1:
                                prefix = parts[0] + ","
                                content_item["image_url"]["url"] = prefix + "<图像数据已截断>"
    
    return result
