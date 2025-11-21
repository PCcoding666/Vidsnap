# 🚀 Chat with Video - 快速开始

## 一分钟上手

### 1️⃣ 启动后端服务
```bash
cd backend
python -m uvicorn app.main:app --reload
```
后端运行在: http://localhost:8000

### 2️⃣ 启动演示界面
**新建终端窗口**，运行：
```bash
cd backend
./run_chat_demo.sh
```
演示界面: http://localhost:7861

### 3️⃣ 开始使用
1. 在演示界面点击「加载示例数据」
2. 点击「启动会话」
3. 在对话标签页输入问题，开始聊天！

---

## 📋 功能概览

### 核心能力
- ✅ **多轮对话**: 支持连续追问和深入讨论
- ✅ **时间定位**: 自动定位视频中的相关片段
- ✅ **视觉问答**: 结合关键帧图像进行分析
- ✅ **智能检索**: 基于问题自动检索转录内容

### 技术栈
- **LLM**: Qwen3-VL-Plus (qwen-vl-plus)
- **框架**: FastAPI + React
- **输入**: 转录文本 + 关键帧图像

---

## 💬 示例问题

### 时间定位
```
问: 视频中在哪里讲了数据分析？
答: 在视频的 10:30-15:45 这个时间段...
```

### 视觉问答
```
问: 这个界面的设计有什么特点？（指定关键帧 ID: 3）
答: 从关键帧可以看到，界面采用了深色主题...
```

### 内容总结
```
问: 这个视频主要讲什么？
答: 这个视频主要介绍 Python 数据分析的基础知识...
```

---

## 🔌 API 使用

### Python 示例
```python
import requests

BASE = "http://localhost:8000/analysis"

# 启动会话
r = requests.post(f"{BASE}/chat/start", json={
    "video_id": "my_video",
    "metadata": {...}  # 包含 transcript 和 keyframes
})
session_id = r.json()["session_id"]

# 提问
r = requests.post(f"{BASE}/chat/message", json={
    "session_id": session_id,
    "question": "视频讲了什么？"
})
print(r.json()["answer"])

# 结束会话
requests.delete(f"{BASE}/chat/session/{session_id}")
```

### cURL 示例
```bash
# 启动会话
curl -X POST http://localhost:8000/analysis/chat/start \
  -H "Content-Type: application/json" \
  -d '{"video_id":"test","metadata":{...}}'

# 提问
curl -X POST http://localhost:8000/analysis/chat/message \
  -H "Content-Type: application/json" \
  -d '{
    "session_id":"xxx",
    "question":"视频讲了什么？"
  }'
```

---

## 🧪 运行测试

```bash
cd backend/app/tests
./run_chat_test.sh
```

测试覆盖:
- ✅ 会话管理
- ✅ 纯文本问答
- ✅ 视觉问答
- ✅ 多轮对话
- ✅ 上下文检索

---

## ⚙️ 配置要求

### 环境变量
```bash
# .env 文件
QWEN_API_KEY=sk-xxx...  # 必需
```

### 依赖项
- Python 3.8+
- FastAPI
- React
- shadcn/ui
- requests
- dashscope

---

## 📖 完整文档

- [完整功能指南](./app/tests/docs/CHAT_WITH_VIDEO_GUIDE.md)
- [实现总结](./app/tests/docs/CHAT_IMPLEMENTATION_SUMMARY.md)
- [API 参考](./app/tests/docs/CHAT_WITH_VIDEO_GUIDE.md#api-接口)

---

## 🆘 常见问题

**Q: "LLM 服务不可用"**  
A: 检查 QWEN_API_KEY 是否设置正确

**Q: "会话不存在"**  
A: session_id 无效或已过期，重新启动会话

**Q: 回答不准确**  
A: 增加 top_k 参数或手动指定关键帧 ID

---

**快速链接**:
- 演示界面: http://localhost:7861
- API 文档: http://localhost:8000/docs
- 测试脚本: `./app/tests/run_chat_test.sh`
