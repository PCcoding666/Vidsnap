# 更新日志

本文件记录对开发者、部署者或用户可见的重要变更。正式发布前先使用 `Unreleased`。

## Unreleased

### Documentation

- 重写根 [README.md](../README.md)，补齐黄金首屏、快速上手、API demo、架构图、文档地图和生产提示。
- 新增 [文档中心](README.md)，统一快速开始、架构、配置、部署、排障、协作和产品验收入口。
- 新增 [快速开始](getting-started.md)，覆盖本地依赖、`.env`、`start_local.sh`、手动启动和 smoke tests。
- 新增 [配置手册](configuration.md)，明确 DashScope、Paraformer、OSS、PostgreSQL、JWT、OAuth、SMTP、前端和代理配置。
- 新增 [系统架构](architecture.md)，记录 query-first 数据流、核心模块、API surface、job 状态和 planner 质量门槛。
- 新增 [部署与生产环境](deployment.md)，记录 Docker Compose、本地/生产部署、反向代理、OSS/DashScope 和安全清单。
- 新增 [故障排查](troubleshooting.md)，覆盖服务启动、环境变量、前端代理、OSS、Paraformer、代理、FFmpeg、数据库、workspace job 和 planner。
- 新增 [贡献指南](contributing.md)，明确目录边界、测试、PR、安全和文档同步要求。

### Backend

- Query-first workspace 已具备 planner、skill registry、同步 process、异步 jobs、artifact 版本、QA、SSE 和 planner eval API。
- Workspace job 当前为 API 进程内 runner，适合 P0/P1 开发；生产化需要持久化 job 状态并迁移到任务队列。
- 后端当前使用本地 PostgreSQL；早期云托管 BaaS 主数据库路径已移除，本地同步存储兼容层为 `store_service.py`。
- Paraformer 默认中间音频格式为 FLAC，并支持重试、轮询、切块和 provider 错误分类。
- OSS 支持 endpoint 规范化、私有 bucket 签名 URL 和可配置过期时间。

### Frontend

- 前端主线包含 query-first workspace 组件、artifact 展示、job 轮询和 transcript-backed 输出类型。
- 开发环境默认通过 Vite 访问 `/api/v1`，本地完整环境使用 `http://localhost:8081`。

### Operations

- 本地启动脚本 `start_local.sh` 启动 PostgreSQL、Redis、FastAPI 和 Vite，并自动尝试显式代理、macOS 系统代理和常见本地代理。
- 本地依赖通过 `docker-compose.yml` 提供 PostgreSQL 15 和 Redis 7。

## Earlier History

早期 README 中的 v2/v3 描述包含托管数据库优先、YouTube/多模态等历史方向，已经不再作为当前开发契约。当前权威产品边界见：

- [Slim 产品边界](vidsnap-slim-product-boundary.md)
- [P0 Query-first 验收](vidsnap-p0-query-first-todo.md)
- [异步任务验收](vidsnap-async-job-acceptance.md)
