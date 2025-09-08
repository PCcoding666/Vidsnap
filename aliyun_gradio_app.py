"""
阿里云视频分析平台 - Gradio Web界面
支持双输入源、实时进度显示、关键帧时间轴、交互分析
"""
import gradio as gr
import os
import asyncio
import json
from datetime import datetime
from typing import Optional, List, Dict, Any

# 导入我们的服务
from aliyun_video_pipeline import pipeline
from aliyun_oss_service import oss_service
from openai_speech_service import speech_service  # 使用OpenAI语音服务

# 全局变量存储当前处理的视频信息
current_video_metadata = {}


def create_aliyun_video_analysis_interface():
    """创建阿里云视频分析平台的Gradio界面"""
    
    with gr.Blocks(
        title="阿里云视频分析平台",
        theme=gr.themes.Soft(),
        css="""
        .gradio-container {
            max-width: 1200px !important;
        }
        .keyframe-gallery img {
            border-radius: 8px;
            border: 2px solid transparent;
            transition: border-color 0.3s;
        }
        .keyframe-gallery img:hover {
            border-color: #2196F3;
        }
        """
    ) as interface:
        
        gr.Markdown("""
        # 🎬 阿里云视频分析平台
        
        支持视频上传或YouTube链接，自动提取关键帧和音频转录，基于阿里云服务的智能视频分析平台。
        """)
        
        # 服务状态检查
        with gr.Row():
            with gr.Column():
                service_status = gr.HTML(value=get_service_status_html())
                gr.Button("刷新服务状态", size="sm").click(
                    fn=lambda: get_service_status_html(),
                    outputs=[service_status]
                )
        
        # 主要功能区域
        with gr.Tabs() as tabs:
            
            # Tab 1: 视频处理
            with gr.Tab("📹 视频处理", id="processing"):
                
                with gr.Row():
                    with gr.Column(scale=1):
                        # 输入源选择
                        input_type = gr.Radio(
                            choices=["上传视频文件", "YouTube URL"],
                            value="上传视频文件",
                            label="📥 视频来源"
                        )
                        
                        # 视频文件上传
                        video_upload = gr.File(
                            file_types=[".mp4", ".avi", ".mov", ".mkv", ".webm"],
                            label="🎥 上传视频文件",
                            visible=True
                        )
                        
                        # YouTube URL输入
                        youtube_url = gr.Textbox(
                            label="🔗 YouTube视频URL",
                            placeholder="https://www.youtube.com/watch?v=...",
                            visible=False
                        )
                        
                        # 处理按钮
                        process_btn = gr.Button(
                            "🚀 开始处理",
                            variant="primary",
                            size="lg"
                        )
                        
                        # 重置按钮
                        reset_btn = gr.Button(
                            "🔄 重置",
                            variant="secondary",
                            size="sm"
                        )
                    
                    with gr.Column(scale=2):
                        # 处理状态显示
                        status_display = gr.Textbox(
                            label="📊 处理状态",
                            interactive=False,
                            lines=2,
                            value="等待开始处理..."
                        )
                        
                        # 处理结果
                        result_display = gr.JSON(
                            label="✅ 处理结果",
                            visible=False
                        )
                        
                        # 错误信息
                        error_display = gr.Textbox(
                            label="❌ 错误信息",
                            visible=False,
                            lines=3
                        )
            
            # Tab 2: 交互分析
            with gr.Tab("🔍 交互分析", id="analysis"):
                
                with gr.Row():
                    with gr.Column(scale=1):
                        # 视频选择
                        video_selector = gr.Dropdown(
                            label="📼 选择视频",
                            choices=[],
                            interactive=True
                        )
                        
                        # 视频信息显示
                        video_info_display = gr.JSON(
                            label="📋 视频信息",
                            visible=False
                        )
                        
                        # 搜索功能
                        with gr.Group():
                            gr.Markdown("### 🔍 转录内容搜索")
                            search_keyword = gr.Textbox(
                                label="搜索关键词",
                                placeholder="在转录文本中搜索..."
                            )
                            search_btn = gr.Button("搜索", size="sm")
                            search_results = gr.JSON(
                                label="搜索结果",
                                visible=False
                            )
                    
                    with gr.Column(scale=2):
                        # 关键帧时间轴
                        keyframes_gallery = gr.Gallery(
                            label="🎬 关键帧时间轴（点击查看详情）",
                            show_label=True,
                            elem_id="keyframe-gallery",
                            columns=5,
                            rows=2,
                            object_fit="cover",
                            height="auto"
                        )
                        
                        # 选中关键帧信息
                        selected_frame_info = gr.JSON(
                            label="🖼️ 选中关键帧信息",
                            visible=False
                        )
                
                with gr.Row():
                    with gr.Column():
                        # 转录内容显示
                        transcript_display = gr.HTML(
                            label="📝 音频转录内容",
                            value="<p>请先选择视频...</p>"
                        )
            
            # Tab 3: 设置
            with gr.Tab("⚙️ 设置", id="settings"):
                
                with gr.Row():
                    with gr.Column():
                        gr.Markdown("### 🔧 阿里云服务配置")
                        
                        with gr.Group():
                            gr.Markdown("请在环境变量中设置以下配置：")
                            gr.Textbox(
                                value="""
# 阿里云访问密钥
ALIYUN_ACCESS_KEY_ID=your_access_key_id
ALIYUN_ACCESS_KEY_SECRET=your_access_key_secret

# OSS配置
ALIYUN_OSS_ENDPOINT=https://oss-cn-hangzhou.aliyuncs.com
ALIYUN_OSS_BUCKET=your_bucket_name

# 智能语音服务
ALIYUN_SPEECH_APP_KEY=your_speech_app_key
""",
                                lines=10,
                                label="环境变量配置",
                                interactive=False
                            )
                        
                        # 配置检查
                        config_check_btn = gr.Button("检查配置", variant="secondary")
                        config_status = gr.HTML(value="点击检查配置状态")
                
                with gr.Row():
                    with gr.Column():
                        gr.Markdown("### 📊 使用统计")
                        usage_stats = gr.HTML(value="暂无使用统计")
        
        # 事件处理函数
        def toggle_input_type(input_type):
            """切换输入类型"""
            if input_type == "上传视频文件":
                return gr.update(visible=True), gr.update(visible=False)
            else:
                return gr.update(visible=False), gr.update(visible=True)
        
        def reset_interface():
            """重置界面"""
            return (
                gr.update(value=None),  # video_upload
                gr.update(value=""),    # youtube_url
                gr.update(value="等待开始处理..."),  # status_display
                gr.update(visible=False),  # result_display
                gr.update(visible=False),  # error_display
                []  # keyframes_gallery
            )
        
        async def process_video_async(video_file, youtube_url, input_type):
            """异步处理视频"""
            try:
                # 检查输入
                if input_type == "上传视频文件" and not video_file:
                    return {
                        "status": "error",
                        "error": "请上传视频文件"
                    }, "❌ 请上传视频文件", gr.update(visible=False), gr.update(visible=True, value="请上传视频文件"), []
                
                if input_type == "YouTube URL" and not youtube_url:
                    return {
                        "status": "error", 
                        "error": "请输入YouTube URL"
                    }, "❌ 请输入YouTube URL", gr.update(visible=False), gr.update(visible=True, value="请输入YouTube URL"), []
                
                # 进度回调函数
                def update_progress(message):
                    return f"⏳ {message}"
                
                # 准备参数
                video_path = video_file.name if video_file else None
                url = youtube_url if input_type == "YouTube URL" else None
                
                # 处理视频
                result = await pipeline.process_video(
                    video_file=video_path,
                    youtube_url=url,
                    progress_callback=update_progress
                )
                
                if result["status"] == "success":
                    # 保存当前视频metadata
                    global current_video_metadata
                    current_video_metadata[result["video_id"]] = result["metadata"]
                    
                    # 准备关键帧图片
                    keyframes_images = []
                    if result["metadata"].keyframes:
                        for kf in result["metadata"].keyframes:
                            if kf.oss_image_url:
                                keyframes_images.append((kf.oss_image_url, f"帧{kf.frame_id}: {kf.timestamp:.1f}s"))
                    
                    return (
                        result,
                        "✅ 处理完成！",
                        gr.update(visible=True, value=result),
                        gr.update(visible=False),
                        keyframes_images
                    )
                else:
                    return (
                        result,
                        f"❌ 处理失败: {result.get('error', '未知错误')}",
                        gr.update(visible=False),
                        gr.update(visible=True, value=result.get('error', '未知错误')),
                        []
                    )
                    
            except Exception as e:
                error_msg = f"处理异常: {str(e)}"
                return (
                    {"status": "error", "error": error_msg},
                    f"❌ {error_msg}",
                    gr.update(visible=False),
                    gr.update(visible=True, value=error_msg),
                    []
                )
        
        def process_video_wrapper(video_file, youtube_url, input_type):
            """同步包装器"""
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(
                    process_video_async(video_file, youtube_url, input_type)
                )
            finally:
                loop.close()
        
        def search_transcript(video_id, keyword):
            """搜索转录内容"""
            if not video_id or not keyword:
                return gr.update(visible=False)
            
            try:
                # 异步调用搜索
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                results = loop.run_until_complete(
                    pipeline.search_in_transcript(video_id, keyword)
                )
                loop.close()
                
                if results:
                    return gr.update(visible=True, value=results)
                else:
                    return gr.update(visible=True, value={"message": "未找到匹配结果"})
                    
            except Exception as e:
                return gr.update(visible=True, value={"error": str(e)})
        
        # 绑定事件
        input_type.change(
            fn=toggle_input_type,
            inputs=[input_type],
            outputs=[video_upload, youtube_url]
        )
        
        reset_btn.click(
            fn=reset_interface,
            outputs=[video_upload, youtube_url, status_display, result_display, error_display, keyframes_gallery]
        )
        
        process_btn.click(
            fn=process_video_wrapper,
            inputs=[video_upload, youtube_url, input_type],
            outputs=[result_display, status_display, result_display, error_display, keyframes_gallery]
        )
        
        search_btn.click(
            fn=search_transcript,
            inputs=[video_selector, search_keyword],
            outputs=[search_results]
        )
        
        config_check_btn.click(
            fn=lambda: get_service_status_html(),
            outputs=[config_status]
        )
    
    return interface


def get_service_status_html() -> str:
    """获取服务状态HTML"""
    try:
        status = pipeline.check_services_availability()
        
        html = """
        <div style="padding: 10px; border-radius: 5px; background-color: #f0f0f0;">
            <h4>🔧 服务状态</h4>
            <ul>
        """
        
        for service, available in status.items():
            icon = "✅" if available else "❌"
            service_name = {
                "video_service": "视频处理服务",
                "speech_service": "智能语音服务", 
                "oss_service": "OSS存储服务"
            }.get(service, service)
            
            html += f"<li>{icon} {service_name}: {'可用' if available else '不可用'}</li>"
        
        html += """
            </ul>
        </div>
        """
        
        return html
        
    except Exception as e:
        return f"""
        <div style="padding: 10px; border-radius: 5px; background-color: #ffe6e6;">
            <h4>❌ 状态检查失败</h4>
            <p>{str(e)}</p>
        </div>
        """


if __name__ == "__main__":
    # 创建界面
    demo = create_aliyun_video_analysis_interface()
    
    # 启动服务
    demo.launch(
        server_name="0.0.0.0",
        server_port=7860,
        share=False,
        show_error=True,
        show_tips=True,
        inbrowser=True
    )