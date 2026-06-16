# 故障排查

排查顺序建议：先确认服务是否启动，再看配置是否加载，再定位外部服务网络和权限。

## 服务没起来

检查 Docker：

```bash
docker ps
docker-compose ps
```

检查端口：

```bash
lsof -nP -iTCP:8000 -sTCP:LISTEN
lsof -nP -iTCP:8081 -sTCP:LISTEN
lsof -nP -iTCP:5432 -sTCP:LISTEN
lsof -nP -iTCP:6379 -sTCP:LISTEN
```

查看日志：

```bash
tail -f logs/backend.log
tail -f logs/frontend.log
```

如果端口被旧进程占用：

```bash
pkill -f "uvicorn app.main:app"
pkill -f "vite"
```

## 后端找不到环境变量

检查文件：

```bash
test -f backend/.env && echo ok
```

检查加载规则：

- 系统环境变量优先。
- 根目录 `.env` 填充缺失值。
- `backend/.env` 再填充缺失值。
- `override=False` 不会覆盖已存在变量。

如果修改 `.env` 后服务还使用旧值，重启后端进程。

## `/health` 正常但前端请求失败

确认后端业务前缀是 `/api/v1`：

```bash
curl http://localhost:8000/health
curl http://localhost:8000/api/v1/video/status
curl http://localhost:8000/api/v1/workspace/skills
```

开发环境前端 API client 使用 `/api/v1` 走 Vite 代理。若代理未配置或端口不一致，直接访问后端 API 验证问题是否在前端代理层。

## OSS 不可用

先看服务状态：

```bash
curl http://localhost:8000/api/v1/video/status
```

必要配置：

```bash
ENABLE_OSS_UPLOADS=true
ALIYUN_ACCESS_KEY_ID=...
ALIYUN_ACCESS_KEY_SECRET=...
ALIYUN_OSS_ENDPOINT=oss-ap-southeast-1.aliyuncs.com
ALIYUN_OSS_BUCKET=...
OSS_USE_SIGNED_URLS=true
```

常见原因：

- `ENABLE_OSS_UPLOADS=false`，服务会主动跳过 OSS。
- endpoint 写错 region，bucket 不在该 region。
- AccessKey 没有目标 bucket 权限。
- bucket 私有但没有使用签名 URL。
- 服务器网络无法访问 OSS endpoint。

建议用 `ossutil` 或阿里云控制台单独验证 AccessKey 和 bucket 权限。不要把 ossutil credential 文件提交到仓库。

## Paraformer 转录失败

常见错误：

- DashScope key 无效或欠费。
- Paraformer 无法拉取音频 URL。
- OSS 签名 URL 过期。
- 网络代理导致连接重置或 TLS EOF。
- 视频无音轨或音频抽取失败。

排查：

```bash
curl http://localhost:8000/api/v1/video/status
tail -f logs/backend.log
```

确认：

- `TRANSCRIPT_SERVICE_API_KEY` 或 `QWEN_API_KEY` 已设置。
- `ENABLE_OSS_UPLOADS=true`。
- `OSS_USE_SIGNED_URLS=true`。
- 签名 URL 有效期大于转录处理时间。
- 后端进程能访问 DashScope endpoint。

如果是瞬时网络错误，Paraformer service 会按配置重试：

```bash
PARAFORMER_TRANSCRIPTION_SUBMIT_RETRIES=3
PARAFORMER_TRANSCRIPTION_FETCH_RETRIES=5
PARAFORMER_TRANSCRIPTION_RETRY_BASE_SECONDS=2
```

## 代理问题

`start_local.sh` 会自动尝试：

1. `VIDSNAP_HTTP_PROXY` / `VIDSNAP_HTTPS_PROXY`
2. macOS 系统代理
3. `127.0.0.1:33210`
4. 直连

手动指定：

```bash
export VIDSNAP_HTTP_PROXY=http://127.0.0.1:7890
export VIDSNAP_HTTPS_PROXY=http://127.0.0.1:7890
./start_local.sh
```

确保本地服务不走代理：

```bash
export no_proxy="${no_proxy:+$no_proxy,}localhost,127.0.0.1,::1"
export NO_PROXY="${NO_PROXY:+$NO_PROXY,}localhost,127.0.0.1,::1"
```

## FFmpeg 缺失或音频抽取失败

检查：

```bash
ffmpeg -version
ffprobe -version
```

macOS 安装：

```bash
brew install ffmpeg
```

如果视频无音轨，转录应明确失败或返回无可转录内容，后续摘要/问答不能伪造结果。

## PostgreSQL 连接失败

检查容器：

```bash
docker-compose ps postgres
docker logs vidsnap-postgres --tail 100
```

检查连接串：

```bash
echo "$DATABASE_URL"
```

本地默认：

```text
postgresql+asyncpg://vidsnap:vidsnap_secret_2024@localhost:5432/vidsnap
```

如果初始化 SQL 没执行，通常是 volume 已经存在。需要重建时：

```bash
docker-compose down -v
docker-compose up -d
```

这会删除本地数据库数据。

## Workspace job 一直没有 artifact

查询 job：

```bash
curl http://localhost:8000/api/v1/workspace/jobs/job_xxxxxxxxxxxxxxxx
```

看这些字段：

- `status`
- `stage`
- `progress`
- `retryable`
- `failed_stage`
- `error`
- `transcript_segments_count`
- `artifact_available`

未完成时 `/artifact` 返回 404 是正常行为。失败且 `retryable=true` 时：

```bash
curl -X POST http://localhost:8000/api/v1/workspace/jobs/job_xxxxxxxxxxxxxxxx/retry
```

当前 job runner 是进程内状态；重启后端后旧 job 状态会丢失。

## Planner 结果不符合预期

运行评估：

```bash
cd backend
pytest app/tests/test_workspace_planner.py
```

查看 API 评估：

```bash
curl http://localhost:8000/api/v1/workspace/evals/planner
```

如果新增 query 类型，应同步更新：

- `backend/app/services/planner_service.py`
- `backend/app/services/skill_registry_service.py`
- `backend/app/evals/planner_eval_set.json`
- `backend/app/tests/test_workspace_planner.py`
- [architecture.md](architecture.md)
- [vidsnap-p0-query-first-todo.md](vidsnap-p0-query-first-todo.md)
