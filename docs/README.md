# VidSnap 文档中心

这套文档的目标是让新人先跑通，再理解架构，最后能安全接手开发和部署。根目录 [README.md](../README.md) 负责 5 秒内讲清楚项目；`docs/` 负责可执行细节和长期维护规则。

## 推荐阅读路径

新开发者：

1. [快速开始](getting-started.md)
2. [配置手册](configuration.md)
3. [系统架构](architecture.md)
4. [贡献指南](contributing.md)

后端或 AI 管线开发：

1. [系统架构](architecture.md)
2. [配置手册](configuration.md)
3. [故障排查](troubleshooting.md)
4. [P0 Query-first 验收](vidsnap-p0-query-first-todo.md)
5. [异步任务验收](vidsnap-async-job-acceptance.md)

部署或运维：

1. [部署与生产环境](deployment.md)
2. [配置手册](configuration.md)
3. [故障排查](troubleshooting.md)

产品和验收：

1. [Slim 产品边界](vidsnap-slim-product-boundary.md)
2. [P0 Query-first 验收](vidsnap-p0-query-first-todo.md)
3. [异步任务验收](vidsnap-async-job-acceptance.md)
4. [更新日志](changelog.md)

## 文档分层

| 文档 | 解决的问题 |
| --- | --- |
| [README.md](../README.md) | 这是什么、怎么跑、核心架构是什么 |
| [getting-started.md](getting-started.md) | 从零启动本地 Web + API，并完成第一个 planner/job 请求 |
| [architecture.md](architecture.md) | 模块边界、数据流、核心概念、API surface |
| [configuration.md](configuration.md) | 环境变量含义、默认值、生产注意事项 |
| [deployment.md](deployment.md) | Docker Compose、本地/生产部署、OSS 和 DashScope 注意事项 |
| [troubleshooting.md](troubleshooting.md) | 常见失败的定位步骤和修复命令 |
| [contributing.md](contributing.md) | 本地开发、测试、PR 和文档协作规则 |
| [changelog.md](changelog.md) | 重要变更和破坏性变更记录 |

## 文档维护规则

- 改动启动脚本、端口、环境变量或依赖时，同步更新 [README.md](../README.md)、[getting-started.md](getting-started.md) 和 [configuration.md](configuration.md)。
- 改动 workspace plan、skill、artifact 或 job 状态时，同步更新 [architecture.md](architecture.md) 和对应验收文档。
- 不在文档里写真实 API Key、AccessKey、签名 URL、cookie、日志片段中的敏感字段。
- README 只放最短路径；长解释放到 `docs/` 专题页。
- 文档里的命令必须能从仓库根目录或文档明确指定的目录运行。
