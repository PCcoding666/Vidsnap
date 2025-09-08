"""
Gradio Interface for Simple Video Summarizer
Provides a web interface for video processing and summarization
"""
import gradio as gr
import logging
import os
import json
from typing import Dict, Any, List, Optional, Tuple
import tempfile
import shutil
from datetime import datetime
import threading
import time

from video_processing_pipeline import processing_pipeline

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def process_video_gradio(video_url: str, 
                        language: str,
                        granularity: str,
                        num_keyframes: int,
                        keyframe_method: str,
                        progress: gr.Progress) -> Tuple[str, str, str, str, List[str]]:
    """
    Process video and return results for Gradio interface
    
    Returns:
        Tuple of (status_message, metadata_json, transcript, summary, keyframe_paths)
    """
    try:
        logger.info(f"Processing video: {video_url}")
        
        # Validate inputs
        if not video_url or not video_url.strip():
            return "❌ 错误：请输入有效的视频URL", "", "", "", []
        
        # Start processing
        progress(0, desc="开始处理...")
        
        def progress_update(stage: str, prog: float):
            progress(prog / 100, desc=stage)
        
        result = processing_pipeline.process_video(
            video_url=video_url.strip(),
            language=language,
            granularity=granularity,
            num_keyframes=num_keyframes,
            keyframe_method=keyframe_method,
            progress_callback=progress_update
        )
        
        progress(1.0, desc="处理完成")
        
        # Format results
        status = result.get("status", "unknown")
        
        if status == "error":
            error_msg = result.get("error", "未知错误")
            return f"❌ 处理失败：{error_msg}", "", "", "", []
        
        # Extract results
        metadata = result.get("video_metadata", {})
        transcript = result.get("transcript", "")
        summary = result.get("summary", "")
        keyframes = result.get("keyframes", [])
        errors = result.get("errors", [])
        
        # Format status message
        if status == "success":
            status_msg = "✅ 处理成功完成！"
        elif status == "partial_success":
            status_msg = f"⚠️ 部分成功完成，但有一些错误：\n" + "\n".join(f"• {err}" for err in errors)
        else:
            status_msg = f"❌ 处理失败：{errors[0] if errors else '未知错误'}"
        
        # Format metadata
        metadata_str = ""
        if metadata:
            metadata_str = f"""📹 视频信息：
• 标题：{metadata.get('title', 'N/A')}
• 上传者：{metadata.get('uploader', 'N/A')}
• 时长：{metadata.get('duration_string', 'N/A')}
• 观看次数：{metadata.get('view_count', 'N/A')}
• 上传日期：{metadata.get('upload_date', 'N/A')}"""
        
        # Format transcript
        transcript_str = ""
        if transcript:
            transcript_str = f"📝 音频转录：\n{transcript}"
        else:
            transcript_str = "❌ 未能获取音频转录"
        
        # Format summary
        summary_str = ""
        if summary:
            summary_str = f"📋 视频摘要：\n{summary}"
        else:
            summary_str = "❌ 未能生成视频摘要"
        
        # Prepare keyframe paths for gallery
        keyframe_paths = [kf.get("local_path", "") for kf in keyframes if kf.get("local_path")]
        
        return status_msg, metadata_str, transcript_str, summary_str, keyframe_paths
        
    except Exception as e:
        logger.exception("Error processing video")
        return f"❌ 处理过程中发生错误：{str(e)}", "", "", "", []


def get_service_status() -> str:
    """Get status of all services"""
    try:
        info = processing_pipeline.get_processing_info()
        services = info.get("services_status", {})
        
        status_lines = ["🔧 服务状态："]
        
        # Video service
        if services.get("video", False):
            status_lines.append("✅ 视频下载服务：可用")
        else:
            status_lines.append("❌ 视频下载服务：不可用")
        
        # Speech service
        if services.get("speech", False):
            speech_info = info.get("speech_service", {})
            service_type = speech_info.get("service_type", "Unknown")
            status_lines.append(f"✅ 语音转录服务：可用 ({service_type})")
        else:
            status_lines.append("❌ 语音转录服务：不可用 (请检查API密钥)")
        
        # LLM service
        if services.get("llm", False):
            llm_info = info.get("llm_service", {})
            primary_service = llm_info.get("primary_service", "Unknown")
            status_lines.append(f"✅ 摘要生成服务：可用 ({primary_service})")
        else:
            status_lines.append("❌ 摘要生成服务：不可用 (请检查API密钥)")
        
        return "\n".join(status_lines)
        
    except Exception as e:
        return f"❌ 获取服务状态失败：{str(e)}"


