# YouTube 视频智能总结系统

一个功能完整的智能视频分析 SaaS 平台，集成用户认证、视频处理、AI 分析和数据持久化。基于阿里云 AI 服务和 Supabase 云数据库，提供 YouTube 视频下载、关键帧提取、音频转录和 AI 内容总结功能。

## ✨ 核心特性

### 用户系统
- 🔐 **完整认证**: 邮箱注册登录 + Google OAuth 社交登录
- 👤 **用户管理**: 基于 Supabase Auth 的安全认证
- 📊 **配额管理**: 多级订阅（Free/Pro/Enterprise）+ 使用限制
- 💾 **数据持久化**: 用户数据、视频记录、处理结果云端存储

### 视频处理
- 🎬 **多源支持**: YouTube URL 下载 + 本地文件上传
- 🖼️ **关键帧提取**: 智能场景识别和关键画面提取
- 🎤 **高精度转录**: Paraformer-v2 语音识别 + 说话人自动分离
- 🤖 **AI 视频理解**: Qwen3-VL-Flash 多模态分析
- ☁️ **云端存储**: 阿里云 OSS 统一资源管理

### 用户界面
- 🌐 **营销主页**: 现代化 React 前端（shadcn/ui + Tailwind CSS）
- 📱 **响应式设计**: 支持桌面端和移动端
- 🔄 **实时反馈**: 处理进度实时显示

## 🚀 快速开始

### 环境准备

**系统要求**:
- Node.js >= 18
- Python >= 3.9
- FFmpeg（视频处理）

**必需配置**:
在项目根目录创建 `.env` 文件：

```bash
# 阿里云 OSS 配置
OSS_ACCESS_KEY_ID=your_access_key_id
OSS_ACCESS_KEY_SECRET=your_access_key_secret
OSS_BUCKET=your_bucket_name
OSS_ENDPOINT=oss-cn-beijing.aliyuncs.com

# 阿里云 AI 服务
QWEN_API_KEY=your_dashscope_api_key

# Supabase 配置
SUPABASE_URL=your_supabase_project_url
SUPABASE_ANON_KEY=your_supabase_anon_key
SUPABASE_SERVICE_KEY=your_supabase_service_key

# Google OAuth（可选）
GOOGLE_CLIENT_ID=your_google_client_id
GOOGLE_CLIENT_SECRET=your_google_client_secret
```

### 方式一：完整 Web 应用（推荐）

使用一键启动脚本同时运行前后端：

```bash
# 安装依赖
cd backend && pip install -r requirements.txt
cd ../frontend && npm install

# 启动完整系统（前端 + 后端）
./start_dev.sh

# 前端访问: http://localhost:8080
# 后端 API: http://localhost:8000
# API 文档: http://localhost:8000/docs
```

或分别启动：

```bash
# 终端 1: 启动后端 API
./app/tests/run_fastapi.sh

# 终端 2: 启动前端
./app/tests/run_frontend.sh
```

### 方式二：仅启动 FastAPI 后端

适合 API 开发和测试：

```bash
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Swagger UI: http://localhost:8000/docs
# ReDoc: http://localhost:8000/redoc
```

## 📁 项目结构

