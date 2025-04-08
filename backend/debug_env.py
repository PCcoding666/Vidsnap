#!/usr/bin/env python
"""
环境变量调试脚本 - 用于验证.env文件是否正确加载
"""
import os
import sys
from dotenv import load_dotenv
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def test_env_loading():
    """测试环境变量加载"""
    logger.info("开始测试环境变量加载...")
    logger.info(f"当前工作目录: {os.getcwd()}")
    
    # 尝试多个可能的.env文件路径
    possible_env_paths = [
        ".env",
        "../.env",
        "../../.env",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"),
        os.path.join(os.getcwd(), ".env")
    ]
    
    # 检查每个路径是否存在.env文件
    for path in possible_env_paths:
        if os.path.exists(path):
            logger.info(f"找到.env文件: {path}")
            try:
                with open(path, 'r') as f:
                    logger.info(f".env文件内容前两行: {f.readline().strip()}, {f.readline().strip()}")
            except Exception as e:
                logger.error(f"读取.env文件时出错: {str(e)}")
        else:
            logger.info(f"未找到.env文件: {path}")
    
    # 尝试加载.env文件
    load_dotenv(verbose=True)
    
    # 检查关键环境变量
    env_vars = [
        "QWEN_API_KEY",
        "QWEN_API_BASE",
        "QWEN_MODEL",
        "OPENAI_API_KEY",
        "HF_TOKEN",
        "SECRET_KEY",
        "STORAGE_DIR"
    ]
    
    for var in env_vars:
        value = os.getenv(var)
        if value:
            # 对于密钥，只显示前几个字符
            if "KEY" in var or "TOKEN" in var:
                masked_value = value[:4] + "*" * (len(value) - 4) if len(value) > 4 else "****"
                logger.info(f"{var}: {masked_value} (已设置，长度: {len(value)})")
            else:
                logger.info(f"{var}: {value}")
        else:
            logger.warning(f"{var}: 未设置")

if __name__ == "__main__":
    test_env_loading()
    logger.info("环境变量测试完成") 