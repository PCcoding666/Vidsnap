# 千问API调用格式文档

## 概述

千问API支持多模态请求，可以接受文本和图像作为输入。本文档说明如何使用正确的格式调用千问API。

## 基本信息

- API端点: `https://dashscope-intl.aliyuncs.com/compatible-mode/v1/chat/completions`
- 请求方法: `POST`
- 请求头:
  ```
  Authorization: Bearer YOUR_API_KEY
  Content-Type: application/json
  ```

## 正确的请求格式

千问API遵循OpenAI兼容格式，但有一些特定要求：

### 消息格式

1. 系统消息:
```json
{
  "role": "system",
  "content": [
    {
      "type": "text",
      "text": "你是一位专业的视频分析师，善于从图像和音频转录中提取关键信息并生成摘要。"
    }
  ]
}
```

2. 用户消息(包含图像和文本):
```json
{
  "role": "user",
  "content": [
    {
      "type": "image_url",
      "image_url": {
        "url": "https://example.com/image.jpg"
      }
    },
    {
      "type": "text",
      "text": "这是什么场景？请描述一下。"
    }
  ]
}
```

### 完整请求示例

```json
{
  "model": "qwen-vl-max",
  "messages": [
    {
      "role": "system",
      "content": [
        {
          "type": "text",
          "text": "你是一位专业的视频分析师，善于从图像和音频转录中提取关键信息并生成摘要。"
        }
      ]
    },
    {
      "role": "user",
      "content": [
        {
          "type": "image_url",
          "image_url": {
            "url": "https://example.com/image1.jpg"
          }
        },
        {
          "type": "image_url",
          "image_url": {
            "url": "https://example.com/image2.jpg"
          }
        },
        {
          "type": "text",
          "text": "根据这些图像和以下转录文本生成摘要：\n[转录文本内容]"
        }
      ]
    }
  ]
}
```

## Python代码示例

使用 `requests`:

```python
import requests
import json

# API信息
api_key = "YOUR_API_KEY"
base_url = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1/chat/completions"

# 请求头
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
                "text": "你是一位专业的视频分析师，善于从图像和音频转录中提取关键信息并生成摘要。"
            }
        ]
    },
    {
        "role": "user",
        "content": [
            {
                "type": "image_url",
                "image_url": {
                    "url": "https://example.com/image.jpg"
                }
            },
            {
                "type": "text",
                "text": "这是什么场景？请描述一下。"
            }
        ]
    }
]

# 构建请求体
payload = {
    "model": "qwen-vl-max",
    "messages": messages
}

# 发送请求
response = requests.post(
    base_url,
    headers=headers,
    json=payload,
    timeout=30
)

# 处理响应
if response.status_code == 200:
    response_data = response.json()
    if "choices" in response_data and len(response_data["choices"]) > 0:
        content = response_data["choices"][0]["message"]["content"]
        print(f"生成的内容: {content}")
else:
    print(f"请求失败: {response.status_code}")
    print(f"错误详情: {response.text}")
```

使用 `openai` 库:

```python
from openai import OpenAI

# 初始化客户端
client = OpenAI(
    api_key="YOUR_API_KEY",
    base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
)

# 构建消息
messages = [
    {
        "role": "system",
        "content": [
            {
                "type": "text",
                "text": "你是一位专业的视频分析师，善于从图像和音频转录中提取关键信息并生成摘要。"
            }
        ]
    },
    {
        "role": "user",
        "content": [
            {
                "type": "image_url",
                "image_url": {
                    "url": "https://example.com/image.jpg"
                }
            },
            {
                "type": "text",
                "text": "这是什么场景？请描述一下。"
            }
        ]
    }
]

# 发送请求
completion = client.chat.completions.create(
    model="qwen-vl-max",
    messages=messages
)

# 获取响应
content = completion.choices[0].message.content
print(f"生成的内容: {content}")
```

## 常见错误

1. 消息格式错误:
   - 系统消息内容不是数组
   - 图像URL格式错误，应使用 `"type": "image_url"` 和 `"image_url": {"url": "图像URL"}`
   - 文本内容格式错误，应使用 `"type": "text"` 和 `"text": "文本内容"`

2. API密钥错误:
   - 确保在环境变量中设置了正确的API密钥

3. 模型限制:
   - 千问API对不同模型有不同的token限制，请参考官方文档

4. 并发限制:
   - 千问API可能有并发调用限制，建议使用重试机制

## 参考资料

- [千问API官方文档](https://www.alibabacloud.com/help/en/model-studio/developer-reference/use-qwen-by-calling-api)
- [OpenAI兼容格式文档](https://www.alibabacloud.com/help/en/model-studio/getting-started/first-api-call-to-qwen) 