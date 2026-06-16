# 贡献指南

本文档面向接手 VidSnap 的开发者。目标是让改动可验证、范围清楚、不会把本地密钥或临时产物带进仓库。

## 开发环境

从仓库根目录开始：

```bash
cp backend/.env.example backend/.env

cd backend
python -m pip install -r requirements.txt

cd ../frontend
npm ci

cd ..
./start_local.sh
```

更多细节见 [快速开始](getting-started.md)。

## 分支和提交

提交信息使用简洁 Conventional Commit 前缀：

```text
feat: add workspace artifact versions
fix: handle empty transcript response
docs: refresh local setup guide
chore: update development dependencies
refactor: split workspace job state
```

保持提交聚焦。不要把格式化、重构、文档和功能实现混在一个大提交里，除非它们是同一个行为变更的必要部分。

## 代码边界

后端：

- 路由放在 `backend/app/api/routes/`。
- 业务流程放在 `backend/app/services/`。
- 配置读取只放在 `backend/app/core/config.py`。
- Pydantic contract 放在 `backend/app/models/`。
- 数据库 schema 和 migration 放在 `backend/database/migrations/` 或 `backend/sql/`。

前端：

- 页面放在 `frontend/src/pages/`。
- 业务组件放在 `frontend/src/components/`。
- shadcn/ui primitive 放在 `frontend/src/components/ui/`。
- API 请求和类型放在 `frontend/src/services/api.ts`。
- 全局配置放在 `frontend/src/config/`。

文档：

- 根 [README.md](../README.md) 保持短路径和架构入口。
- 细节放到 `docs/` 专题页。
- 改动环境变量、端口、API contract、脚本或部署方式时，同步更新文档。

## 测试

后端：

```bash
cd backend
pytest
```

重点测试：

```bash
pytest app/tests/test_workspace_planner.py
pytest app/tests/test_workspace_jobs.py
pytest app/tests/test_paraformer_retry.py
```

前端：

```bash
cd frontend
npm run lint
npm run build
```

当前前端没有单元测试框架。新增 UI 测试前，需要先引入并文档化测试工具链。

## API 验证

最小 smoke test：

```bash
curl http://localhost:8000/health
curl http://localhost:8000/api/v1/video/status
curl http://localhost:8000/api/v1/workspace/skills
curl -X POST http://localhost:8000/api/v1/workspace/plan \
  -H "Content-Type: application/json" \
  -d '{"query":"生成课程复习笔记"}'
```

涉及真实转录、OSS、DashScope 的改动，至少用一个短视频跑通 `/api/v1/workspace/jobs` 或 `/api/v1/video/process`。

## Query-first 改动规则

改动 planner、skill、artifact 或 job contract 时，需要同步检查：

- `backend/app/models/workspace.py`
- `backend/app/services/planner_service.py`
- `backend/app/services/skill_registry_service.py`
- `backend/app/services/workspace_service.py`
- `backend/app/services/workspace_job_service.py`
- `frontend/src/services/api.ts`
- `backend/app/evals/planner_eval_set.json`
- `backend/app/tests/test_workspace_planner.py`
- [architecture.md](architecture.md)
- [vidsnap-p0-query-first-todo.md](vidsnap-p0-query-first-todo.md)

Planner P0 必须保持确定性。同一个 query 不应依赖随机模型输出生成不同 plan。

## 安全规则

不要提交：

- `.env`
- API Key
- AccessKey
- cookie
- 签名 URL
- `logs/`
- 大视频文件
- ossutil credential 文件
- 本地数据库 dump

如果需要分享失败日志，先删除：

- `Authorization` header
- `access_token`
- `refresh_token`
- `Signature`
- `Expires`
- DashScope/OSS key
- 用户邮箱、手机号等个人信息

## PR 清单

提交 PR 前确认：

- 改动范围和标题一致。
- 后端测试或前端 lint/build 已运行，或者说明为什么不能运行。
- 新增环境变量已更新 `backend/.env.example` 和 [configuration.md](configuration.md)。
- API contract 变更已更新前端类型和 [architecture.md](architecture.md)。
- 可见 UI 改动有截图或录屏。
- 数据库 schema 变更有迁移说明。
- 没有提交 secret、日志、视频样本或本地配置。

## 文档质量标准

文档不是最后补的注释，而是开发者体验的一部分。新增能力至少回答：

- 它解决什么用户问题？
- 本地怎么跑？
- 依赖哪些配置？
- 失败时怎么排查？
- 哪些测试证明它工作？
- 是否影响部署或生产安全？
