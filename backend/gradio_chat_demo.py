"""
Gradio Chat with Video 演示界面
用于测试视频多轮对话功能
"""
import gradio as gr
import requests
import json
import os
from typing import List, Tuple, Optional

# API 基础 URL（如果后端运行在其他端口，请修改）
API_BASE = os.getenv("API_BASE_URL", "http://localhost:8000")

# 全局会话 ID
current_session_id: Optional[str] = None


def format_time(seconds: float) -> str:
    """将秒数格式化为 MM:SS 或 HH:MM:SS"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    else:
        return f"{minutes:02d}:{secs:02d}"


def start_chat_session(video_id: str, metadata_json: str) -> Tuple[str, str]:
    """
    启动聊天会话
    
    Args:
        video_id: 视频 ID
        metadata_json: 元数据 JSON 字符串
        
    Returns:
        (状态消息, 会话信息)
    """
    global current_session_id
    
    if not video_id:
        return "❌ 错误: 请输入视频 ID", ""
    
    if not metadata_json:
        return "❌ 错误: 请输入视频元数据", ""
    
    try:
        # 解析 JSON
        metadata = json.loads(metadata_json)
        
        # 调用 API
        response = requests.post(
            f"{API_BASE}/analysis/chat/start",
            json={
                "video_id": video_id,
                "metadata": metadata
            },
            timeout=10
        )
        
        if response.status_code == 200:
            result = response.json()
            current_session_id = result["session_id"]
            
            info = f"""✅ 会话创建成功！

📋 会话信息:
- Session ID: {current_session_id}
- Video ID: {result['video_id']}
- 关键帧数量: {result['keyframes_count']}
- 转录片段数量: {result['transcript_segments_count']}

💬 现在可以开始提问了！
"""
            return "✅ 会话已启动", info
        else:
            error = response.json().get("detail", "未知错误")
            return f"❌ 启动失败: {error}", ""
            
    except json.JSONDecodeError:
        return "❌ 错误: 元数据 JSON 格式不正确", ""
    except Exception as e:
        return f"❌ 错误: {str(e)}", ""


def ask_question(
    question: str,
    keyframe_ids_str: str,
    top_k: int,
    auto_keyframes: bool,
    history: List[Tuple[str, str]]
) -> Tuple[List[Tuple[str, str]], str]:
    """
    提问并获取回答
    
    Args:
        question: 用户问题
        keyframe_ids_str: 关键帧 ID（逗号分隔）
        top_k: 检索片段数量
        auto_keyframes: 自动匹配关键帧
        history: 对话历史
        
    Returns:
        (更新后的历史, 引用信息)
    """
    global current_session_id
    
    if not current_session_id:
        return history, "❌ 错误: 请先启动会话"
    
    if not question:
        return history, "❌ 错误: 请输入问题"
    
    try:
        # 解析关键帧 ID
        keyframe_ids = None
        if keyframe_ids_str.strip():
            keyframe_ids = [int(x.strip()) for x in keyframe_ids_str.split(",")]
        
        # 调用 API
        response = requests.post(
            f"{API_BASE}/analysis/chat/message",
            json={
                "session_id": current_session_id,
                "question": question,
                "keyframe_ids": keyframe_ids,
                "top_k": top_k,
                "auto_keyframes": auto_keyframes
            },
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            answer = result["answer"]
            references = result["references"]
            
            # 添加到历史
            history = history + [(question, answer)]
            
            # 格式化引用信息
            ref_info = "📌 引用信息:\n\n"
            
            # 时间范围
            if references["time_ranges"]:
                ref_info += "🕒 相关时间段:\n"
                for tr in references["time_ranges"]:
                    start = format_time(tr["start_time"])
                    end = format_time(tr["end_time"])
                    text_preview = tr["text"][:60] + "..." if len(tr["text"]) > 60 else tr["text"]
                    ref_info += f"  • {start} - {end}: {text_preview}\n"
                ref_info += "\n"
            
            # 关键帧
            if references["keyframes"]:
                ref_info += "🖼️ 使用的关键帧:\n"
                for kf in references["keyframes"]:
                    timestamp = format_time(kf["timestamp"])
                    ref_info += f"  • Frame {kf['frame_id']} ({timestamp})\n"
                ref_info += "\n"
            
            ref_info += f"💬 对话轮数: {result['history_length'] // 2}"
            
            return history, ref_info
        else:
            error = response.json().get("detail", "未知错误")
            return history, f"❌ 提问失败: {error}"
            
    except Exception as e:
        return history, f"❌ 错误: {str(e)}"


def end_session() -> str:
    """结束当前会话"""
    global current_session_id
    
    if not current_session_id:
        return "⚠️ 当前没有活动会话"
    
    try:
        response = requests.delete(
            f"{API_BASE}/analysis/chat/session/{current_session_id}",
            timeout=10
        )
        
        if response.status_code == 200:
            session_id = current_session_id
            current_session_id = None
            return f"✅ 会话 {session_id[:8]}... 已结束"
        else:
            return "❌ 结束会话失败"
            
    except Exception as e:
        return f"❌ 错误: {str(e)}"


def get_session_info() -> str:
    """获取当前会话信息"""
    global current_session_id
    
    if not current_session_id:
        return "⚠️ 当前没有活动会话"
    
    try:
        response = requests.get(
            f"{API_BASE}/analysis/chat/session/{current_session_id}",
            timeout=10
        )
        
        if response.status_code == 200:
            info = response.json()
            
            output = f"""📊 会话详情:

