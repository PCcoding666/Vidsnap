# 部署与生产环境

VidSnap 当前提供本地开发的一键脚本和 Docker Compose 依赖服务。生产部署需要额外补齐进程管理、反向代理、密钥管理、数据库运维和任务队列持久化。

## 本地开发部署

```bash
./start_local.sh
```

本地服务：

| 服务 | 地址 | 说明 |
| --- | --- | --- |
| Frontend | `http://localhost:8081` | Vite dev server。 |
| Backend | `http://localhost:8000` | FastAPI + hot reload。 |
| Swagger | `http://localhost:8000/docs` | OpenAPI 文档。 |
| PostgreSQL | `localhost:5432` | `docker-compose.yml` 启动。 |
| Redis | `localhost:6379` | `docker-compose.yml` 启动。 |

只启动依赖：

```bash
docker-compose up -d
```

停止依赖但保留数据：

```bash
docker-compose down
```

清空本地数据库和 Redis volume：

```bash
docker-compose down -v
```

## 后端进程

开发命令：

```bash
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

生产建议：

```bash
cd backend
uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 2
```

生产不要直接暴露 Uvicorn 到公网。放在 Nginx、Caddy、Traefik 或云负载均衡后面。

## 前端构建

```bash
cd frontend
npm ci
npm run build
```

构建产物在 `frontend/dist/`。生产环境可以由 Nginx/Caddy 静态托管，也可以交给对象存储/CDN。

生产 `VITE_API_BASE_URL` 应指向带 `/api/v1` 的后端地址，例如：

```bash
VITE_API_BASE_URL=https://vidsnap.example.com/api/v1
```

## 反向代理要求

上传和长任务场景需要代理层调整：

| 项 | 建议 |
| --- | --- |
| 上传体积 | 至少覆盖目标视频大小，例如 `client_max_body_size 1G`。 |
| 请求超时 | 同步 `/video/process` 可能较长；推荐用户路径走 `/workspace/jobs`。 |
| SSE | `/api/v1/workspace/jobs/{job_id}/events` 需要禁用代理缓冲。 |
| WebSocket | `/api/v1/ws/...` 需要 `Upgrade` 和 `Connection` 头。 |
| CORS | 生产后端只允许正式前端域名。 |

Nginx 片段示例：

```nginx
server {
    listen 443 ssl;
    server_name vidsnap.example.com;

    client_max_body_size 1G;

    location /api/ {
        proxy_pass http://127.0.0.1:8000/api/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_read_timeout 3600;
        proxy_send_timeout 3600;
    }

    location /api/v1/workspace/jobs/ {
        proxy_pass http://127.0.0.1:8000/api/v1/workspace/jobs/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_buffering off;
        proxy_read_timeout 3600;
    }

    location / {
        root /srv/vidsnap/frontend/dist;
        try_files $uri /index.html;
    }
}
```

根据实际路径合并 location，避免重复规则覆盖。

## 数据库

本地：

- PostgreSQL 15 Alpine
- 初始 SQL：`backend/database/migrations/001_init_schema.sql`
- 默认用户：`vidsnap`
- 默认库：`vidsnap`

生产建议：

- 使用托管 PostgreSQL 或独立数据库主机。
- 替换默认密码，不把数据库暴露到公网。
- 建立备份和恢复演练。
- 把 SQL migration 纳入发布流程，而不是依赖容器首次初始化。
- 将 `DATABASE_URL` 作为环境变量注入后端进程。

## Redis 和任务队列

当前 workspace job runner 是 API 进程内实现，状态保存在内存里，输入文件保存在 `TEMP_DIR/workspace_jobs/{job_id}`。这适合 P0/P1 开发，但生产存在限制：

- API 进程重启会丢失 job 状态。
- 多 worker 或多实例下 job 状态不共享。
- 输入文件依赖本机磁盘。

生产化方向：

- 使用 Celery/RQ/云任务队列承接同一 `/workspace/jobs` contract。
- 将 job 状态持久化到 PostgreSQL。
- 将原始输入和中间音频放到 OSS，并记录对象 key。
- 让 worker 与 API 共享数据库和对象存储，而不是共享本地磁盘。

## OSS 部署要求

Paraformer 需要能访问音频 URL。生产环境建议：

- `ENABLE_OSS_UPLOADS=true`
- `OSS_USE_SIGNED_URLS=true`
- 使用私有 bucket + 签名 URL。
- bucket region 尽量靠近 DashScope endpoint 和服务器 region。
- 配置生命周期规则清理临时音频、视频和失败任务遗留对象。
- 仅授予 VidSnap 专用 RAM 用户访问目标 bucket 的最小权限。
- 后端日志不要输出签名 URL。

常见 endpoint 形式：

```bash
ALIYUN_OSS_ENDPOINT=oss-ap-southeast-1.aliyuncs.com
ALIYUN_OSS_BUCKET=your_bucket_name
```

## DashScope 部署要求

生产至少设置：

```bash
QWEN_API_KEY=...
TRANSCRIPT_SERVICE_API_KEY=...
```

网络策略：

- 确认服务器能访问 DashScope 和 OSS endpoint。
- 如果服务器出网需要代理，使用 `VIDSNAP_HTTP_PROXY`/`VIDSNAP_HTTPS_PROXY`，并保持 `localhost,127.0.0.1,::1` 在 no_proxy。
- 如果默认 endpoint 在当前网络不可用，设置 `DASHSCOPE_HTTP_BASE_URL`。

## 安全检查清单

上线前必须确认：

- `JWT_SECRET` 已替换为强随机值。
- FastAPI CORS 不再是 `allow_origins=["*"]`。
- `.env`、cookie、AccessKey、DashScope key 不进入 Git。
- 代理和应用日志不会记录 Authorization、签名 URL、API key。
- OSS AccessKey 是最小权限，并支持定期轮换。
- 数据库密码不是 `vidsnap_secret_2024`。
- 反向代理限制上传大小、请求超时和 HTTPS。
- 有失败重试、告警和日志留存策略。

## 发布验证

后端：

```bash
curl https://vidsnap.example.com/health
curl https://vidsnap.example.com/api/v1/video/status
curl -X POST https://vidsnap.example.com/api/v1/workspace/plan \
  -H "Content-Type: application/json" \
  -d '{"query":"生成课程复习笔记"}'
```

前端：

```bash
cd frontend
npm run build
```

后端测试：

```bash
cd backend
pytest
```
