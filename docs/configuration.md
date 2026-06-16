# 配置手册

VidSnap 的后端配置集中在 [backend/app/core/config.py](../backend/app/core/config.py)。本地开发通常使用 `backend/.env`；部署环境应使用平台 Secret 或系统环境变量。

## 加载规则

后端启动时会加载：

1. 已存在的系统环境变量。
2. 项目根目录 `.env`，仅填充缺失值。
3. `backend/.env`，仅填充缺失值。

因为 `override=False`，系统环境变量不会被 `.env` 覆盖；根目录 `.env` 的值也不会被 `backend/.env` 覆盖。

`start_local.sh` 会检查 `backend/.env` 是否存在，因此即使主要配置放在根目录 `.env`，本地也建议保留一个 `backend/.env`。

## 后端核心配置

| 变量 | 默认值 | 必填 | 说明 |
| --- | --- | --- | --- |
| `DATABASE_URL` | `postgresql+asyncpg://vidsnap:vidsnap_secret_2024@localhost:5432/vidsnap` | 本地否，生产是 | 本地 PostgreSQL 连接串。生产必须替换密码和主机。 |
| `JWT_SECRET` | `your-super-secret-jwt-key-change-in-production` | 生产是 | JWT 签名密钥。生产必须使用强随机值。 |
| `JWT_LIFETIME_SECONDS` | `604800` | 否 | JWT 有效期，默认 7 天。 |
| `TEMP_DIR` | `/tmp/video_analysis` | 否 | 上传、音频抽取、workspace job 输入缓存目录。 |
| `APP_URL` | `https://vidsnap.space` | 否 | 邮件链接和对外应用 URL。 |

## DashScope 和 LLM

| 变量 | 默认值 | 必填 | 说明 |
| --- | --- | --- | --- |
| `QWEN_API_KEY` | 空 | 是 | Qwen/LLM 服务密钥。也作为 DashScope 后备密钥。 |
| `TRANSCRIPT_SERVICE_API_KEY` | 空 | 转录建议填 | 音频转录专用密钥，优先级高于 `QWEN_API_KEY`。 |
| `DASHSCOPE_API_KEY` | 空 | 否 | 兼容旧环境变量；仅在前两者为空时作为后备。 |
| `DASHSCOPE_HTTP_BASE_URL` | 空 | 否 | 自定义 DashScope HTTP base URL。网络或地域需要切换 endpoint 时使用。 |

密钥选择优先级：

```text
TRANSCRIPT_SERVICE_API_KEY -> QWEN_API_KEY -> DASHSCOPE_API_KEY
```

## Paraformer 转录

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `PARAFORMER_TRANSCRIPTION_SUBMIT_RETRIES` | `3` | 提交转录任务的瞬时错误重试次数。 |
| `PARAFORMER_TRANSCRIPTION_FETCH_RETRIES` | `5` | 拉取任务状态时允许的连续瞬时错误次数。 |
| `PARAFORMER_TRANSCRIPTION_RETRY_BASE_SECONDS` | `2` | 指数退避基础秒数。 |
| `PARAFORMER_MAX_WAIT_SECONDS` | `1800` | 单个转录任务最长等待时间。 |
| `PARAFORMER_POLL_INTERVAL_SECONDS` | `5` | 轮询任务状态间隔。 |
| `PARAFORMER_AUDIO_FORMAT` | `flac` | 中间音频格式，默认使用压缩 mono 16kHz FLAC，避免长视频产生巨大 WAV。 |
| `PARAFORMER_CHUNK_SECONDS` | `1800` | 长音频切块秒数。 |
| `PARAFORMER_MAX_PARALLEL_CHUNKS` | `2` | 并发转录切块数量。 |
| `LOCAL_ASR_ENABLED` | `false` | 是否暴露本地 ASR provider。当前 P0 主要路径仍是 Paraformer。 |

## 阿里云 OSS

