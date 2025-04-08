import os
import json
from dotenv import load_dotenv
from openai import OpenAI

# 加载环境变量
load_dotenv()

# 获取API密钥
api_key = os.getenv("QWEN_API_KEY")
if not api_key:
    print("错误：未设置QWEN_API_KEY环境变量")
    exit(1)

# OpenAI兼容模式的BASE URL
base_url = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"

# 模型
model_name = os.getenv("QWEN_MODEL", "qwen-vl-max")

print("=== 环境变量信息 ===")
print(f"QWEN_API_KEY: {'已设置' if api_key else '未设置'}")
print(f"QWEN_MODEL: {model_name}")
print(f"BASE_URL: {base_url}")

print("\n=== 测试纯文本对话 ===")
try:
    # 初始化OpenAI客户端
    client = OpenAI(
        api_key=api_key,
        base_url=base_url,
    )
    
    # 发送纯文本请求
    completion = client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": [{"type": "text", "text": "You are a helpful assistant."}]},
            {"role": "user", "content": [{"type": "text", "text": "你是谁？"}]}
        ],
    )
    
    print(f"API响应: {completion.choices[0].message.content}")
except Exception as e:
    print(f"纯文本请求失败: {e}")

print("\n=== 测试多模态对话 ===")
try:
    # 初始化OpenAI客户端
    client = OpenAI(
        api_key=api_key,
        base_url=base_url,
    )
    
    # 发送多模态请求（包含图像）
    completion = client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": [{"type": "text", "text": "You are a helpful assistant."}]},
            {"role": "user", "content": [
                # 第一张图像链接
                {"type": "image_url", "image_url": {"url": "https://dashscope.oss-cn-beijing.aliyuncs.com/images/dog_and_girl.jpeg"}},
                # 第二张图像链接
                {"type": "image_url", "image_url": {"url": "https://dashscope.oss-cn-beijing.aliyuncs.com/images/tiger.png"}},
                # 提问文本
                {"type": "text", "text": "这些图描绘了什么内容？"}
            ]}
        ],
    )
    
    print(f"多模态API响应: {completion.choices[0].message.content}")
except Exception as e:
    print(f"多模态请求失败: {e}")

# 测试带有单张图像的请求
print("\n=== 测试单图像对话 ===")
try:
    completion = client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": [{"type": "text", "text": "You are a helpful assistant."}]},
            {"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": "https://dashscope.oss-cn-beijing.aliyuncs.com/images/tiger.png"}},
                {"type": "text", "text": "这是什么动物？它在做什么？"}
            ]}
        ],
    )
    
    print(f"单图像API响应: {completion.choices[0].message.content}")
except Exception as e:
    print(f"单图像请求失败: {e}") 