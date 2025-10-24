# Gradio 界面集成 Chat with Video 功能

## 📋 集成方案

将 Chat with Video 功能集成到现有的 Gradio 主界面中，提供完整的视频分析 + 对话体验。

---

## 🎯 集成目标

在 `gradio_app.py` 中添加一个新的标签页"💬 与视频对话"，用户可以：

1. 在处理完视频后，直接启动聊天会话
2. 基于生成的 metadata 进行多轮问答
3. 查看带时间戳和关键帧引用的回答

---

## 🔧 集成步骤

### 步骤 1: 修改 gradio_app.py

在现有的三个标签页后添加第四个标签页：

```python
# gradio_app.py
import requests
from typing import List, Tuple, Optional

# 全局变量存储当前会话
current_chat_session: Optional[str] = None
current_video_metadata: Optional[dict] = None

def start_chat_from_result(result: dict) -> Tuple[str, str]:
    """从处理结果启动聊天会话"""
    global current_chat_session, current_video_metadata
    
    if not result or result.get("status") != "success":
        return "❌ 错误: 请先成功处理视频", ""
    
    try:
        # 准备 metadata
        from dataclasses import asdict
        metadata_dict = asdict(result["metadata"])
        current_video_metadata = metadata_dict
        
        # 调用 API 启动会话
        response = requests.post(
            "http://localhost:8000/analysis/chat/start",
            json={
                "video_id": result["video_id"],
                "metadata": metadata_dict
            }
        )
        
        if response.status_code == 200:
            r = response.json()
            current_chat_session = r["session_id"]
            
            info = f"""✅ 聊天会话已启动！

📋 会话信息:
- Video ID: {r['video_id']}
- 关键帧: {r['keyframes_count']}
- 转录片段: {r['transcript_segments_count']}

💬 现在可以提问了！
"""
            return "✅ 会话已启动", info
        else:
            return "❌ 启动失败", str(response.json())
    
    except Exception as e:
        return f"❌ 错误: {str(e)}", ""


def chat_ask(question: str, history: List[Tuple[str, str]]) -> Tuple[List[Tuple[str, str]], str]:
    """提问并获取回答"""
    global current_chat_session
    
    if not current_chat_session:
        return history, "❌ 请先启动聊天会话"
    
    if not question:
        return history, "❌ 请输入问题"
    
    try:
        response = requests.post(
            "http://localhost:8000/analysis/chat/message",
            json={
                "session_id": current_chat_session,
                "question": question,
                "top_k": 5,
                "auto_keyframes": True
            }
        )
        
        if response.status_code == 200:
            r = response.json()
            answer = r["answer"]
            refs = r["references"]
            
            # 添加到历史
            history = history + [(question, answer)]
            
            # 格式化引用
            ref_text = "📌 引用信息:\n\n"
            if refs["time_ranges"]:
                ref_text += "🕒 相关时间段:\n"
                for tr in refs["time_ranges"]:
                    ref_text += f"  • {tr['start_time']:.1f}s - {tr['end_time']:.1f}s\n"
            
            return history, ref_text
        else:
            return history, f"❌ 提问失败: {response.json()}"
    
    except Exception as e:
        return history, f"❌ 错误: {str(e)}"


# 在主界面中添加标签页
with gr.Blocks() as app:
    # ... 现有的标签页 ...
    
    with gr.Tab("💬 与视频对话"):
        gr.Markdown("### 基于视频内容的智能问答")
        gr.Markdown("先处理视频，然后在这里与视频内容进行对话")
        
        with gr.Row():
            start_chat_btn = gr.Button("🚀 启动聊天会话", variant="primary")
        
        chat_status = gr.Textbox(label="状态", interactive=False)
        chat_info = gr.Textbox(label="会话信息", interactive=False, lines=8)
        
        gr.Markdown("---")
        
        chatbot = gr.Chatbot(label="对话历史", height=400)
        
        with gr.Row():
            question_input = gr.Textbox(
                label="你的问题",
                placeholder="例如: 视频中在哪里讲了XXX？",
                scale=4
            )
            send_btn = gr.Button("💬 发送", variant="primary", scale=1)
        
        references = gr.Textbox(label="引用信息", interactive=False, lines=6)
        
        # 事件绑定
        start_chat_btn.click(
            fn=start_chat_from_result,
            inputs=[result_state],  # 从处理结果获取
            outputs=[chat_status, chat_info]
        )
        
        send_btn.click(
            fn=chat_ask,
            inputs=[question_input, chatbot],
            outputs=[chatbot, references]
        ).then(
            fn=lambda: "",
            outputs=question_input
        )
```