```
.
├── frontend/                   # React 前端应用
│   ├── src/
│   │   ├── components/         # UI 组件
│   │   │   ├── auth/          # 认证相关组件
│   │   │   ├── dashboard/     # 仪表板组件
│   │   │   ├── chat/          # 聊天组件
│   │   │   └── ui/            # shadcn/ui 组件
│   │   ├── contexts/          # React Context
│   │   ├── pages/             # 页面组件
│   │   ├── services/          # API 服务层
│   │   └── integrations/      # Supabase 集成
│   ├── package.json
│   └── vite.config.ts
│
├── backend/                    # FastAPI 后端
│   ├── app/
│   │   ├── api/
│   │   │   └── routes/        # API 路由
│   │   │       ├── auth.py    # 认证路由
│   │   │       ├── video.py   # 视频处理路由
│   │   │       └── analysis.py # 分析路由
│   │   ├── core/              # 核心配置
│   │   │   ├── config.py      # 配置管理
│   │   │   └── logging.py     # 日志配置
│   │   ├── models/            # Pydantic 数据模型
│   │   ├── services/          # 业务服务层
│   │   │   ├── video_service.py      # 视频下载处理
│   │   │   ├── paraformer_service.py # 语音转录
│   │   │   ├── llm_service.py        # AI 分析
│   │   │   ├── oss_service.py        # 云存储
│   │   │   ├── supabase_service.py   # 数据库操作
│   │   │   ├── chat_service.py       # 聊天服务
│   │   │   └── pipeline_service.py   # 处理流水线
│   │   └── tests/             # 单元测试
│   ├── sql/                   # 数据库 Schema
│   ├── scripts/               # 工具脚本
│   └── requirements.txt       # Python 依赖
│
├── app/tests/                 # 集成测试
│   ├── docs/                  # 测试文档
│   ├── run_fastapi.sh         # 后端启动脚本
│   ├── run_frontend.sh        # 前端启动脚本
│   └── run_system_integration_test.sh
│
├── start_dev.sh               # 开发环境一键启动
├── test_integration.sh        # 集成测试脚本
└── README.md                  # 本文件
```

## 🛠️ 安装和配置

### 后端依赖

```bash
cd backend
pip install -r requirements.txt
```

### 前端依赖

```bash
cd frontend
npm install
# 或使用 bun
bun install
```

### 数据库初始化

