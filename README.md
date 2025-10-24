# YouTube 视频智能总结系统

基于阿里云 AI 服务的智能视频分析平台，支持 YouTube 视频下载、关键帧提取、音频转录和 AI 内容总结。

## ✨ 特性

- 🎬 **视频处理**: 支持 YouTube URL 和本地文件上传
- 🖼️ **关键帧提取**: 自动识别并提取视频关键画面
- 🎤 **音频转录**: 使用 Paraformer-v2 高精度转录 + 说话人分离
- 🤖 **AI 总结**: Qwen3-VL-Flash 多模态视频理解
- ☁️ **云端存储**: 阿里云 OSS 集成
- 🖌️ **Web 界面**: Gradio 交互式界面

## 🚀 快速开始

### 方式一：前端营销主页（推荐）

```
# 1. 进入前端目录
cd frontend

# 2. 安装依赖
npm install

# 3. 启动开发服务器
npm run dev
# 或使用启动脚本
./start.sh

# 4. 打开浏览器访问
open http://localhost:5173
```

📚 **详细文档**: [前端 README](frontend/README.md) | [部署指南](frontend/DEPLOYMENT.md)

### 方式二：Gradio Web 界面

```
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

### 方式三：FastAPI 后端服务

```
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
│   │   ├── paraformer_service.py # Paraformer-v2 语音识别
│   │   ├── speech_service.py   # SenseVoice 语音识别 (旧)
│   │   ├── llm_service.py      # Qwen3-VL-Flash 总结
│   │   ├── oss_service.py      # OSS存储服务
│   │   └── pipeline_service.py # 处理管道服务
│   ├── utils/                  # 工具函数
│   └── tests/                  # 测试代码
├── gradio_app.py               # Gradio Web 界面
├── run_gradio.sh               # Gradio 启动脚本
├── GRADIO_QUICKSTART.md        # Gradio 快速入门
├── GRADIO_USER_GUIDE.md        # Gradio 完整指南
├── PARAFORMER_QUICKREF.md      # Paraformer-v2 快速参考
├── requirements.txt            # 依赖文件
└── README.md                   # 项目说明
```

## 🛠️ 安装依赖

```
pip install -r requirements.txt
```

## ⚙️ 环境变量配置

在项目根目录创建 `.env` 文件并配置以下变量：

```
# 阿里云 OSS 配置（必需）
OSS_ACCESS_KEY_ID=your_access_key_id
OSS_ACCESS_KEY_SECRET=your_access_key_secret
OSS_BUCKET=your_bucket_name
OSS_ENDPOINT=oss-cn-beijing.aliyuncs.com

# API 密钥配置（至少配置一个）
QWEN_API_KEY=your_qwen_api_key
```

## 🖌️ Gradio Web 界面

```
cd backend
./run_gradio.sh
```

访问: http://127.0.0.1:7860

## 🔧 FastAPI 后端

```
python -m app.main
```

或者使用uvicorn：

```
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

## 📝 API文档

启动服务后，可以通过以下URL访问API文档：

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## 🧪 测试

```
# 运行单元测试
cd backend
pytest app/tests/

# 运行完整集成测试
cd app/tests
./run_complete_pipeline_test.sh
```

## 📚 文档

- **前端文档**
  - [前端 README](frontend/README.md)
  - [部署指南](frontend/DEPLOYMENT.md)
- **后端文档**
  - [Gradio 快速入门](backend/GRADIO_QUICKSTART.md)
  - [Gradio 完整指南](backend/GRADIO_USER_GUIDE.md)
  - [SenseVoice 集成指南](backend/app/tests/docs/SENSEVOICE_INTEGRATION_GUIDE.md)
  - [Qwen3-VL 集成指南](backend/app/tests/docs/QWEN3_VL_INTEGRATION_GUIDE.md)

## 📦 技术栈

**前端**
- **React 18** - UI 框架
- **TypeScript** - 类型安全
- **Vite** - 构建工具
- **Tailwind CSS** - 样式系统
- **Framer Motion** - 动画库

**后端**
- **Gradio** - Web 界面框架
- **FastAPI** - API 框架
- **yt-dlp** - YouTube 下载
- **FFmpeg** - 视频/音频处理
- **Paraformer-v2** - 音频转录 + 说话人分离
- **Qwen3-VL-Flash** - 视频理解
- **阿里云 OSS** - 对象存储

## 🌟 功能展示

- ✅ YouTube 视频下载和本地文件上传
- ✅ 自动关键帧提取和场景描述
- ✅ 高精度音频转录（Paraformer-v2 + 说话人分离）
- ✅ 多粒度 AI 总结（简要/标准/详细）
- ✅ 实时处理进度显示
- ✅ 可视化结果展示
- ✅ 云端存储和资源下载

---

## 🆕 更新日志

### v2.0 (2025-10-24)

✨ **重大更新**: 语音识别升级到 Paraformer-v2

- ✅ 转录准确率从 88% 提升到 **95%**
- ✅ 时间戳精度从秒级提升到**毫秒级**
- ✨ 新增**说话人自动分离**功能
- ✨ 输出格式优化，无乱码标签
- 📚 查看 [Paraformer 详细对比](backend/app/tests/docs/PARAFORMER_VS_SENSEVOICE.md)

---

**使用感受请反馈！** 🚀