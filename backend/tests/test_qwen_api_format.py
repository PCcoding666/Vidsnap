import os
import sys
import json
from dotenv import load_dotenv
from openai import OpenAI
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
file_handler = logging.FileHandler(os.path.join(log_dir, 'qwen_api_format_test.log'))
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
base_url = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"

# 模型
model_name = os.getenv("QWEN_MODEL", "qwen-vl-max")

logger.info("=== 环境变量信息 ===")
logger.info(f"QWEN_API_KEY: {'已设置' if api_key else '未设置'}")
logger.info(f"QWEN_MODEL: {model_name}")
logger.info(f"BASE_URL: {base_url}")

logger.info("\n=== 测试正确格式的API请求 ===")
try:
    # 初始化OpenAI客户端
    client = OpenAI(
        api_key=api_key,
        base_url=base_url,
    )
    
    # 使用正确的格式发送请求
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
    
    logger.info("准备发送请求...")
    logger.info(f"请求消息结构: {json.dumps(messages, indent=2, ensure_ascii=False)}")
    
    completion = client.chat.completions.create(
        model=model_name,
        messages=messages,
    )
    
    logger.info(f"API响应状态: {completion.model_dump().get('model')}")
    logger.info(f"API响应内容: {completion.choices[0].message.content}")
    print(f"API响应内容: {completion.choices[0].message.content}")
    
except Exception as e:
    logger.error(f"请求失败: {e}")
    print(f"请求失败: {e}") 