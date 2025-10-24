# Chat with Video - 视频多轮对话功能指南

## 📋 功能概述

**Chat with Video** 是一个基于视频元数据（转录文本 + 关键帧）的智能多轮对话系统，允许用户通过自然语言与视频内容进行交互。

### 核心特性

1. **多模态理解**
   - 结合转录文本和关键帧图像
   - 使用 Qwen3-VL-Plus 进行多模态推理

2. **智能上下文检索**
   - 基于问题自动检索相关转录片段
   - 自动匹配时间范围内的关键帧

3. **时间定位**
   - 回答中包含视频时间范围引用
   - 支持定位到具体的视频片段

4. **多轮对话**
   - 保持会话历史上下文
   - 支持连续追问和深入讨论

---

## 🏗️ 架构设计

### 服务层次

```
┌─────────────────────────────────────┐
│     Gradio Frontend / REST API      │
└────────────┬────────────────────────┘
             │
┌────────────▼────────────────────────┐
│   Chat Service (chat_service.py)    │
│  - Session Management               │
│  - Context Retrieval                │
│  - Multi-turn Dialogue              │
└────────────┬────────────────────────┘
             │
┌────────────▼────────────────────────┐
│   LLM Service (llm_service.py)      │
│  - Qwen3-VL-Plus (qwen-vl-plus)     │
│  - Qwen3-VL-Flash (qwen-vl-max)     │
└─────────────────────────────────────┘
```

### 数据流

```
用户问题
    ↓
转录文本检索 (关键词匹配)
    ↓
关键帧匹配 (时间范围)
    ↓
多模态上下文组装
    ↓
Qwen3-VL-Plus 推理
    ↓
回答 + 引用信息
```

---

## 🔌 API 接口

### 1. 启动会话

**POST** `/analysis/chat/start`

创建新的聊天会话，绑定视频元数据。

**请求体:**
```json
{
  "video_id": "video_123",
  "metadata": {
    "transcript": {
      "oss_audio_url": "https://...",
      "language": "zh-CN",
      "overall_confidence": 0.95,
      "segments": [
        {
          "text": "欢迎来到今天的教程...",
          "start_time": 0.0,
          "end_time": 5.2,
          "confidence": 0.98
        }
      ]
    },
    "keyframes": [
      {
        "frame_id": 1,
        "timestamp": 3.5,
        "oss_image_url": "https://...",
        "scene_description": "开场画面"
      }
    ]
  }
}
```

**响应:**
```json
{
  "status": "success",
  "session_id": "a1b2c3d4-...",
  "video_id": "video_123",
  "keyframes_count": 10,
  "transcript_segments_count": 50
}
```

---

### 2. 提问

**POST** `/analysis/chat/message`

在会话中提问，支持纯文本问答和视觉问答。

**请求体:**
```json
{
  "session_id": "a1b2c3d4-...",
  "question": "视频中在哪里讲了数据分析？",
  "keyframe_ids": [3, 5],       // 可选，指定关键帧ID用于视觉问答
  "top_k": 5,                   // 可选，检索相关片段数量
  "auto_keyframes": true        // 可选，自动匹配关键帧
}
```

**响应:**
```json
{
  "status": "success",
  "session_id": "a1b2c3d4-...",
  "answer": "在视频的 10:30-15:45 这个时间段，详细讲解了数据分析的重要性...",
  "references": {
    "time_ranges": [
      {
        "start_time": 630.0,
        "end_time": 945.0,
        "text": "数据分析可以帮助我们..."
      }
    ],
    "keyframe_ids": [3, 5],
    "keyframes": [
      {
        "frame_id": 3,
        "timestamp": 650.0,
        "oss_image_url": "https://..."
      }
    ]
  },
  "history_length": 4
}
```

---

### 3. 查看会话信息

**GET** `/analysis/chat/session/{session_id}`

获取会话的详细信息和历史对话。

**响应:**
```json
{
  "status": "success",
  "session_id": "a1b2c3d4-...",
  "video_id": "video_123",
  "created_at": "2025-10-22T10:30:00",
  "history_length": 10,
  "recent_messages": [
    {
      "role": "user",
      "content": "视频主要讲什么？",
      "timestamp": "2025-10-22T10:32:15"
    },
    {
      "role": "assistant",
      "content": "这个视频主要介绍...",
      "timestamp": "2025-10-22T10:32:18"
    }
  ],
  "keyframes_count": 10,
  "transcript_segments_count": 50
}
```

