# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What VidSnap is

VidSnap is an AI-native workspace for local video files: a user uploads a video and writes a natural-language goal ("query-first"), and the system turns the video into searchable, citable, reusable text assets. The transcript (from Aliyun Fun-ASR-Flash) is the single source of truth; summaries, notes, timestamps, and Q&A are all derived from it. **Key-frame / visual analysis is an opt-in, plan-driven capability** (`visual_mode` = `auto`/`on`/`off`, default `auto`): frames are extracted only when the query asks for visuals (auto) or `visual_mode=on`; `off` forces text-only with no image skills in the plan.

This is the "slim" variant (`vidsnap_slim` branch): only the video-analysis core is kept, and it runs on a local PostgreSQL database (the earlier hosted-BaaS integration has been removed; the local sync-store compat layer is `store_service.py`).

## Commands

```bash
# Full local environment (Docker Postgres+Redis, then backend:8000 + frontend:8081)
./start_local.sh                 # requires backend/.env and a running Docker

# Infra only
docker-compose up -d             # Postgres (5432) + Redis (6379)

# Backend
cd backend && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
cd backend && pytest             # tests live in backend/app/tests/ (test_*.py)
cd backend && pytest app/tests/test_x.py::test_name   # single test

# Frontend (Vite/React, http://localhost:8081)
cd frontend && npm run dev -- --port 8081 --host 0.0.0.0
cd frontend && npm run build     # outputs frontend/dist/
cd frontend && npm run lint      # ESLint (eslint.config.js)
```

Swagger UI: http://localhost:8000/docs · Health: http://localhost:8000/health

## Configuration

Env loading order (in `backend/app/core/config.py`): system env > project-root `.env` > `backend/.env` (each only fills missing values). `start_local.sh` requires `backend/.env` to exist. All env reads are centralized in `core/config.py` — add new settings there, not inline.

Notable: `DASHSCOPE_API_KEY` is a computed property with precedence `TRANSCRIPT_SERVICE_API_KEY > QWEN_API_KEY > DASHSCOPE_API_KEY`. `settings.oss_available` gates real transcription. For planner/API-only work you can leave `ENABLE_OSS_UPLOADS=false`; **real Paraformer transcription needs OSS enabled** because Paraformer fetches audio from a cloud-accessible (signed) URL.

## Backend architecture (`backend/app/`)

- `api/routes/` — feature-named endpoints (`workspace.py`, `video.py`, `analysis.py`, `auth.py`, `user.py`, `websocket.py`). Routes registered in `main.py`.
- `services/` — all business logic; modules end in `_service.py`. Core flow:
  - `planner_service.py` — **deterministic, rule-based** (P0) mapping of a query → `SkillPlan` (keyword matching against term sets). Kept rule-based so plan quality is reproducibly evaluable against a golden set; LLM planning can later slot behind the same `SkillPlan` contract.
  - `pipeline_service.py` (`AliyunVideoProcessingPipeline`) — orchestrates video → audio extraction → transcription → LLM analysis, producing unified metadata.
  - `paraformer_service.py` — Fun-ASR-Flash transcription (chunking, retries, polling; tunable via `PARAFORMER_*` env vars).
  - `oss_service.py` — uploads audio to Aliyun OSS and produces signed URLs for Paraformer.
  - `llm_service.py` — Qwen/DashScope LLM calls for summaries/notes/Q&A.
  - `workspace_job_service.py` — **resumable async jobs run as in-process `asyncio.Task`s** (`self.tasks: Dict[str, asyncio.Task]`), tracking stage progress, retries, and versioned artifacts. This is the primary execution path.
  - `video_service.py`, `transcription_provider_service.py`, `skill_registry_service.py`, `chat_service.py`, `database_service.py`.
- `core/` — `config.py`, auth, logging, app setup, and `celery_app.py`. **Note:** Celery is configured but `include=[]` and not wired into the main job flow — the workspace pipeline uses asyncio tasks, not Celery. Don't assume Celery runs jobs.
- `models/` — Pydantic/data models (`workspace.py`, `analysis.py`, `video.py`).
- SQL: `backend/sql/` and `backend/database/migrations/` (the latter is mounted into Postgres as `docker-entrypoint-initdb.d`, so it runs on first DB init).

### Workspace job API flow

`POST /api/v1/workspace/plan` (no upload, planner only) → `POST /api/v1/workspace/jobs` (upload video + query → `job_id`) → poll `GET /workspace/jobs/{job_id}`, fetch `/artifact`, stream `/events` (SSE), `/retry`, `/qa`, add `/artifacts` versions.

## Frontend (`frontend/src/`)

Vite + React + TypeScript + Tailwind + shadcn/ui. `pages/` route screens, `components/` (with `components/ui/` shadcn primitives), `contexts/` React context, `services/` API clients, `i18n/` localization. Use the `@/` alias for `frontend/src`. Components `PascalCase`, hooks `useSomething`.

## Conventions

- Python: 4-space indent, explicit async service code, route modules named by feature, service modules end in `_service.py`.
- Commits: Conventional Commit prefixes (`feat:`, `fix:`, `chore:`, `refactor:`), imperative and scoped. Commit messages and code comments in this repo are frequently in Chinese — match the surrounding style.
