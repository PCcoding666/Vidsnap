import os
import sys
import json
import requests
from dotenv import load_dotenv
import logging

# 添加项目根目录到PYTHONPATH
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, ".."))
sys.path.insert(0, project_root)

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 添加文件处理器以记录到文件
log_dir = os.path.join(current_dir, "logs")
os.makedirs(log_dir, exist_ok=True)
file_handler = logging.FileHandler(os.path.join(log_dir, 'qwen_direct_test.log'))
file_handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

# 加载环境变量
load_dotenv()

# 获取API密钥
api_key = os.getenv("QWEN_API_KEY")
if not api_key:
    logger.error("错误：未设置QWEN_API_KEY环境变量")
    exit(1)

# OpenAI兼容模式的BASE URL
base_url = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1/chat/completions"

# 打印环境变量信息
logger.info("=== 环境变量信息 ===")
logger.info(f"QWEN_API_KEY: {'已设置' if api_key else '未设置'}")
logger.info(f"BASE_URL: {base_url}")

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
                "text": "你是一位专业的视频分析师，善于从图像和音频转录中提取关键信息并生成摘要。请提供一个包含主要内容、关键点和结论的摘要。"
            }
        ]
    },
    {
        "role": "user",
        "content": [
            {
                "type": "image_url",
                "image_url": {
                    "url": "https://dashscope.oss-cn-beijing.aliyuncs.com/images/tiger.png"
                }
            },
            {
                "type": "text",
                "text": "这是什么动物？它在做什么？请生成一个简短的描述。"
            }
        ]
    }
]

# 构建请求体
payload = {
    "model": "qwen-vl-max",  # 使用环境变量中的模型名称或默认值
    "messages": messages
}

logger.info("=== 发送API请求 ===")
logger.info(f"请求负载: {json.dumps(payload, indent=2, ensure_ascii=False)}")

try:
    # 发送请求
    response = requests.post(
        base_url,
        headers=headers,
        json=payload,
        timeout=30
    )
    
    # 打印响应信息
    logger.info(f"响应状态码: {response.status_code}")
    logger.info(f"响应内容: {response.text}")
    
    # 如果请求成功，解析JSON响应
    if response.status_code == 200:
        response_data = response.json()
        if "choices" in response_data and len(response_data["choices"]) > 0:
            content = response_data["choices"][0]["message"]["content"]
            logger.info(f"生成的内容: {content}")
            print(f"生成的内容: {content}")
        else:
            logger.warning("响应中没有找到生成的内容")
    else:
        logger.error(f"请求失败: {response.status_code}")
        logger.error(f"错误详情: {response.text}")
        
except Exception as e:
    logger.error(f"发送请求时出错: {e}") 