# 🎬 Simple YouTube Video Summarizer

一个简化的视频处理应用，可以下载YouTube视频、提取音频转录、生成AI摘要。

## ✨ 功能特性

- **视频下载**: 使用 yt-dlp 下载 YouTube 和其他平台视频
- **音频转录**: 使用 OpenAI Whisper API 进行高质量语音转文字
- **关键帧提取**: 自动提取视频关键帧
- **AI摘要**: 使用 OpenAI GPT-4 Vision 或 Qwen VL 生成视频摘要
- **Web界面**: 基于 Gradio 的用户友好界面
- **多语言支持**: 支持中文、英文和自动检测

## 🚀 快速开始

### 环境要求

- Python 3.8+
- pip 包管理器
- 网络连接用于 API 服务

### 安装步骤

1. **克隆或下载项目**
   ```bash
   cd My_Youtube_Summarizer
   ```

2. **安装依赖**
   ```bash
   pip install -r requirements_simple.txt
   ```

3. **设置环境变量**
   ```bash
   cp .env.example .env
   # 编辑 .env 文件，添加你的 API 密钥
   ```

4. **安装 yt-dlp 和 ffmpeg**（如果尚未安装）
   ```bash
   # macOS with Homebrew
   brew install yt-dlp ffmpeg
   
   # Ubuntu/Debian
   sudo apt update
   sudo apt install yt-dlp ffmpeg
   ```

### 使用方法

1. **启动应用**
   ```bash
   python main.py
   ```

2. **打开浏览器** 访问 `http://localhost:7860`

3. **处理视频**:
   - 输入 YouTube URL
   - 选择处理选项（语言、摘要详细程度等）
   - 点击"开始处理"
   - 等待结果

## 🔧 配置

### 必需的 API 密钥

选择以下一种或两种配置：

#### 选项1: OpenAI（推荐）
- 从 [OpenAI](https://platform.openai.com/api-keys) 获取 API 密钥
- 在 `.env` 文件中设置 `OPENAI_API_KEY`
- 提供语音转录和摘要功能

#### 选项2: Qwen/DashScope（摘要替代方案）
- 从 [阿里云 DashScope](https://help.aliyun.com/zh/dashscope/) 获取 API 密钥
- 在 `.env` 文件中设置 `QWEN_API_KEY` 或 `DASHSCOPE_API_KEY`
- 仅提供摘要功能，转录需要 OpenAI 或使用本地备用方案

### 环境变量

```bash
# 必需：至少一个 API 密钥
OPENAI_API_KEY=your_openai_api_key_here
QWEN_API_KEY=your_qwen_api_key_here

# 可选
PORT=7860                # Web 界面端口
LOG_LEVEL=INFO          # 日志级别
```

## 📋 功能详情

### 视频处理流程

1. **下载**: 使用 yt-dlp 下载视频和提取音频
2. **关键帧提取**: 使用 OpenCV 提取代表性帧
3. **转录**: 使用 Whisper API 将音频转换为文字
4. **摘要**: 分析转录文本和关键帧生成摘要

### 支持的平台

- YouTube
- yt-dlp 支持的大多数视频平台

### 输出格式

- **文字转录**: 完整音频转录
- **视频摘要**: 多种详细程度的 AI 生成摘要
- **关键帧**: 视频代表性图像
- **元数据**: 视频标题、上传者、时长等

## 🛠️ 故障排除

### 常见问题

1. **"未找到 yt-dlp"**
   - 安装 yt-dlp: `pip install yt-dlp`

2. **"未找到 OpenCV"**
   - 安装 OpenCV: `pip install opencv-python`

3. **"API 密钥无效"**
   - 检查 API 密钥是否正确
   - 确保有足够的 API 额度
   - 检查 API 密钥权限

4. **"视频下载失败"**
   - 检查网络连接
   - 尝试其他视频 URL
   - 某些视频可能有地域限制

### 性能优化

- 减少关键帧数量以加快处理速度
- 使用"简短"摘要粒度获得更快结果
- 确保稳定的网络连接

## 📁 项目结构

```
├── main.py                      # 应用入口点
├── gradio_app.py               # Gradio Web 界面
├── video_processing_pipeline.py # 主处理流程
├── simple_video_service.py     # 视频下载和关键帧
├── simple_speech_service.py    # 音频转录
├── simple_llm_service.py       # AI 摘要
├── requirements_simple.txt     # Python 依赖
├── .env.example               # 环境变量模板
└── README_SIMPLE.md           # 此文件
```

## 🔄 从复杂版本迁移

此简化版本移除了：
- 数据库存储（SQLite）
- 用户认证系统
- 订阅管理
- React 前端
- 复杂微服务架构
- Google Cloud 集成
- 会话管理

保留了核心视频处理功能，采用更直接、简单的方法。

## 📝 许可证

[在此添加你的许可证信息]

## 🤝 贡献

[在此添加贡献指南]

## 📞 支持

如有问题和疑问：
1. 查看上述故障排除部分
2. 查看 `video_summarizer.log` 中的日志
3. 提交包含详细错误信息的 issue