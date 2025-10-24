"""
YouTube 视频智能总结系统 - Gradio Web 界面
提供友好的交互界面，支持 YouTube URL 和本地视频文件上传
"""
import gradio as gr
import asyncio
import json
import tempfile
import os
import traceback
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime
from dataclasses import asdict

# 导入后端服务
import sys
sys.path.insert(0, str(Path(__file__).parent))

from app.services.pipeline_service import pipeline
from app.services.chat_service import video_chat_service
from app.core.logging import logger
from app.models.analysis import VideoMetadata, VideoSummary


# 全局变量：存储当前聊天会话
current_chat_session_id: Optional[str] = None
current_video_metadata: Optional[dict] = None
current_video_id: Optional[str] = None


class GradioProgressCallback:
    """Gradio 进度回调处理器"""
    
    def __init__(self, progress: gr.Progress):
        self.progress = progress
        self.current_step = 0
        self.total_steps = 7
        self.step_weights = {
            "初始化": 0.0,
            "下载/上传视频": 0.15,
            "提取关键帧": 0.30,
            "上传关键帧到OSS": 0.45,
            "转录音频": 0.60,
            "生成AI总结": 0.80,
            "上传结果": 0.95,
            "完成": 1.0
        }
    
    def __call__(self, message: str):
        """更新进度"""
        # 根据消息内容估算进度
        progress_value = 0.0
        for step, weight in self.step_weights.items():
            if step in message or step.lower() in message.lower():
                progress_value = weight
                break
        
        self.progress(progress_value, desc=message)
        logger.info(f"[进度] {message}")


