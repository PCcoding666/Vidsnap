#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
千问服务集成测试脚本
测试QwenService类的主要功能，包括初始化、可用性检查和摘要生成
"""

import os
import sys
import logging
from dotenv import load_dotenv
import argparse
from pathlib import Path

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 添加项目根目录到PYTHONPATH
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, ".."))
sys.path.insert(0, project_root)

# 加载环境变量
load_dotenv()

def setup_logging(verbose=False):
    """配置日志输出"""
    log_level = logging.DEBUG if verbose else logging.INFO
    logger.setLevel(log_level)
    # 添加文件处理器
    log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
    os.makedirs(log_dir, exist_ok=True)
    file_handler = logging.FileHandler(os.path.join(log_dir, 'qwen_integration_test.log'))
    file_handler.setLevel(log_level)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    return logger

def check_environment():
    """检查环境变量是否正确设置"""
    required_vars = ["QWEN_API_KEY"]
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        logger.error(f"缺少必要的环境变量: {', '.join(missing_vars)}")
        return False
    
    logger.info("环境变量检查通过")
    return True

def test_qwen_service_init():
    """测试QwenService类的初始化"""
    try:
        from app.services.summary.qwen_service_part2 import QwenService
        logger.info("导入QwenService类成功")
        
        service = QwenService()
        logger.info(f"QwenService初始化成功，服务可用状态: {service.is_available()}")
        
        return service
    except Exception as e:
        logger.error(f"QwenService初始化失败: {e}")
        return None

def test_direct_api_call():
    """测试直接调用千问API"""
    try:
        import requests
        import json
        
        api_key = os.getenv("QWEN_API_KEY")
        base_url = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1/chat/completions"
        
        # 设置请求头
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        # 构建消息
        messages = [
            {
                "role": "system",
                "content": [
                    {
                        "type": "text",
                        "text": "你是一个有帮助的助手。"
                    }
                ]
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "请简要介绍一下视频摘要生成的方法。"
                    }
                ]
            }
        ]
        
        # 构建请求体
        payload = {
            "model": "qwen-max",  # 纯文本模型
            "messages": messages
        }
        
        logger.info("发送直接API请求...")
        
        response = requests.post(
            base_url,
            headers=headers,
            json=payload,
            timeout=30
        )
        
        logger.info(f"API响应状态码: {response.status_code}")
        
        if response.status_code == 200:
            response_data = response.json()
            content = response_data.get("choices", [{}])[0].get("message", {}).get("content", "")
            logger.info(f"API响应内容(摘要): {content[:100]}...")
            print(f"API响应摘要: {content[:100]}...")
            return True
        else:
            logger.error(f"API请求失败: {response.status_code}, {response.text}")
            return False
    
    except Exception as e:
        logger.error(f"API请求过程中出错: {e}")
        return False

def test_summary_generation(service, test_type="text"):
    """测试摘要生成功能"""
    if not service or not service.is_available():
        logger.error("QwenService不可用，跳过摘要生成测试")
        return False
    
    try:
        if test_type == "text":
            # 测试纯文本摘要
            transcript = """
            这是一个测试视频的转录文本。这个视频主要讨论了人工智能的发展和应用。
            视频中提到了机器学习、深度学习和自然语言处理等技术。
            同时，视频也探讨了AI在医疗、教育和金融等领域的应用前景。
            最后，视频总结了AI技术的未来发展趋势和可能带来的社会影响。
            """
            
            metadata = {
                "title": "人工智能发展与应用概述",
                "channel": "技术前沿",
                "duration": 600,
                "upload_date": "20250101",
                "categories": ["Technology"],
                "tags": ["AI", "机器学习", "深度学习"],
                "description": "本视频概述了人工智能的发展历程、关键技术和应用领域，以及未来发展趋势。"
            }
            
            logger.info("测试纯文本摘要生成...")
            result = service.generate_summary_from_frames(
                http_image_urls=[],  # 无图像
                audio_transcript=transcript,
                video_metadata=metadata,
                language="zh",
                granularity="medium",
                format_markdown=True
            )
            
            if "error" in result:
                logger.error(f"纯文本摘要生成失败: {result['error']}")
                return False
            
            summary_content = result.get("summary", {}).get("choices", [{}])[0].get("message", {}).get("content", "")
            logger.info(f"生成的摘要(摘要): {summary_content[:100]}...")
            print(f"生成的摘要(摘要): {summary_content[:100]}...")
            return True
            
        elif test_type == "multimodal":
            # 测试多模态摘要
            # 使用公开可访问的测试图像
            http_image_urls = [
                "https://dashscope.oss-cn-beijing.aliyuncs.com/images/tiger.png",
                "https://dashscope.oss-cn-beijing.aliyuncs.com/images/dog_and_girl.jpeg"
            ]
            
            transcript = """
            这是一个关于野生动物的测试视频转录文本。视频中展示了老虎和狗等动物的生活场景。
            视频讨论了保护野生动物的重要性和人类与动物和谐相处的方式。
            """
            
            metadata = {
                "title": "野生动物与人类",
                "channel": "自然探索",
                "duration": 480,
                "upload_date": "20250201",
                "categories": ["Nature"],
                "tags": ["野生动物", "保护", "自然"],
                "description": "本视频展示了野生动物的生活场景，讨论了野生动物保护的重要性。"
            }
            
            logger.info("测试多模态摘要生成...")
            result = service.generate_summary_from_frames(
                http_image_urls=http_image_urls,
                audio_transcript=transcript,
                video_metadata=metadata,
                language="zh",
                granularity="medium",
                format_markdown=True
            )
            
            if "error" in result:
                logger.error(f"多模态摘要生成失败: {result['error']}")
                return False
            
            summary_content = result.get("summary", {}).get("choices", [{}])[0].get("message", {}).get("content", "")
            logger.info(f"生成的摘要(摘要): {summary_content[:100]}...")
            print(f"生成的摘要(摘要): {summary_content[:100]}...")
            return True
    
    except Exception as e:
        logger.error(f"摘要生成测试过程中出错: {e}")
        return False

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="千问服务集成测试")
    parser.add_argument("-v", "--verbose", action="store_true", help="输出详细日志")
    parser.add_argument("-t", "--test", choices=["init", "api", "text", "multimodal", "all"], 
                        default="all", help="选择要运行的测试类型")
    args = parser.parse_args()
    
    # 设置日志
    setup_logging(args.verbose)
    
    logger.info("===== 开始千问服务集成测试 =====")
    
    # 检查环境
    if not check_environment():
        sys.exit(1)
    
    # 根据参数执行测试
    if args.test in ["init", "text", "multimodal", "all"]:
        service = test_qwen_service_init()
        if not service and args.test != "init":
            logger.error("QwenService初始化失败，无法继续测试")
            sys.exit(1)
    
    if args.test in ["api", "all"]:
        logger.info("----- 测试直接API调用 -----")
        success = test_direct_api_call()
        logger.info(f"直接API调用测试结果: {'成功' if success else '失败'}")
    
    if args.test in ["text", "all"]:
        logger.info("----- 测试纯文本摘要生成 -----")
        success = test_summary_generation(service, "text")
        logger.info(f"纯文本摘要生成测试结果: {'成功' if success else '失败'}")
    
    if args.test in ["multimodal", "all"]:
        logger.info("----- 测试多模态摘要生成 -----")
        success = test_summary_generation(service, "multimodal")
        logger.info(f"多模态摘要生成测试结果: {'成功' if success else '失败'}")
    
    logger.info("===== 千问服务集成测试完成 =====")

if __name__ == "__main__":
    main() 