---

### 4. 结束会话

**DELETE** `/analysis/chat/session/{session_id}`

结束并清理会话。

**响应:**
```json
{
  "status": "success",
  "session_id": "a1b2c3d4-...",
  "message": "会话已结束"
}
```

---

### 5. 列出所有会话

**GET** `/analysis/chat/sessions`

列出所有活动的聊天会话。

**响应:**
```json
{
  "status": "success",
  "sessions": [
    {
      "session_id": "a1b2c3d4-...",
      "video_id": "video_123",
      "created_at": "2025-10-22T10:30:00",
      "history_length": 10
    }
  ],
  "total": 3
}
```

---

## 💡 使用场景

### 场景 1: 时间定位问答

**用户:** "视频中在哪里讲了 pandas 库的使用？"

**系统流程:**
1. 在转录文本中检索包含 "pandas" 的片段
2. 返回相关的时间范围（如 15:30-20:45）
3. 自动匹配该时间段内的关键帧

**回答示例:**
```
在视频的 15:30-20:45 这个时间段，详细介绍了 pandas 库的使用方法。
具体包括数据加载、清洗和基本操作等内容。
```

---

### 场景 2: 视觉问答

**用户:** "这个界面的设计有什么特点？"（指定关键帧 ID: 5）

**系统流程:**
1. 加载关键帧 5 的图像
2. 结合关键帧的 scene_description
3. 使用 Qwen3-VL-Plus 分析图像内容

**回答示例:**
```
从关键帧可以看到，这个界面采用了深色主题设计，
左侧是代码编辑区，右侧是实时输出面板。
整体布局简洁明了，便于用户专注于代码学习。
```

---

### 场景 3: 多轮对话

**第 1 轮:**
- 用户: "这个视频主要讲什么？"
- 助手: "这个视频主要介绍 Python 数据分析的基础知识..."

**第 2 轮:**
- 用户: "能详细说说 pandas 部分吗？"
- 助手: "pandas 部分在视频的 15:30 开始，主要包括..."

**第 3 轮:**
- 用户: "这部分有代码演示吗？"
- 助手: "是的，在 18:20 左右有实际的代码演示..."

---

## 🔧 核心实现

### 上下文检索算法

```python
def _retrieve_relevant_context(question, transcript, top_k=5):
    """
    从转录文本中检索与问题相关的片段
    
    算法:
    1. 提取问题中的关键词
    2. 计算每个转录片段的相关性得分（关键词匹配数）
    3. 按得分排序，取前 top_k 个片段
    4. 按时间顺序组合上下文
    """
    question_tokens = set(q.lower() for q in question.split())
    
    scored_segments = []
    for i, seg in enumerate(transcript.segments):
        score = sum(1 for token in question_tokens if token in seg.text.lower())
        if score > 0:
            scored_segments.append((score, i, seg))
    
    scored_segments.sort(key=lambda x: (-x[0], x[1]))
    selected = [seg for _, _, seg in scored_segments[:top_k]]
    
    return combine_context(selected)
```

### 关键帧自动匹配

```python
def _find_relevant_keyframes(time_ranges, keyframes, max_keyframes=3):
    """
    根据时间范围查找相关关键帧
    
    算法:
    1. 遍历所有关键帧
    2. 检查关键帧时间戳是否在任何时间范围内
    3. 返回前 max_keyframes 个匹配的关键帧
    """
    relevant_kfs = []
    for kf in keyframes:
        for tr in time_ranges:
            if tr["start_time"] <= kf.timestamp <= tr["end_time"]:
                relevant_kfs.append(kf)
                break
    
    return relevant_kfs[:max_keyframes]
```

### 多轮对话上下文管理

```python
# 保留最近 4 轮对话（8 条消息）
for msg in session.history[-8:]:
    messages.append({
        "role": msg.role,
        "content": [{"text": msg.content}]
    })

# 添加当前问题（多模态内容）
messages.append({
    "role": "user",
    "content": [
        {"text": f"用户问题：{question}"},
        {"text": f"相关转录：{context_text}"},
        {"image": keyframe_url}  # 可选
    ]
})
```