---

## 🎨 界面布局

```
┌─────────────────────────────────────────────────┐
│  标签页: 💬 与视频对话                           │
├─────────────────────────────────────────────────┤
│                                                 │
│  [🚀 启动聊天会话]                               │
│                                                 │
│  ┌─────────────────────────────────────────┐   │
│  │ 状态: ✅ 会话已启动                      │   │
│  └─────────────────────────────────────────┘   │
│                                                 │
│  ┌─────────────────────────────────────────┐   │
│  │ 会话信息:                                │   │
│  │ - Video ID: xxx                          │   │
│  │ - 关键帧: 10                             │   │
│  │ - 转录片段: 50                           │   │
│  └─────────────────────────────────────────┘   │
│                                                 │
│  ─────────────────────────────────────────     │
│                                                 │
│  ┌─────────────────────────────────────────┐   │
│  │ 对话历史:                                │   │
│  │                                          │   │
│  │ 👤: 视频讲了什么？                       │   │
│  │ 🤖: 这个视频主要介绍...                  │   │
│  │                                          │   │
│  │ 👤: 在哪里讲了pandas？                   │   │
│  │ 🤖: 在15:30-20:45这个时间段...          │   │
│  └─────────────────────────────────────────┘   │
│                                                 │
│  ┌──────────────────────────┐  [💬 发送]      │
│  │ 你的问题...              │                  │
│  └──────────────────────────┘                  │
│                                                 │
│  ┌─────────────────────────────────────────┐   │
│  │ 引用信息:                                │   │
│  │ 🕒 相关时间段:                           │   │
│  │   • 15:30 - 20:45                        │   │
│  │ 🖼️ 关键帧: Frame 3                       │   │
│  └─────────────────────────────────────────┘   │
└─────────────────────────────────────────────────┘
```

---

## 📝 完整集成代码示例

### gradio_app.py (Chat 部分)

```python
# 在文件顶部添加
import requests
from typing import List, Tuple, Optional

# 全局变量
current_chat_session: Optional[str] = None

def start_chat_from_result(result: dict) -> Tuple[str, str]:
    """从视频处理结果启动聊天"""
    global current_chat_session
    
    if not result or result.get("status") != "success":
        return "❌ 错误: 请先处理视频", ""
    
    try:
        from dataclasses import asdict
        metadata = asdict(result["metadata"])
        
        response = requests.post(
            "http://localhost:8000/analysis/chat/start",
            json={
                "video_id": result["video_id"],
                "metadata": metadata
            },
            timeout=10
        )
        
        if response.status_code == 200:
            r = response.json()
            current_chat_session = r["session_id"]
            info = f"✅ 会话已启动\nVideo: {r['video_id']}\n关键帧: {r['keyframes_count']}\n转录: {r['transcript_segments_count']}"
            return "✅ 成功", info
        else:
            return "❌ 失败", str(response.json())
    except Exception as e:
        return f"❌ 错误: {str(e)}", ""


def chat_ask(question: str, history: List) -> Tuple[List, str]:
    """提问"""
    global current_chat_session
    
    if not current_chat_session:
        return history, "❌ 请先启动会话"
    
    try:
        response = requests.post(
            "http://localhost:8000/analysis/chat/message",
            json={
                "session_id": current_chat_session,
                "question": question,
                "top_k": 5,
                "auto_keyframes": True
            },
            timeout=30
        )
        
        if response.status_code == 200:
            r = response.json()
            history = history + [(question, r["answer"])]
            
            refs = "📌 引用:\n"
            for tr in r["references"]["time_ranges"][:3]:
                refs += f"• {tr['start_time']:.1f}s-{tr['end_time']:.1f}s\n"
            
            return history, refs
        else:
            return history, f"❌ 失败"
    except Exception as e:
        return history, f"❌ 错误: {str(e)}"


# 在 gr.Blocks() 中添加标签页
with gr.Tab("💬 与视频对话"):
    gr.Markdown("### 智能视频问答")
    
    start_btn = gr.Button("🚀 启动聊天", variant="primary")
    status = gr.Textbox(label="状态")
    info = gr.Textbox(label="会话信息", lines=5)
    
    gr.Markdown("---")
    
    chatbot = gr.Chatbot(height=400)
    question = gr.Textbox(placeholder="输入问题...")
    send = gr.Button("发送", variant="primary")
    refs = gr.Textbox(label="引用", lines=5)
    
    # 绑定
    start_btn.click(
        start_chat_from_result,
        inputs=[result_state],
        outputs=[status, info]
    )
    
    send.click(
        chat_ask,
        inputs=[question, chatbot],
        outputs=[chatbot, refs]
    ).then(lambda: "", outputs=question)
```

