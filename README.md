# YouTube 视频摘要工具

这是一个商业级YouTube视频摘要工具，可以自动下载视频、提取关键帧、转录音频，并生成详细的视频内容摘要。支持中文、英文和韩文三种语言。

## 核心功能

- **视频下载**：支持输入YouTube链接自动下载视频内容
- **关键帧提取**：支持三种关键帧提取方法（均匀分段、固定时间间隔、场景检测）
- **音频转文本**：使用OpenAI的Whisper API进行高精度音频转录
- **说话人分离**：使用pyannote.audio识别不同的说话人，并在转录中标记
- **摘要生成**：调用阿里云通义千问模型（Qwen）生成多种粒度的视频内容摘要
- **多语言支持**：支持中文、英文和韩文三种语言的界面和输出
- **用户系统**：完整的用户注册、登录和个人资料管理
- **付费墙**：提供免费、基础和高级三种订阅计划
- **历史记录**：保存和管理所有生成的摘要

## 技术栈

- **前端**：React + JavaScript + Ant Design
- **后端**：FastAPI + Python
- **数据存储**：JSON文件存储 (可配置Google Cloud Storage用于存储关键帧)
- **容器化**：Docker + Docker Compose
- **语音转文本**：OpenAI Whisper API
- **摘要生成**：阿里云通义千问（Qwen）
- **说话人分离**：pyannote.audio
- **关键帧提取**：OpenCV, scenedetect
- **视频下载**：yt-dlp

## 项目结构

```
my-youtube-summarizer/
├── frontend/                   # React前端应用
│   ├── public/
│   ├── src/
│   │   ├── assets/
│   │   ├── components/
│   │   ├── pages/
│   │   ├── services/
│   │   └── App.js
│   ├── Dockerfile
│   └── package.json
├── backend/                    # FastAPI后端应用
│   ├── app/
│   │   ├── api/                # API路由和端点
│   │   │   └── api_v1/
│   │   │       └── endpoints/
│   │   ├── core/               # 核心配置和安全设置
│   │   ├── models/             # Pydantic数据模型
│   │   ├── services/           # 业务逻辑服务
│   │   │   ├── auth/
│   │   │   ├── payment/
│   │   │   ├── storage/
│   │   │   └── summary/        # 视频处理、转录、摘要生成等
│   │   └── main.py             # FastAPI应用入口
│   ├── storage/                # 本地文件存储目录 (视频, 音频, 关键帧, JSON数据)
│   ├── logs/                   # 日志文件目录
│   ├── tests/                  # 测试代码
│   ├── requirements.txt        # Python依赖列表
│   ├── Dockerfile              # 后端Docker配置
│   └── .env                    # 环境变量文件
├── docker-compose.yml          # Docker Compose配置文件
├── README.md                   # 本文件
└── .env.example                # 环境变量示例文件
```

## 快速开始

### 环境要求

- Docker 和 Docker Compose
- Python 3.8+
- OpenAI API密钥（用于Whisper语音转文本）
- 阿里云通义千问 API密钥（用于视频摘要生成）
- Hugging Face Token（用于pyannote.audio说话人分离）
- (可选) Google Cloud Platform (GCP) 项目和存储桶，并配置好服务账号密钥（用于将关键帧上传到GCS）

### 安装步骤

1. 克隆仓库：

```bash
git clone https://github.com/yourusername/youtube-summarizer.git
cd youtube-summarizer
```

2. 创建并配置环境变量文件：

```bash
cp .env.example .env
```

3. 编辑 `.env` 文件，填入您的API密钥和配置：

```plaintext
# FastAPI 后端配置
SECRET_KEY=your_secret_key_for_jwt # 用于JWT令牌签名，请生成一个强随机字符串
ACCESS_TOKEN_EXPIRE_MINUTES=10080 # 令牌有效期（分钟），例如7天
STORAGE_DIR=./backend/storage      # 本地文件存储根目录
LOG_LEVEL=INFO                     # 日志级别 (DEBUG, INFO, WARNING, ERROR, CRITICAL)

# API 密钥
OPENAI_API_KEY=your_openai_api_key        # OpenAI Whisper API 密钥
QWEN_API_KEY=your_qwen_api_key            # 阿里云通义千问 API 密钥
HF_TOKEN=your_huggingface_token           # Hugging Face Token (用于 pyannote.audio)

# 千问 API 配置 (通常不需要修改)
QWEN_API_BASE=https://dashscope-intl.aliyuncs.com/compatible-mode/v1/chat/completions
QWEN_MODEL=qwen-max                       # 使用的模型

# Google Cloud Storage 配置 (可选)
GCS_BUCKET_NAME=your_gcs_bucket_name             # 您的 GCS 存储桶名称
GOOGLE_APPLICATION_CREDENTIALS=path/to/your/gcp-service-account-key.json # GCP服务账号密钥文件路径
```

   **重要安全提示**: `SECRET_KEY` 必须是一个难以猜测的随机字符串。您可以使用 `openssl rand -hex 32` 命令生成一个。

4. 构建并启动 Docker 容器：

```bash
docker-compose up --build -d
```

5. 访问应用：

   在浏览器中打开 `http://localhost` （或您配置的端口）访问前端应用。
   API文档通常位于 `http://localhost:8000/docs` (假设后端端口为8000)。

## 订阅计划

- **免费版**：每月3次视频处理额度，基本摘要功能
- **基础版**：每月20次视频处理额度，详细摘要功能，说话人分离，多种关键帧提取方法
- **高级版**：每月100次视频处理额度，所有功能，优先处理，无广告体验

## 技术实现细节

### 后端 (FastAPI)

- 同步处理视频下载和摘要生成
- 使用yt-dlp下载YouTube视频
- OpenAI的Whisper API进行音频转录
- 阿里云通义千问（Qwen）API生成视频摘要和分析关键帧
- pyannote.audio进行说话人分离
- JSON文件存储用户数据、订阅和摘要记录 (关键帧可配置存储在本地或GCS)

### 前端 (React)

- React函数组件和Hooks
- Ant Design UI组件库
- React Router处理路由
- Axios处理API请求
- JWT认证
- Nginx 处理前端静态文件和 API 请求代理
- 使用 Docker Compose 编排多容器应用

### 部署

- Docker容器化应用
- Nginx处理前端静态文件和API请求代理
- 使用Docker Compose编排多容器应用

## 功能扩展路径

- 集成数据库（例如PostgreSQL）替代JSON文件存储
- 添加异步任务处理（Celery）
- 实现社交分享功能
- 优化移动端体验
- 添加更多语言支持

## 许可证

MIT 