1. 在 [Supabase](https://supabase.com) 创建项目
2. 执行数据库 Schema：

```bash
cd backend
python scripts/init_supabase_schema.py
# 或手动在 Supabase SQL Editor 执行 sql/schema_v1.sql
```

### 前端环境配置

在 `frontend/.env.development` 文件中配置：

```bash
VITE_API_BASE_URL=http://localhost:8000
VITE_SUPABASE_URL=your_supabase_url
VITE_SUPABASE_ANON_KEY=your_supabase_anon_key
```

## 🧪 测试

### 系统集成测试

```bash
# 完整的前后端集成测试
./test_integration.sh

# 系统集成测试（包含认证、视频处理等）
./app/tests/run_system_integration_test.sh
```

### 后端单元测试

```bash
cd backend

# 所有测试
pytest app/tests/

# 特定功能测试
pytest app/tests/test_video_service.py
pytest app/tests/test_paraformer_service.py
pytest app/tests/test_supabase_service.py

# 管道测试
./app/tests/run_complete_pipeline_test.sh
```

### API 测试

前端提供 API 测试页面，访问 `/api-test` 路由测试各个端点。

## 📚 文档

### 用户认证
- [Supabase 指南](backend/SUPABASE_GUIDE.md)
- [Google OAuth 指南](backend/GOOGLE_OAUTH_GUIDE.md)

### 视频处理
- [Paraformer 快速参考](backend/PARAFORMER_QUICKREF.md)
- [Qwen3-VL 集成指南](backend/app/tests/docs/QWEN3_VL_INTEGRATION_GUIDE.md)

### 前端开发
- [前端 README](frontend/README.md)
- [部署指南](frontend/DEPLOYMENT.md)（如果存在）

### 测试文档
- [阶段一测试指南](app/tests/docs/PHASE_1_TEST_GUIDE.md)
- [系统集成测试](app/tests/docs/SYSTEM_INTEGRATION_TEST_REPORT.md)
- [Supabase 验证指南](app/tests/docs/SUPABASE_VERIFICATION.md)

## 📦 技术栈

### 前端技术
- **React 18** - 现代化 UI 框架
- **TypeScript** - 类型安全开发
- **Vite** - 快速构建工具
- **React Router v6** - 前端路由
- **shadcn/ui** - 高质量 UI 组件库
- **Tailwind CSS** - 实用优先的样式系统
- **Radix UI** - 无障碍访问组件
- **Framer Motion** - 流畅动画库
- **React Query** - 服务端状态管理
- **Axios** - HTTP 客户端

### 后端技术
- **FastAPI** - 高性能 Web 框架
- **Pydantic** - 数据验证
- **yt-dlp** - YouTube 视频下载
- **FFmpeg** - 媒体处理
- **PySceneDetect** - 场景检测

### AI 服务（阿里云 DashScope）
- **Paraformer-v2** - 高精度语音识别 + 说话人分离
- **Qwen3-VL-Flash** - 多模态视频理解

### 云服务
- **阿里云 OSS** - 对象存储
- **Supabase** - 后端即服务（BaaS）
  - Auth - 用户认证
  - Database - PostgreSQL 数据库
  - Storage - 文件存储

### 开发工具
- **pytest** - Python 测试框架
- **ESLint** - JavaScript/TypeScript 代码检查
- **python-dotenv** - 环境变量管理

## 🌟 功能清单

### 用户系统 ✅
- ✅ 邮箱注册/登录
- ✅ Google OAuth 社交登录
- ✅ JWT Token 认证
- ✅ 用户配额管理（Free/Pro/Enterprise）
- ✅ 使用量统计

### 视频处理 ✅
- ✅ YouTube URL 视频下载
- ✅ 本地文件上传
- ✅ 自动关键帧提取
- ✅ 场景智能识别
- ✅ 视频元数据提取

### AI 分析 ✅
- ✅ 高精度语音转录（Paraformer-v2）
- ✅ 说话人自动分离
- ✅ 毫秒级时间戳
- ✅ 多模态视频理解（Qwen3-VL-Flash）
- ✅ 多粒度内容总结（简要/标准/详细）
- ✅ 智能问答（基于转录内容）

### 数据管理 ✅
- ✅ 视频记录持久化
- ✅ 处理结果存储
- ✅ 用户历史查询
- ✅ 云端文件管理

### 用户体验 ✅
- ✅ 实时处理进度显示
- ✅ 响应式界面设计
- ✅ 错误处理和提示
- ✅ 结果可视化展示
- ✅ 资源下载功能

## 🎯 API 端点

### 认证相关
- `POST /auth/signup` - 用户注册
- `POST /auth/signin` - 用户登录
- `GET /auth/me` - 获取当前用户信息
- `GET /auth/oauth/google` - Google OAuth 登录
- `POST /auth/oauth/callback` - OAuth 回调处理

### 视频处理
- `POST /video/process` - 提交视频处理任务
- `GET /video/{video_id}` - 获取视频信息
- `GET /video/user/{user_id}` - 获取用户视频列表
- `GET /video/status` - 查询处理状态

### 分析服务
- `POST /analysis/chat` - 基于转录内容的问答

---

## 🆕 更新日志

### v3.0 (2025-01-15)

🎉 **完整 SaaS 平台上线**

- ✅ 完整的用户认证系统（邮箱 + Google OAuth）
- ✅ Supabase 数据持久化集成
- ✅ React 前端营销主页
- ✅ 用户仪表板和历史记录
- ✅ 配额管理和订阅系统
- ✅ 智能问答功能
- 📚 查看 [系统集成测试报告](app/tests/docs/SYSTEM_INTEGRATION_TEST_REPORT.md)

### v2.0 (2024-10-24)

✨ **语音识别升级到 Paraformer-v2**

- ✅ 转录准确率从 88% 提升到 **95%**
- ✅ 时间戳精度从秒级提升到**毫秒级**
- ✨ 新增**说话人自动分离**功能
- ✨ 输出格式优化，无乱码标签
- 📚 查看 [Paraformer 详细对比](backend/app/tests/docs/PARAFORMER_VS_SENSEVOICE.md)

---

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

## 📄 许可证

MIT License

---

**使用感受请反馈！** 🚀