---

## 🔄 数据流

```
视频处理完成
    ↓
获取 metadata (包含 transcript 和 keyframes)
    ↓
点击「启动聊天」
    ↓
调用 /analysis/chat/start
    ↓
获得 session_id
    ↓
用户输入问题
    ↓
调用 /analysis/chat/message
    ↓
显示回答 + 引用信息
    ↓
继续多轮对话...
```

---

## 🎯 用户体验流程

1. **处理视频**
   - 用户在"输入配置"标签页上传视频或输入URL
   - 点击"开始处理"
   - 在"结果展示"查看处理结果

2. **启动对话**
   - 切换到"💬 与视频对话"标签页
   - 点击"启动聊天会话"
   - 查看会话信息确认启动成功

3. **开始提问**
   - 在输入框输入问题
   - 点击"发送"或按Enter
   - 查看AI回答和引用信息

4. **多轮对话**
   - 继续提问，进行深入讨论
   - AI会基于上下文给出连贯回答

---

## 💡 优化建议

### 1. 自动启动会话
在视频处理完成后自动启动聊天会话：

```python
def process_video_complete(result):
    # 处理完成后自动启动聊天
    if result["status"] == "success":
        chat_status, chat_info = start_chat_from_result(result)
        return result, chat_status, chat_info
    return result, "", ""
```

### 2. 添加快捷问题
提供常见问题按钮：

```python
with gr.Row():
    gr.Button("视频讲了什么？").click(...)
    gr.Button("有哪些重点内容？").click(...)
    gr.Button("在哪里讲了XXX？").click(...)
```

### 3. 时间戳跳转
点击时间引用可以跳转到视频播放器：

```python
def jump_to_timestamp(timestamp: float):
    """跳转到指定时间戳"""
    # 更新视频播放器位置
    return timestamp
```

### 4. 关键帧预览
显示引用的关键帧图像：

```python
def show_keyframes(keyframe_urls: List[str]):
    """显示关键帧图像"""
    return gr.Gallery(keyframe_urls)
```

---

## 🧪 测试集成

### 测试步骤
1. 启动后端: `python -m uvicorn app.main:app --reload`
2. 启动前端: `./run_gradio.sh`
3. 上传测试视频并处理
4. 切换到对话标签页
5. 启动会话并提问

### 验证清单
- [ ] 会话启动成功
- [ ] 提问得到正确回答
- [ ] 引用信息显示正确
- [ ] 多轮对话上下文连贯
- [ ] 错误处理正常

---

## 📚 相关文档

- [Chat 功能指南](./CHAT_WITH_VIDEO_GUIDE.md)
- [实现总结](./CHAT_IMPLEMENTATION_SUMMARY.md)
- [快速开始](../../CHAT_QUICK_START.md)

---

**版本**: 1.0  
**更新时间**: 2025-10-22  
**状态**: 待集成