def create_gradio_interface():
    """Create and configure the Gradio interface"""
    
    # Custom CSS
    custom_css = """
    .gradio-container {
        max-width: 1200px !important;
    }
    .main-header {
        text-align: center;
        margin-bottom: 2rem;
    }
    .status-box {
        border: 1px solid #ddd;
        border-radius: 8px;
        padding: 1rem;
        margin: 1rem 0;
        background-color: #f9f9f9;
    }
    .result-section {
        margin-top: 2rem;
    }
    """
    
    with gr.Blocks(css=custom_css, title="视频摘要器", theme=gr.themes.Soft()) as app:
        
        # Header
        with gr.Row():
            gr.HTML("""
                <div class="main-header">
                    <h1>🎬 简化版视频摘要器</h1>
                    <p>上传视频URL，自动生成转录和摘要</p>
                </div>
            """)
        
        # Service status
        with gr.Row():
            service_status = gr.Textbox(
                label="🔧 服务状态",
                value=get_service_status(),
                interactive=False,
                lines=5
            )
            
            refresh_status_btn = gr.Button("🔄 刷新状态", variant="secondary")
        
        # Input section
        with gr.Row():
            with gr.Column(scale=2):
                video_url = gr.Textbox(
                    label="📹 视频URL",
                    placeholder="请输入YouTube或其他视频平台的URL...",
                    lines=2
                )
                
                with gr.Row():
                    language = gr.Dropdown(
                        label="🌐 语言",
                        choices=[("中文", "zh"), ("英文", "en"), ("自动检测", "auto")],
                        value="zh"
                    )
                    
                    granularity = gr.Dropdown(
                        label="📋 摘要详细程度",
                        choices=[("简短", "short"), ("中等", "medium"), ("详细", "detailed")],
                        value="medium"
                    )
                
                with gr.Row():
                    num_keyframes = gr.Slider(
                        label="🖼️ 关键帧数量",
                        minimum=5,
                        maximum=20,
                        value=10,
                        step=1
                    )
                    
                    keyframe_method = gr.Dropdown(
                        label="🎯 关键帧提取方法",
                        choices=[("均匀采样", "uniform"), ("时间间隔", "interval"), ("场景检测", "scene")],
                        value="uniform"
                    )
                
                process_btn = gr.Button("🚀 开始处理", variant="primary", size="lg")
            
            with gr.Column(scale=1):
                gr.HTML("""
                    <div class="status-box">
                        <h3>📋 使用说明</h3>
                        <ol>
                            <li>输入视频URL（支持YouTube等平台）</li>
                            <li>选择处理参数</li>
                            <li>点击"开始处理"</li>
                            <li>等待处理完成，查看结果</li>
                        </ol>
                        <p><strong>注意：</strong>需要设置相应的API密钥才能使用语音转录和摘要功能。</p>
                    </div>
                """)
        
        # Results section
        gr.HTML("<div class='result-section'><h2>📊 处理结果</h2></div>")
        
        with gr.Row():
            status_output = gr.Textbox(
                label="📈 处理状态",
                interactive=False,
                lines=3
            )
        
        with gr.Row():
            with gr.Column():
                metadata_output = gr.Textbox(
                    label="📹 视频信息",
                    interactive=False,
                    lines=8
                )
            
            with gr.Column():
                transcript_output = gr.Textbox(
                    label="📝 音频转录",
                    interactive=False,
                    lines=8
                )
        
        with gr.Row():
            summary_output = gr.Textbox(
                label="📋 视频摘要",
                interactive=False,
                lines=10
            )
        
        with gr.Row():
            keyframes_gallery = gr.Gallery(
                label="🖼️ 关键帧",
                show_label=True,
                elem_id="keyframes",
                columns=4,
                rows=2,
                height="auto"
            )
        
        # Event handlers
        refresh_status_btn.click(
            fn=get_service_status,
            outputs=service_status
        )
        
        process_btn.click(
            fn=process_video_gradio,
            inputs=[video_url, language, granularity, num_keyframes, keyframe_method],
            outputs=[status_output, metadata_output, transcript_output, summary_output, keyframes_gallery],
            show_progress=True
        )
        
        # Examples
        with gr.Row():
            gr.Examples(
                examples=[
                    ["https://www.youtube.com/watch?v=dQw4w9WgXcQ", "en", "medium", 10, "uniform"],
                    ["https://youtu.be/jNQXAC9IVRw", "zh", "detailed", 15, "scene"],
                ],
                inputs=[video_url, language, granularity, num_keyframes, keyframe_method],
                label="📝 示例URL"
            )
    
    return app


def launch_app():
    """Launch the Gradio application"""
    app = create_gradio_interface()
    
    # Get port from environment or use default
    port = int(os.getenv("PORT", 7860))
    
    logger.info(f"Launching Gradio app on port {port}")
    
    app.launch(
        server_port=port,
        server_name="0.0.0.0",
        share=False,
        debug=False,
        show_error=True
    )


if __name__ == "__main__":
    launch_app()