| 变量 | 默认值 | 必填 | 说明 |
| --- | --- | --- | --- |
| `ENABLE_OSS_UPLOADS` | `false` | 真实转录是 | 控制是否上传视频/音频到 OSS。Paraformer 需要可访问音频 URL，因此真实云转录应设为 `true`。 |
| `ALIYUN_ACCESS_KEY_ID` | 空 | OSS 开启时是 | 阿里云 AccessKey ID。 |
| `ALIYUN_ACCESS_KEY_SECRET` | 空 | OSS 开启时是 | 阿里云 AccessKey Secret。 |
| `ALIYUN_OSS_ENDPOINT` | 空 | OSS 开启时是 | OSS endpoint，可写 `oss-ap-southeast-1.aliyuncs.com`，服务会规范化协议前缀。 |
| `ALIYUN_OSS_BUCKET` | 空 | OSS 开启时是 | OSS bucket 名。 |
| `OSS_USE_SIGNED_URLS` | `true` | 否 | 返回签名 URL，适合私有 bucket 给 Paraformer 拉取音频。 |
| `OSS_SIGNED_URL_EXPIRES_SECONDS` | `86400` | 否 | 签名 URL 有效期，默认 24 小时。 |

最小权限建议：

- 单独创建用于 VidSnap 的 RAM 用户或 STS 角色。
- 权限只覆盖目标 bucket 的 `PutObject`、`GetObject`、`DeleteObject` 和必要的 multipart 操作。
- 开启 bucket 生命周期规则，清理 `audio/`、`videos/` 或临时对象。
- 不在日志和文档中输出签名 URL。

## 邮件和 OAuth

| 变量 | 默认值 | 必填 | 说明 |
| --- | --- | --- | --- |
| `GOOGLE_OAUTH_CLIENT_ID` | 空 | Google 登录时是 | Google OAuth client id。 |
| `GOOGLE_OAUTH_CLIENT_SECRET` | 空 | Google 登录时是 | Google OAuth client secret。 |
| `GMAIL_SMTP_USER` | 空 | 邮件通知时是 | SMTP 用户名。 |
| `GMAIL_SMTP_PASSWORD` | 空 | 邮件通知时是 | Gmail App Password 或 SMTP 密码。 |
| `GMAIL_SMTP_HOST` | `smtp.gmail.com` | 否 | SMTP host。 |
| `GMAIL_SMTP_PORT` | `587` | 否 | SMTP port。 |
| `GMAIL_SMTP_FROM` | 空 | 邮件通知时建议 | 发件人显示名和地址。 |

## 前端配置

前端配置位于 `frontend/.env.development` 和 `frontend/.env.production`。

| 变量 | 说明 |
| --- | --- |
| `VITE_API_BASE_URL` | 生产构建下的 API base URL。开发环境当前 API client 使用 `/api/v1` 触发 Vite 代理。 |
| `VITE_DISABLE_AUTH` | 设为 `true` 时开发环境可绕过部分前端认证保护。 |
| `VITE_SUPABASE_URL` / `VITE_SUPABASE_ANON_KEY` | 旧前端 Supabase 集成仍存在，但后端当前强制本地 PostgreSQL。新功能不应依赖 Supabase 作为主数据库。 |

前端开发默认：

```bash
cd frontend
npm run dev -- --port 8081 --host 0.0.0.0
```

## Docker Compose 配置

[docker-compose.yml](../docker-compose.yml) 提供本地开发依赖：

| 服务 | 端口 | 说明 |
| --- | --- | --- |
| `postgres` | `5432` | 本地数据库，初始化 SQL 来自 `backend/database/migrations/`。 |
| `redis` | `6379` | Redis，当前用于异步基础设施和未来任务队列能力。 |

`POSTGRES_PASSWORD` 可通过环境变量覆盖；默认值只适合本地开发。

## 代理配置

`start_local.sh` 启动后端时会按顺序设置代理：

1. 显式 `VIDSNAP_HTTP_PROXY`、`VIDSNAP_HTTPS_PROXY`、`VIDSNAP_ALL_PROXY`。
2. macOS 系统代理。
3. 常见本地代理 `127.0.0.1:33210`。
4. 未检测到代理时直连外部服务。

脚本会自动追加 `localhost,127.0.0.1,::1` 到 `no_proxy`/`NO_PROXY`，避免本地 API 和数据库走代理。

## 安全规则

- 不提交 `.env`、cookie、真实 AccessKey、DashScope key、签名 URL 或完整敏感日志。
- 文档示例只使用占位符。
- 生产环境不要使用默认 `JWT_SECRET`、默认 PostgreSQL 密码或全开放 CORS。
- 任何会进入日志的 URL 都要确认没有暴露签名参数、token 或 secret。