async def process_video_async(
    input_mode: str,
    youtube_url: str,
    video_file: Optional[Any],
    language: str,
    granularity: str,
    num_keyframes: int,
    progress: gr.Progress = gr.Progress()
) -> Tuple:
    """
    异步处理视频
    
    Returns:
        Tuple: (简要总结, 标准总结, 详细总结, 转录文本, 关键帧列表, 视频信息, 下载链接HTML, 状态消息)
    """
    try:
        # 创建进度回调
        progress_callback = GradioProgressCallback(progress)
        progress_callback("🚀 开始处理视频...")
        
        # 验证输入
        video_path = None
        yt_url = None
        
        if input_mode == "YouTube URL":
            if not youtube_url or not youtube_url.strip():
                return ("", "", "", "", [], "", "", "❌ 错误：请输入有效的 YouTube URL")
            yt_url = youtube_url.strip()
            progress_callback(f"📥 准备下载 YouTube 视频: {yt_url}")
        else:
            if video_file is None:
                return ("", "", "", "", [], "", "", "❌ 错误：请上传视频文件")
            
            # 处理上传的文件
            if hasattr(video_file, 'name'):
                video_path = video_file.name
            else:
                video_path = str(video_file)
            
            # 验证文件格式
            file_ext = Path(video_path).suffix.lower()
            if file_ext not in ['.mp4', '.avi', '.mov', '.mkv']:
                return ("", "", "", "", [], "", "", f"❌ 错误：不支持的文件格式 {file_ext}，请上传 MP4、AVI、MOV 或 MKV 格式")
            
            progress_callback(f"📤 准备处理上传的视频文件: {Path(video_path).name}")
        
        # 调用处理管道
        progress_callback("⚙️ 启动处理管道...")
        
        # 设置语言参数
        lang_map = {
            "自动检测": "auto",
            "中文": "zh",
            "英文": "en",
            "韩文": "ko"
        }
        lang_code = lang_map.get(language, "auto")
        
        # 设置粒度参数
        gran_map = {
            "简要": "brief",
            "标准": "standard",
            "详细": "detailed"
        }
        gran_code = gran_map.get(granularity, "standard")
        
        # 调用后端处理
        result = await pipeline.process_video_with_summary(
            video_file=video_path,
            youtube_url=yt_url,
            granularity=gran_code,
            progress_callback=progress_callback
        )
        
        # 检查处理结果
        if result["status"] != "success":
            error_msg = result.get("error", "未知错误")
            progress_callback(f"❌ 处理失败: {error_msg}")
            return ("", "", "", "", [], "", "", f"❌ 处理失败: {error_msg}")
        
        # 提取结果数据
        video_id = result["video_id"]
        metadata: VideoMetadata = result["metadata"]
        video_summary: Optional[VideoSummary] = result.get("video_summary")
        
        progress_callback("📊 整理结果数据...")
        
        # 1. 提取总结内容
        brief_summary = ""
        standard_summary = ""
        detailed_summary = ""
        
        if video_summary:
            brief_summary = video_summary.brief_summary or "无简要总结"
            standard_summary = video_summary.standard_summary or "无标准总结"
            detailed_summary = video_summary.detailed_summary or ""
        else:
            brief_summary = "⚠️ LLM 总结服务不可用"
            standard_summary = "⚠️ LLM 总结服务不可用，请检查 API 配置"
        
        # 2. 提取转录文本
        transcript_text = ""
        if metadata.transcript and metadata.transcript.segments:
            transcript_lines = []
            for segment in metadata.transcript.segments:
                start_str = format_timestamp(segment.start_time)
                end_str = format_timestamp(segment.end_time)
                transcript_lines.append(f"[{start_str} - {end_str}] {segment.text}")
            transcript_text = "\n".join(transcript_lines)
        else:
            transcript_text = "⚠️ 无转录内容"
        
        # 3. 提取关键帧
        keyframes_gallery = []
        if metadata.keyframes:
            for kf in metadata.keyframes:
                if kf.oss_image_url:
                    # Gradio Gallery 格式: (url, caption)
                    caption = f"帧 #{kf.frame_id} | {format_timestamp(kf.timestamp)}\n{kf.scene_description[:100]}..."
                    keyframes_gallery.append((kf.oss_image_url, caption))
        
        # 4. 生成视频信息
        video_info_html = f"""
        <div style='padding: 15px; background: #f5f5f5; border-radius: 8px;'>
            <h3 style='margin-top: 0;'>📹 视频信息</h3>
            <p><b>标题:</b> {metadata.title}</p>
            <p><b>时长:</b> {format_duration(metadata.duration)}</p>
            <p><b>视频ID:</b> {video_id}</p>
            <p><b>处理时间:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
            <p><b>语言:</b> {metadata.transcript.language if metadata.transcript else 'N/A'}</p>
            <p><b>分辨率:</b> {metadata.video_resolution or 'N/A'}</p>
            <p><b>文件大小:</b> {format_filesize(metadata.video_size) if metadata.video_size else 'N/A'}</p>
        </div>
        """
        
        # 5. 生成下载链接
        download_html = f"""
        <div style='padding: 15px; background: #e8f4f8; border-radius: 8px;'>
            <h3 style='margin-top: 0;'>💾 下载资源</h3>
        """
        
        if metadata.oss_video_url:
            download_html += f"<p>📹 <a href='{metadata.oss_video_url}' target='_blank'>下载原视频</a></p>"
        
        if metadata.transcript and metadata.transcript.oss_audio_url:
            download_html += f"<p>🎵 <a href='{metadata.transcript.oss_audio_url}' target='_blank'>下载音频文件</a></p>"
        
        if metadata.metadata_oss_url:
            download_html += f"<p>📄 <a href='{metadata.metadata_oss_url}' target='_blank'>下载元数据 JSON</a></p>"
        
        download_html += "</div>"
        
        # 6. 生成状态消息
        status_msg = f"✅ 处理完成！视频ID: {video_id}"
        if video_summary:
            status_msg += f" | 生成了 {len(video_summary.keyframe_descriptions)} 个关键帧描述"
        
        progress_callback("✅ 全部完成！")
        
        # 7. 保存 metadata 到全局变量（用于聊天）
        global current_video_metadata, current_video_id
        current_video_metadata = asdict(metadata)
        current_video_id = video_id
        
        return (
            brief_summary,
            standard_summary,
            detailed_summary,
            transcript_text,
            keyframes_gallery,
            video_info_html,
            download_html,
            status_msg
        )
        
    except Exception as e:
        error_msg = f"处理异常: {str(e)}\n{traceback.format_exc()}"
        logger.exception(error_msg)
        return ("", "", "", "", [], "", "", f"❌ {error_msg}")


def process_video_wrapper(*args, **kwargs):
    """同步包装器，用于 Gradio"""
    return asyncio.run(process_video_async(*args, **kwargs))


def format_timestamp(seconds: float) -> str:
    """格式化时间戳"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    else:
        return f"{minutes:02d}:{secs:02d}"


def format_duration(seconds: float) -> str:
    """格式化时长"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    
    parts = []
    if hours > 0:
        parts.append(f"{hours}小时")
    if minutes > 0:
        parts.append(f"{minutes}分钟")
    if secs > 0 or not parts:
        parts.append(f"{secs}秒")
    
    return " ".join(parts)


