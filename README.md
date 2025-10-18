# YouTube 视频智能总结系统

基于阿里云 AI 服务的智能视频分析平台，支持 YouTube 视频下载、关键帧提取、音频转录和 AI 内容总结。

## ✨ 特性

- 🎬 **视频处理**: 支持 YouTube URL 和本地文件上传
- 🖼️ **关键帧提取**: 自动识别并提取视频关键画面
- 🎤 **音频转录**: 使用 SenseVoice 高精度转录
- 🤖 **AI 总结**: Qwen3-VL-Flash 多模态视频理解
- ☁️ **云端存储**: 阿里云 OSS 集成
- 🖌️ **Web 界面**: Gradio 交互式界面

## 🚀 快速开始

### 方式一：Gradio Web 界面（推荐）

```bash
# 1. 安装依赖
cd backend
pip install -r requirements.txt

# 2. 配置环境变量
# 在项目根目录创建 .env 文件
# 填入 API 密钥和 OSS 配置

# 3. 启动 Web 界面
./run_gradio.sh

# 4. 打开浏览器访问
open http://127.0.0.1:7860
```

📚 **详细文档**: [Gradio 快速入门](backend/GRADIO_QUICKSTART.md) | [完整使用指南](backend/GRADIO_USER_GUIDE.md)

### 方式二：FastAPI 后端服务

```bash
# 启动 API 服务
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# API 文档
open http://localhost:8000/docs
```

## 📁 项目结构

```
backend/
├── app/
│   ├── api/                    # API路由
│   ├── core/                   # 核心配置
│   ├── models/                 # 数据模型
│   ├── services/               # 业务服务层
│   │   ├── video_service.py    # 视频处理服务
│   │   ├── speech_service.py   # SenseVoice 语音识别
│   │   ├── llm_service.py      # Qwen3-VL-Flash 总结
│   │   ├── oss_service.py      # OSS存储服务
│   │   └── pipeline_service.py # 处理管道服务
│   ├── utils/                  # 工具函数
│   └── tests/                  # 测试代码
├── gradio_app.py               # Gradio Web 界面
├── run_gradio.sh               # Gradio 启动脚本
├── GRADIO_QUICKSTART.md        # Gradio 快速入门
├── GRADIO_USER_GUIDE.md        # Gradio 完整指南
├── requirements.txt            # 依赖文件
└── README.md                   # 项目说明
```

## 🛠️ 安装依赖

```bash
pip install -r requirements.txt
```

## ⚙️ 环境变量配置

在项目根目录创建 `.env` 文件并配置以下变量：

```env
# 阿里云 OSS 配置（必需）
OSS_ACCESS_KEY_ID=your_access_key_id
OSS_ACCESS_KEY_SECRET=your_access_key_secret
OSS_BUCKET=your_bucket_name
OSS_ENDPOINT=oss-cn-beijing.aliyuncs.com

# API 密钥配置（至少配置一个）
QWEN_API_KEY=your_qwen_api_key
```

## 🖌️ Gradio Web 界面

```bash
cd backend
./run_gradio.sh
```

访问: http://127.0.0.1:7860

## 🔧 FastAPI 后端

```bash
python -m app.main
```

或者使用uvicorn：

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

## 📝 API文档

启动服务后，可以通过以下URL访问API文档：

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## 🧪 测试

```bash
# 运行单元测试
cd backend
pytest app/tests/

# 运行完整集成测试
cd app/tests
./run_complete_pipeline_test.sh
```

## 📚 文档

- [Gradio 快速入门](backend/GRADIO_QUICKSTART.md)
- [Gradio 完整指南](backend/GRADIO_USER_GUIDE.md)
- [SenseVoice 集成指南](backend/app/tests/docs/SENSEVOICE_INTEGRATION_GUIDE.md)
- [Qwen3-VL 集成指南](backend/app/tests/docs/QWEN3_VL_INTEGRATION_GUIDE.md)

## 📦 技术栈

- **Gradio** - Web 界面框架
- **FastAPI** - API 框架
- **yt-dlp** - YouTube 下载
- **FFmpeg** - 视频/音频处理
- **SenseVoice** - 音频转录
- **Qwen3-VL-Flash** - 视频理解
- **阿里云 OSS** - 对象存储

## 🌟 功能展示

- ✅ YouTube 视频下载和本地文件上传
- ✅ 自动关键帧提取和场景描述
- ✅ 高精度音频转录（SenseVoice）
- ✅ 多粒度 AI 总结（简要/标准/详细）
- ✅ 实时处理进度显示
- ✅ 可视化结果展示
- ✅ 云端存储和资源下载

---

**使用感受请反馈！** 🚀