---

## 🧪 测试

### 运行测试

```bash
cd backend/app/tests
chmod +x run_chat_test.sh
./run_chat_test.sh
```

### 测试覆盖

1. ✅ 启动会话
2. ✅ 纯文本问答（时间定位）
3. ✅ 视觉问答（指定关键帧）
4. ✅ 多轮对话
5. ✅ 会话管理
6. ✅ 上下文检索

---

## 📊 性能优化

### 1. 上下文截断策略

- **智能截断**: 保留开头 60% + 结尾 40%
- **最大长度**: 2000 字符（可配置）
- **原因**: 避免超过模型上下文窗口

### 2. 关键帧数量限制

- **用户指定**: 无限制
- **自动匹配**: 最多 2 个
- **原因**: 平衡视觉信息量和推理效率

### 3. 历史对话保留

- **保留数量**: 最近 4 轮（8 条消息）
- **原因**: 保持上下文连贯性，避免过长输入

---

## 🚀 快速开始

### Python 脚本示例

```python
import requests

BASE_URL = "http://localhost:8000/analysis"

# 1. 启动会话
response = requests.post(f"{BASE_URL}/chat/start", json={
    "video_id": "my_video",
    "metadata": metadata  # 从 pipeline 获取
})
session_id = response.json()["session_id"]

# 2. 提问
response = requests.post(f"{BASE_URL}/chat/message", json={
    "session_id": session_id,
    "question": "视频中讲了哪些内容？"
})
answer = response.json()["answer"]
print(f"回答: {answer}")

# 3. 视觉问答
response = requests.post(f"{BASE_URL}/chat/message", json={
    "session_id": session_id,
    "question": "这个界面有什么特点？",
    "keyframe_ids": [3]
})

# 4. 结束会话
requests.delete(f"{BASE_URL}/chat/session/{session_id}")
```

---

## 🔐 环境配置

### 必需的环境变量

```bash
# .env 文件
QWEN_API_KEY=sk-xxx...  # 通义千问 API Key
```

### 可选配置

```python
# 在 chat_service.py 中
top_k = 5              # 检索片段数量
max_length = 800       # LLM 最大输出长度
max_keyframes = 3      # 自动匹配关键帧数量
```

---

## 📝 注意事项

1. **会话管理**
   - 会话存储在内存中，服务重启后会丢失
   - 生产环境建议使用 Redis 持久化

2. **API 限流**
   - 注意通义千问 API 的调用频率限制
   - 建议添加请求队列和重试机制

3. **上下文质量**
   - 转录质量直接影响检索效果
   - 关键帧的场景描述有助于视觉问答

4. **成本控制**
   - 每次对话会调用 Qwen3-VL-Plus
   - 注意 token 消耗和 API 费用

---

## 🛠️ 故障排查

### 问题 1: "LLM 服务不可用"

**原因:** QWEN_API_KEY 未设置或无效

**解决:**
```bash
export QWEN_API_KEY=sk-xxx...
# 或在 .env 文件中设置
```

### 问题 2: "会话不存在"

**原因:** session_id 无效或会话已过期

**解决:**
- 检查 session_id 是否正确
- 重新调用 `/chat/start` 创建新会话

### 问题 3: 回答不准确

**原因:** 上下文检索不精准

**解决:**
- 增加 `top_k` 参数（如 10）
- 手动指定 `keyframe_ids`
- 优化问题措辞，包含更多关键词

---

## 📚 相关文档

- [LLM Service Architecture](./QWEN3_VL_ARCHITECTURE.md)
- [Pipeline Orchestration](./TEST_PIPELINE_README.md)
- [Transcript Service Guide](./TRANSCRIPT_SERVICE_API_KEY_GUIDE.md)

---

## 🎯 未来改进

1. **向量检索**
   - 使用嵌入模型进行语义检索
   - 替代当前的关键词匹配

2. **会话持久化**
   - 集成 Redis 存储会话
   - 支持跨服务器会话恢复

3. **流式响应**
   - 支持 SSE 流式输出
   - 提升用户体验

4. **多语言支持**
   - 自动检测用户语言
   - 支持英文、日文等问答

---

**文档版本**: 1.0  
**更新时间**: 2025-10-22  
**维护者**: Video Analysis Team