def format_filesize(size_bytes: float) -> str:
    """格式化文件大小"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} TB"


def update_input_visibility(input_mode: str):
    """根据输入模式更新控件可见性"""
    if input_mode == "YouTube URL":
        return (
            gr.update(visible=True),   # youtube_url
            gr.update(visible=False)   # video_file
        )
    else:
        return (
            gr.update(visible=False),  # youtube_url
            gr.update(visible=True)    # video_file
        )


def start_chat_session() -> Tuple[str, str]:
    """
    启动聊天会话
    
    Returns:
        (chat_status, chat_info)
    """
    global current_chat_session_id, current_video_metadata, current_video_id
    
    if not current_video_id or not current_video_metadata:
        return "❌ 错误", "请先处理视频后再启动聊天会话"
    
    try:
        # 调用聊天服务启动会话
        result = video_chat_service.start_session(
            video_id=current_video_id,
            metadata=current_video_metadata
        )
        
        if result.get("status") == "success":
            current_chat_session_id = result["session_id"]
            
            info = f"""✅ 聊天会话已启动！

📋 会话信息:
- Session ID: {current_chat_session_id[:16]}...
- Video ID: {result['video_id']}
- 关键帧数量: {result['keyframes_count']}
- 转录片段数量: {result['transcript_segments_count']}

