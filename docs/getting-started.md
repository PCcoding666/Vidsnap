# 快速开始

本文档用于把一个干净开发环境跑到第一个可验证结果。默认工作目录是仓库根目录：`/Users/chengpeng/MyProject/Vidsnap`。

## 1. 检查前置条件

```bash
python --version
node --version
npm --version
docker --version
ffmpeg -version
```

推荐版本：

| 依赖 | 版本 | 用途 |
| --- | --- | --- |
| Python | >= 3.10 | FastAPI 后端、AI/视频服务 |
| Node.js | >= 18 | Vite/React 前端 |
| Docker | current stable | 本地 PostgreSQL 和 Redis |
| FFmpeg | current stable | 视频/音频抽取与格式转换 |

Docker Desktop 需要处于运行状态。

## 2. 安装依赖

```bash
cd backend
python -m pip install -r requirements.txt

cd ../frontend
npm ci
```

如果 `npm ci` 因 lockfile 与 package 不一致失败，先确认是否需要保留当前 lockfile；本地临时开发可改用：

```bash
npm install
```

## 3. 准备环境变量

```bash
cp backend/.env.example backend/.env
```

最小可启动配置：

```bash
QWEN_API_KEY=your_dashscope_key
TRANSCRIPT_SERVICE_API_KEY=your_dashscope_key
TEMP_DIR=/tmp/video_analysis
```

真实视频转录还需要 OSS，因为 DashScope Paraformer 需要可访问的音频 URL：

```bash
ENABLE_OSS_UPLOADS=true
OSS_USE_SIGNED_URLS=true
OSS_SIGNED_URL_EXPIRES_SECONDS=86400
ALIYUN_ACCESS_KEY_ID=your_access_key_id
ALIYUN_ACCESS_KEY_SECRET=your_access_key_secret
ALIYUN_OSS_ENDPOINT=oss-ap-southeast-1.aliyuncs.com
ALIYUN_OSS_BUCKET=your_bucket_name
```

环境变量优先级：

1. 已存在的系统环境变量最高优先级。
2. 项目根目录 `.env` 填充缺失值。
3. `backend/.env` 继续填充缺失值。

`load_dotenv(..., override=False)` 会保留已经存在的环境变量；更早加载的值优先。

## 4. 一键启动

```bash
./start_local.sh
```

脚本会执行：

- 检查 `backend/.env`
- 检查 Docker
- 启动 PostgreSQL 和 Redis
- 启动后端 `uvicorn app.main:app --port 8000 --reload`
- 启动前端 `npm run dev -- --port 8081 --host 0.0.0.0`
- 将日志写到 `logs/backend.log` 和 `logs/frontend.log`

访问地址：

- Frontend: http://localhost:8081
- Backend: http://localhost:8000
- Swagger UI: http://localhost:8000/docs
- Health: http://localhost:8000/health

## 5. 手动启动

```bash
docker-compose up -d
```

终端 1：

```bash
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

终端 2：

```bash
cd frontend
npm run dev -- --port 8081 --host 0.0.0.0
```

## 6. Smoke tests

### Health

```bash
curl http://localhost:8000/health
```

期望返回：

```json
{"status":"healthy","database_mode":"local"}
```

### Service status

```bash
curl http://localhost:8000/api/v1/video/status
```

这个接口能快速看 OSS、DashScope、数据库等服务是否可用。

### Planner

Planner 不需要上传视频，适合验证 workspace API 和技能计划：

```bash
curl -X POST http://localhost:8000/api/v1/workspace/plan \
  -H "Content-Type: application/json" \
  -d '{"query":"帮我定位视频里讲 attention 的片段"}'
```

期望看到：

- `status: "success"`
- `plan.artifact_type`
- `plan.steps`
- `validation.valid: true`

### Async workspace job

```bash
curl -X POST http://localhost:8000/api/v1/workspace/jobs \
  -F "video_file=@/absolute/path/to/video.webm" \
  -F "query=把这个课程整理成结构化笔记" \
  -F "provider=paraformer"
```

返回里会包含 `job_id`。继续轮询：

```bash
curl http://localhost:8000/api/v1/workspace/jobs/job_xxxxxxxxxxxxxxxx
curl http://localhost:8000/api/v1/workspace/jobs/job_xxxxxxxxxxxxxxxx/artifact
```

任务成功前，artifact 端点可能返回 `404 artifact not ready`，这是预期行为。

### Legacy direct processing

短视频同步处理路径：

```bash
curl -X POST http://localhost:8000/api/v1/video/process \
  -F "video_file=@/absolute/path/to/video.webm"
```

这个接口会等处理完成后返回结果。长视频和可恢复任务优先使用 `/api/v1/workspace/jobs`。

## 7. 常用开发验证

```bash
cd backend
pytest

cd ../frontend
npm run lint
npm run build
```

## 8. 停止服务

`start_local.sh` 会输出 PID 到 `logs/`。如果没有专用停止脚本，可手动停止：

```bash
pkill -f "uvicorn app.main:app"
pkill -f "vite"
docker-compose down
```

保留数据库数据时不要删除 Docker volumes。需要彻底清理本地数据库时再使用：

```bash
docker-compose down -v
```
