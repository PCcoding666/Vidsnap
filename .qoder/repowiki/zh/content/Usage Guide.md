# 使用指南

<cite>
**本文档引用的文件**   
- [gradio_app.py](file://gradio_app.py) - *前端界面重构，v0.1.2版本*
- [main.py](file://main.py) - *应用入口点，包含环境检查*
- [video_processing_pipeline.py](file://video_processing_pipeline.py) - *核心处理流程*
- [simple_video_service.py](file://simple_video_service.py) - *视频下载与关键帧提取*
- [simple_speech_service.py](file://simple_speech_service.py) - *语音转录服务*
- [simple_llm_service.py](file://simple_llm_service.py) - *摘要生成服务*
- [README_SIMPLE.md](file://README_SIMPLE.md) - *简化版应用说明文档*
</cite>

## 更新摘要
**已更改内容**   
- 根据 `e6dbe90` 提交，将应用启动方式从容器化部署更新为直接运行Python脚本
- 更新了启动应用部分，反映 `main.py` 的实际行为和配置要求
- 修正了CLI使用部分，准确描述简化版的启动流程
- 更新了环境变量配置说明，与 `README_SIMPLE.md` 保持一致

**新增内容**   
- 增加了对 `.env` 配置文件的详细说明
- 补充了系统依赖（ffmpeg、yt-dlp）的安装指导
- 添加了关于API密钥配置选项的详细信息

**已移除内容**   
- 移除了关于阿里云服务配置的过时信息
- 删除了与 `aliyun_gradio_app.py` 相关的不适用内容

**来源跟踪系统更新**   
- 更新了所有文件引用以反映当前代码库状态
- 为新分析的文件添加了来源注释

## 目录
1. [启动应用](#启动应用)
2. [用户界面概述](#用户界面概述)
3. [处理工作流程](#处理工作流程)
4. [CLI使用](#cli使用)
5. [错误处理与故障排除](#错误处理与故障排除)

## 启动应用

要使用Gradio Web界面启动YouTube摘要器应用，请执行 `main.py` 文件。该脚本作为主要入口点，包含完整的环境检查和依赖验证。

```bash
python main.py
```

应用默认在端口7860上启动。可以通过设置 `PORT` 环境变量来自定义此端口：

```bash
export PORT=8080
python main.py
```

启动后，应用可通过 `http://localhost:7860` 访问。Gradio界面提供了一个用户友好的基于Web的前端，用于视频摘要，无需任何额外的服务器配置。

**Section sources**
- [main.py](file://main.py#L102-L174) - *主程序入口和环境检查*
- [gradio_app.py](file://gradio_app.py#L332-L342) - *应用启动逻辑*

## 用户界面概述

Gradio界面分为三个主要部分：服务状态、输入参数和结果展示。

### 服务状态

服务状态部分显示关键组件的可用性：
- **视频下载服务**：始终可用（使用yt-dlp）
- **语音转录服务**：取决于OpenAI API密钥
- **摘要生成服务**：取决于OpenAI或Qwen API密钥

用户可以使用"🔄 刷新状态"按钮刷新状态，以验证API密钥配置。

### 输入参数

输入部分包含以下交互组件：

**视频URL输入**
- 标签："📹 视频URL"
- 占位符："请输入YouTube或其他视频平台的URL..."
- 目的：接受任何有效的YouTube或支持的视频平台URL

**处理选项**
- 语言选择：下拉菜单，选项包括中文("zh")、英文("en")或自动检测("auto")
- 摘要详细程度：短、中等或详细摘要的选项
- 关键帧数量：5到20帧的滑块（默认：10）
- 关键帧提取方法：三种可用方法：
  - 均匀采样：均匀分布的帧
  - 时间间隔：固定时间间隔
  - 场景检测：场景变化检测（当前回退到均匀采样）

### 结果展示

结果部分显示四个输出组件：
- 处理状态：实时进度更新
- 视频信息：包括标题、上传者、时长、观看次数和上传日期的元数据
- 音频转录：视频音频的完整文本转录
- 视频摘要：AI生成的内容摘要
- 关键帧图库：以4列网格显示提取的关键帧

**Section sources**
- [gradio_app.py](file://gradio_app.py#L125-L310) - *UI组件定义*

## 处理工作流程

从URL输入到最终输出的完整工作流程涉及通过视频处理管道协调的多个后端服务。

### 逐步流程

```
输入YouTube URL → 验证URL → 下载视频和音频 → 提取关键帧 → 转录音频 → 生成摘要 → 显示结果 → 完成
```

**Diagram sources**
- [video_processing_pipeline.py](file://video_processing_pipeline.py#L53-L86) - *处理流程定义*
- [gradio_app.py](file://gradio_app.py#L68-L103) - *UI到后端的映射*

### 后端服务集成

Gradio UI组件通过 `process_video_gradio` 函数直接映射到后端服务：

```python
def process_video_gradio(video_url: str, 
                        language: str,
                        granularity: str,
                        num_keyframes: int,
                        keyframe_method: str,
                        progress: gr.Progress)
```

此函数协调以下后端服务：
1. **视频服务**：使用yt-dlp处理下载和关键帧提取
2. **语音服务**：使用OpenAI Whisper API进行音频转录
3. **LLM服务**：使用OpenAI GPT-4 Vision或Qwen VL生成摘要

进度回调使用以下阶段实时更新Gradio界面：
- 初始化 (0%)
- 视频下载 (10%)
- 关键帧提取 (30%)
- 音频转录 (55%)
- 摘要生成 (80%)
- 完成 (100%)

**Section sources**
- [video_processing_pipeline.py](file://video_processing_pipeline.py#L53-L273) - *核心处理管道*
- [gradio_app.py](file://gradio_app.py#L68-L165) - *Gradio处理函数*

## CLI使用

对于无头操作，可以通过直接Python执行使用应用。`main.py` 脚本是主要入口点，包含环境验证。

### 命令模式

```bash
# 基本执行
python main.py

# 使用自定义端口
PORT=8080 python main.py

# 使用API密钥
OPENAI_API_KEY=your_key python main.py
```

脚本执行启动前检查：
- 所需API密钥（OpenAI或Qwen）
- 依赖项（yt-dlp、OpenCV、Gradio）
- 环境配置

启动期间的示例输出：
```
🎬 简化版视频摘要器
==================================================
检查环境...
✅ OpenAI API密钥已找到
✅ yt-dlp可用
✅ OpenCV可用
✅ Gradio可用
✅ 环境检查通过！
🚀 启动Gradio应用...
INFO:     已启动服务器进程 [12345]
INFO:     等待应用启动。
INFO:     应用启动完成。
INFO:     Uvicorn在http://0.0.0.0:7860上运行
```

**Section sources**
- [main.py](file://main.py#L1-L118) - *主程序入口和环境检查*
- [README_SIMPLE.md](file://README_SIMPLE.md) - *简化版安装和配置说明*

## 错误处理与故障排除

应用实现了针对常见用户问题的全面错误处理。

### 常见错误及解决方案

**无效URL**
- **症状**："❌ 错误：请输入有效的视频URL"
- **原因**：空或格式错误的URL输入
- **解决方案**：输入有效的YouTube URL（例如，https://www.youtube.com/watch?v=example）

**API密钥问题**
- **症状**："❌ 语音转录服务：不可用（请检查API密钥）"
- **原因**：缺少或无效的OPENAI_API_KEY
- **解决方案**：设置环境变量：
  ```bash
  export OPENAI_API_KEY=your_actual_key
  ```

**API超时**
- **语音服务**：Whisper API的300秒超时
- **LLM服务**：OpenAI和Qwen API的120秒超时
- **网络**：yt-dlp操作的60秒套接字超时

**部分成功场景**
系统优雅地处理部分失败：
- 如果转录失败但关键帧存在，则生成仅视觉摘要
- 如果关键帧提取失败但转录存在，则生成仅文本摘要
- 多个错误被聚合并在状态输出中显示

### 服务可用性检查

应用在初始化期间验证服务状态：

```python
def get_services_status(self) -> Dict[str, bool]:
    return {
        "video": True,
        "speech": self.speech_service is not None and self.speech_service.is_available(),
        "llm": self.llm_service.is_available()
    }
```

用户应在处理视频前验证所有服务显示"✅ 可用"，以避免中断。

**Section sources**
- [simple_speech_service.py](file://simple_speech_service.py#L101) - *语音服务可用性检查*
- [simple_llm_service.py](file://simple_llm_service.py#L135) - *LLM服务可用性检查*
- [simple_video_service.py](file://simple_video_service.py#L26) - *视频服务实现*
- [gradio_app.py](file://gradio_app.py#L125-L158) - *服务状态获取*