💬 现在可以开始提问了！
"""
            return "✅ 会话已启动", info
        else:
            error = result.get("error", "未知错误")
            return "❌ 启动失败", f"启动失败: {error}"
    
    except Exception as e:
        logger.exception(f"启动聊天会话失败: {e}")
        return "❌ 错误", f"错误: {str(e)}"


def ask_question(question: str, history: List[Tuple[str, str]]) -> Tuple[List[Tuple[str, str]], str]:
    """
    在聊天会话中提问
    
    Args:
        question: 用户问题
        history: 对话历史
        
    Returns:
        (更新后的对话历史, 引用信息)
    """
    global current_chat_session_id
    
    if not current_chat_session_id:
        return history, "❌ 错误: 请先启动聊天会话"
    
    if not question or not question.strip():
        return history, "❌ 错误: 请输入问题"
    
    try:
        # 异步调用聊天服务
        result = asyncio.run(
            video_chat_service.ask_question(
                session_id=current_chat_session_id,
                question=question.strip(),
                top_k=5,
                auto_keyframes=False  # 禁用自动关键帧，避免 OSS URL 问题
            )
        )
        
        if result.get("status") == "success":
            answer = result["answer"]
            references = result["references"]
            
            # 更新对话历史
            history = history + [(question, answer)]
            
            # 格式化引用信息
            ref_text = "📋 引用信息:\n\n"
            
            # 时间范围
            if references["time_ranges"]:
                ref_text += "🕒 相关时间段:\n"
                for tr in references["time_ranges"][:5]:  # 最多显示5个
                    start = format_timestamp(tr["start_time"])
                    end = format_timestamp(tr["end_time"])
                    text_preview = tr["text"][:50] + "..." if len(tr["text"]) > 50 else tr["text"]
                    ref_text += f"  • {start} - {end}: {text_preview}\n"
                ref_text += "\n"
            
            # 关键帧
            if references["keyframes"]:
                ref_text += "🖼️ 使用的关键帧:\n"
                for kf in references["keyframes"]:
                    timestamp = format_timestamp(kf["timestamp"])
                    ref_text += f"  • Frame {kf['frame_id']} ({timestamp})\n"
                ref_text += "\n"
            
            ref_text += f"💬 对话轮数: {result['history_length'] // 2}"
            
            return history, ref_text
        else:
            error = result.get("error", "未知错误")
            return history, f"❌ 提问失败: {error}"
    
    except Exception as e:
        logger.exception(f"聊天提问失败: {e}")
        return history, f"❌ 错误: {str(e)}"


def create_gradio_interface():
    """创建 Gradio 界面"""
    
    # 自定义 CSS
    custom_css = """
    .gradio-container {
        max-width: 1400px !important;
    }
    .summary-card {
        padding: 15px;
        border-radius: 8px;
        margin: 10px 0;
    }
    .brief-summary {
        background: #e3f2fd;
        font-size: 18px;
        font-weight: 500;
    }
    .standard-summary {
        background: #f3e5f5;
    }
    .detailed-summary {
        background: #fff3e0;
    }
    """
    
    with gr.Blocks(
        title="YouTube 视频智能总结系统",
        theme=gr.themes.Soft(),
        css=custom_css
    ) as app:
        
        gr.Markdown("""
        # 🎬 YouTube 视频智能总结系统
        
        基于阿里云 AI 服务的智能视频分析平台，支持：
        - 🎥 YouTube 视频下载与本地文件上传
        - 🖼️ 关键帧自动提取
        - 🎤 高精度音频转录（SenseVoice）
        - 🤖 智能内容总结（Qwen3-VL-Flash）
        """)
        
        with gr.Tabs() as tabs:
            
            # ===== 标签页 1: 输入与配置 =====
            with gr.Tab("📥 输入与配置", id=0):
                
                gr.Markdown("### 1️⃣ 选择输入方式")
                input_mode = gr.Radio(
                    choices=["YouTube URL", "本地视频上传"],
                    value="YouTube URL",
                    label="输入方式",
                    info="选择视频来源"
                )
                
                gr.Markdown("### 2️⃣ 提供视频")
                
                youtube_url = gr.Textbox(
                    label="YouTube 视频链接",
                    placeholder="例如: https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                    visible=True
                )
                
                video_file = gr.File(
                    label="上传视频文件",
                    file_types=[".mp4", ".avi", ".mov", ".mkv"],
                    type="filepath",
                    visible=False
                )
                
                # 绑定输入模式切换事件
                input_mode.change(
                    fn=update_input_visibility,
                    inputs=[input_mode],
                    outputs=[youtube_url, video_file]
                )
                
                gr.Markdown("### 3️⃣ 处理参数")
                
                with gr.Row():
                    language = gr.Dropdown(
                        choices=["自动检测", "中文", "英文", "韩文"],
                        value="自动检测",
                        label="语言选择"
                    )
                    
                    granularity = gr.Dropdown(
                        choices=["简要", "标准", "详细"],
                        value="标准",
                        label="总结粒度"
                    )
                
                num_keyframes = gr.Slider(
                    minimum=5,
                    maximum=20,
                    value=10,
                    step=1,
                    label="关键帧数量",
                    info="提取的关键帧数量（更多帧=更详细，但处理时间更长）"
                )
                
                gr.Markdown("### 4️⃣ 开始处理")
                
                process_btn = gr.Button(
                    "🚀 开始分析",
                    variant="primary",
                    size="lg"
                )
                
                status_msg = gr.Textbox(
                    label="状态",
                    interactive=False,
                    show_label=True
                )
            
            # ===== 标签页 2: 结果展示 =====
            with gr.Tab("📊Dynamic 结果展示", id=1):
                
                with gr.Row():
                    # 左列：文本信息
                    with gr.Column(scale=1):
                        gr.Markdown("## 📝 内容总结")
                        
                        brief_summary = gr.Textbox(
                            label="📝 简要总结",
                            lines=3,
                            interactive=False,
                            elem_classes=["summary-card", "brief-summary"]
                        )
                        
                        standard_summary = gr.Textbox(
                            label="📖 标准总结",
                            lines=8,
                            interactive=False,
                            elem_classes=["summary-card", "standard-summary"]
                        )
                        
                        detailed_summary = gr.Textbox(
                            label="📚 详细总结",
                            lines=12,
                            interactive=False,
                            elem_classes=["summary-card", "detailed-summary"]
                        )
                        
                        transcript_text = gr.Textbox(
                            label="🎤 音频转录",
                            lines=10,
                            interactive=False
                        )
                    
                    # 右列：多媒体展示
                    with gr.Column(scale=1):
                        gr.Markdown("## 🖼️ 关键帧展示")
                        
                        keyframes_gallery = gr.Gallery(
                            label="关键帧",
                            columns=3,
                            height="auto",
                            object_fit="contain"
                        )
                        
                        video_info_html = gr.HTML(
                            label="视频信息"
                        )
                        
                        download_html = gr.HTML(
                            label="下载链接"
                        )
                
                # 分隔线
                gr.Markdown("---")
                
                # 聊天区域
                gr.Markdown("## 💬 与视频对话")
                gr.Markdown("基于视频内容的智能问答，支持多轮对话和时间定位")
                
                with gr.Row():
                    chat_start_btn = gr.Button(
                        "🚀 启动聊天会话",
                        variant="primary",
                        size="sm"
                    )
                
                with gr.Row():
                    with gr.Column(scale=1):
                        chat_status = gr.Textbox(
                            label="会话状态",
                            interactive=False,
                            max_lines=1
                        )
                    with gr.Column(scale=2):
                        chat_info = gr.Textbox(
                            label="会话信息",
                            interactive=False,
                            lines=6
                        )
                
                chatbot = gr.Chatbot(
                    label="对话历史",
                    height=400,
                    show_label=True
                )
                
                with gr.Row():
                    question_input = gr.Textbox(
                        label="你的问题",
                        placeholder="例如：视频中在哪里讲了XXX？",
                        scale=4
                    )
                    send_btn = gr.Button(
                        "💬 发送",
                        variant="primary",
                        scale=1
                    )
                
                chat_references = gr.Textbox(
                    label="引用信息",
                    interactive=False,
                    lines=8
                )
                
                with gr.Row():
                    clear_chat_btn = gr.Button("🗑️ 清空对话", size="sm")
                
                gr.Markdown("""
                ### 💡 使用提示
                
                - **时间定位类问题**: "视频中在哪里讲了XXX？" → 系统会返回具体时间段
                - **内容总结类问题**: "这个视频主要讲什么？" → 基于转录和关键帧总结
                - **多轮对话**: 支持连续追问，系统会保留上下文
                """)
        
        # 绑定处理按钮
        process_btn.click(
            fn=process_video_wrapper,
            inputs=[
                input_mode,
                youtube_url,
                video_file,
                language,
                granularity,
                num_keyframes
            ],
            outputs=[
                brief_summary,
                standard_summary,
                detailed_summary,
                transcript_text,
                keyframes_gallery,
                video_info_html,
                download_html,
                status_msg
            ]
        )
        
        # 绑定聊天功能
        chat_start_btn.click(
            fn=start_chat_session,
            outputs=[chat_status, chat_info]
        )
        
        send_btn.click(
            fn=ask_question,
            inputs=[question_input, chatbot],
            outputs=[chatbot, chat_references]
        ).then(
            fn=lambda: "",
            outputs=question_input
        )
        
        question_input.submit(
            fn=ask_question,
            inputs=[question_input, chatbot],
            outputs=[chatbot, chat_references]
        ).then(
            fn=lambda: "",
            outputs=question_input
        )
        
        clear_chat_btn.click(
            fn=lambda: [],
            outputs=chatbot
        )
        
        # 添加使用提示
        gr.Markdown("""
        ---
        ### 💡 使用提示
        
        - **YouTube 模式**: 直接输入视频链接，系统会自动下载并处理
        - **上传模式**: 支持本地视频文件，推荐使用 MP4 格式
        - **处理时间**: 根据视频长度，通常需要 1-5 分钟
        - **最佳效果**: 推荐 5-15 分钟的视频，语音清晰
        
        ### 🔧 技术支持
        
        - SenseVoice: 高精度音频转录
        - Qwen3-VL-Flash: 多模态视频理解
        - 阿里云 OSS: 云端存储
        """)
    
    return app


def main():
    """启动 Gradio 应用"""
    logger.info("=" * 60)
    logger.info("启动 YouTube 视频智能总结系统 - Gradio Web 界面")
    logger.info("=" * 60)
    
    # 检查服务可用性
    services_status = pipeline.check_services_availability()
    logger.info("服务状态检查:")
    for service, available in services_status.items():
        status = "✅ 可用" if available else "❌ 不可用"
        logger.info(f"  - {service}: {status}")
    
    # 创建并启动界面
    app = create_gradio_interface()
    
    # 从环境变量接收启动参数（由 run_gradio.sh 注入）
    server_name = os.getenv("GRADIO_HOST", "0.0.0.0")
    requested_port = int(os.getenv("GRADIO_PORT", "7860"))
    share_env = os.getenv("GRADIO_SHARE", "false").lower()
    share_flag = True if share_env in ["1", "true", "yes"] else False

    # 端口自动回退：从请求端口起最多尝试 20 个端口
    selected_port = None
    max_attempts = 20
    for i in range(max_attempts):
        try_port = requested_port + i
        try:
            logger.info("\n🚀 正在启动 Gradio 服务器...")
            logger.info(f"📱 本地访问地址: http://127.0.0.1:{try_port}")
            logger.info(f"🌐 网络访问地址: http://{server_name}:{try_port}")
            logger.info("\n按 Ctrl+C 停止服务器\n")

            app.launch(
                server_name=server_name,
                server_port=try_port,
                share=share_flag,  # 设置为 True 可生成公网链接
                show_error=True,
                inbrowser=False  # 自动打开浏览器
            )
            selected_port = try_port
            break
        except OSError as e:
            msg = str(e)
            if "address already in use" in msg or "Cannot find empty port" in msg:
                logger.warning(f"端口 {try_port} 已被占用，尝试下一个端口...")
                continue
            else:
                raise

    if selected_port is None:
        raise OSError(f"无法找到可用端口，从 {requested_port} 开始尝试 {max_attempts} 次均失败。")


if __name__ == "__main__":
    main()