🆔 Session ID: {info['session_id']}
🎬 Video ID: {info['video_id']}
🕐 创建时间: {info['created_at']}
💬 对话轮数: {info['history_length'] // 2}
🖼️ 关键帧: {info['keyframes_count']}
📝 转录片段: {info['transcript_segments_count']}

📜 最近对话:
"""
            for msg in info['recent_messages'][-6:]:  # 显示最近 3 轮
                role = "👤 用户" if msg['role'] == 'user' else "🤖 助手"
                content = msg['content'][:100] + "..." if len(msg['content']) > 100 else msg['content']
                output += f"\n{role}: {content}"
            
            return output
        else:
            return "❌ 获取会话信息失败"
            
    except Exception as e:
        return f"❌ 错误: {str(e)}"


# 创建示例元数据
EXAMPLE_METADATA = {
    "transcript": {
        "oss_audio_url": "https://example.oss.com/audio.mp3",
        "language": "zh-CN",
        "overall_confidence": 0.95,
        "segments": [
            {
                "text": "欢迎来到今天的视频教程，我们将学习如何使用Python进行数据分析",
                "start_time": 0.0,
                "end_time": 5.2,
                "confidence": 0.98
            },
            {
                "text": "首先，让我们了解一下什么是数据分析以及为什么它很重要",
                "start_time": 5.2,
                "end_time": 10.5,
                "confidence": 0.96
            },
            {
                "text": "数据分析可以帮助我们从大量数据中提取有价值的信息和洞察",
                "start_time": 10.5,
                "end_time": 15.8,
                "confidence": 0.97
            },
            {
                "text": "接下来我们将介绍pandas库，这是Python中最流行的数据分析工具",
                "start_time": 15.8,
                "end_time": 22.3,
                "confidence": 0.95
            },
            {
                "text": "这个界面展示了pandas的基本操作，包括数据加载和清洗",
                "start_time": 22.3,
                "end_time": 28.6,
                "confidence": 0.94
            }
        ]
    },
    "keyframes": [
        {
            "frame_id": 1,
            "timestamp": 3.5,
            "oss_image_url": "https://example.oss.com/keyframe_1.jpg",
            "scene_description": "视频开场画面，标题展示"
        },
        {
            "frame_id": 2,
            "timestamp": 12.0,
            "oss_image_url": "https://example.oss.com/keyframe_2.jpg",
            "scene_description": "数据分析概念图解"
        },
        {
            "frame_id": 3,
            "timestamp": 25.0,
            "oss_image_url": "https://example.oss.com/keyframe_3.jpg",
            "scene_description": "pandas代码演示界面"
        }
    ]
}


# 创建 Gradio 界面
with gr.Blocks(title="Chat with Video - 演示", theme=gr.themes.Soft()) as demo:
    gr.Markdown("# 🎬 Chat with Video - 视频多轮对话演示")
    gr.Markdown("基于视频元数据（转录 + 关键帧）的智能问答系统")
    
    with gr.Tab("1️⃣ 启动会话"):
        gr.Markdown("### 步骤 1: 输入视频元数据并启动会话")
        
        with gr.Row():
            video_id_input = gr.Textbox(
                label="视频 ID",
                placeholder="例如: my_video_001",
                value="demo_video"
            )
        
        metadata_input = gr.Code(
            label="视频元数据 (JSON 格式)",
            language="json",
            value=json.dumps(EXAMPLE_METADATA, indent=2, ensure_ascii=False),
            lines=20
        )
        
        with gr.Row():
            start_btn = gr.Button("🚀 启动会话", variant="primary")
            load_example_btn = gr.Button("📝 加载示例数据")
        
        start_status = gr.Textbox(label="状态", interactive=False)
        session_info_display = gr.Textbox(
            label="会话信息",
            interactive=False,
            lines=10
        )
    
    with gr.Tab("2️⃣ 开始对话"):
        gr.Markdown("### 步骤 2: 与视频进行多轮对话")
        
        chatbot = gr.Chatbot(label="对话历史", height=400)
        
        with gr.Row():
            question_input = gr.Textbox(
                label="你的问题",
                placeholder="例如: 视频中在哪里讲了数据分析？",
                scale=4
            )
            submit_btn = gr.Button("💬 发送", variant="primary", scale=1)
        
        with gr.Accordion("高级选项", open=False):
            with gr.Row():
                keyframe_ids_input = gr.Textbox(
                    label="指定关键帧 ID（逗号分隔，用于视觉问答）",
                    placeholder="例如: 1,3,5",
                    scale=2
                )
                top_k_input = gr.Slider(
                    minimum=1,
                    maximum=10,
                    value=5,
                    step=1,
                    label="检索片段数量",
                    scale=1
                )
                auto_keyframes_input = gr.Checkbox(
                    label="自动匹配关键帧",
                    value=True,
                    scale=1
                )
        
        references_output = gr.Textbox(
            label="引用信息",
            interactive=False,
            lines=10
        )
        
        with gr.Row():
            clear_btn = gr.Button("🗑️ 清空对话")
            info_btn = gr.Button("ℹ️ 查看会话信息")
    
    with gr.Tab("3️⃣ 会话管理"):
        gr.Markdown("### 步骤 3: 管理会话")
        
        with gr.Row():
            refresh_info_btn = gr.Button("🔄 刷新会话信息")
            end_session_btn = gr.Button("⛔ 结束会话", variant="stop")
        
        session_detail = gr.Textbox(
            label="会话详情",
            interactive=False,
            lines=15
        )
        
        end_status = gr.Textbox(label="操作状态", interactive=False)
    
    with gr.Tab("📖 使用说明"):
        gr.Markdown("""
## 使用指南

### 1. 启动会话
1. 在「启动会话」标签页输入视频 ID
2. 粘贴或输入视频元数据（包含 transcript 和 keyframes）
3. 点击「启动会话」按钮
4. 查看会话信息确认成功

### 2. 开始对话
1. 切换到「开始对话」标签页
2. 在输入框中输入你的问题
3. （可选）在高级选项中指定关键帧 ID 进行视觉问答
4. 点击「发送」按钮
5. 查看回答和引用信息

### 3. 多轮对话
- 系统会自动保留对话历史
- 可以连续提问，进行深入讨论
- 每个问题都会结合转录文本和关键帧

### 4. 结束会话
- 在「会话管理」标签页点击「结束会话」
- 或关闭浏览器窗口（会话会在服务器保留）

---

## 问题示例

### 时间定位类问题
- "视频中在哪里讲了 XXX？"
- "关于 XXX 的内容大概在什么时间段？"
- "第 XX 分钟讲了什么？"

### 视觉问答类问题
- "这个界面有什么特点？"（需指定关键帧 ID）
- "这张图展示了什么内容？"
- "界面的设计风格是什么样的？"

### 内容总结类问题
- "这个视频主要讲了什么？"
- "XXX 部分的重点是什么？"
- "能总结一下 XXX 的内容吗？"

---

## 技术说明

- **模型**: Qwen3-VL-Plus (qwen-vl-plus)
- **上下文检索**: 基于关键词匹配
- **多模态输入**: 转录文本 + 关键帧图像
- **历史保留**: 最近 4 轮对话

---

## 注意事项

⚠️ **环境要求**:
- 后端服务必须运行（默认 http://localhost:8000）
- 需要设置 `QWEN_API_KEY` 环境变量

⚠️ **会话管理**:
- 会话存储在内存中，服务重启后会丢失
- 建议在使用完毕后手动结束会话

⚠️ **性能优化**:
- 指定关键帧 ID 可以加快响应速度
- 减少 top_k 值可以降低上下文长度

---

## API 文档

详细 API 文档请参考: `backend/app/tests/docs/CHAT_WITH_VIDEO_GUIDE.md`
        """)
    
    # 事件绑定
    load_example_btn.click(
        fn=lambda: json.dumps(EXAMPLE_METADATA, indent=2, ensure_ascii=False),
        outputs=metadata_input
    )
    
    start_btn.click(
        fn=start_chat_session,
        inputs=[video_id_input, metadata_input],
        outputs=[start_status, session_info_display]
    )
    
    submit_btn.click(
        fn=ask_question,
        inputs=[
            question_input,
            keyframe_ids_input,
            top_k_input,
            auto_keyframes_input,
            chatbot
        ],
        outputs=[chatbot, references_output]
    ).then(
        fn=lambda: "",
        outputs=question_input
    )
    
    question_input.submit(
        fn=ask_question,
        inputs=[
            question_input,
            keyframe_ids_input,
            top_k_input,
            auto_keyframes_input,
            chatbot
        ],
        outputs=[chatbot, references_output]
    ).then(
        fn=lambda: "",
        outputs=question_input
    )
    
    clear_btn.click(fn=lambda: [], outputs=chatbot)
    
    info_btn.click(fn=get_session_info, outputs=references_output)
    
    refresh_info_btn.click(fn=get_session_info, outputs=session_detail)
    
    end_session_btn.click(fn=end_session, outputs=end_status)


if __name__ == "__main__":
    print("=" * 60)
    print("Chat with Video - 演示界面")
    print("=" * 60)
    print(f"API Base URL: {API_BASE}")
    print("请确保后端服务已启动！")
    print("=" * 60)
    
    demo.launch(
        server_name="0.0.0.0",
        server_port=7861,
        share=False
    )
