# AGENTS.md

This file provides guidance to the AI agent when working with code in this repository.

## What this is

VidSnap (`vidsnap_slim` branch): FastAPI backend + Vite/React frontend, local-Postgres-only. The earlier hosted-BaaS integration is removed (compat shim: `backend/app/services/store_service.py`). Transcript from Aliyun Fun-ASR is the single source of truth; summaries/notes/QA are derived from it. Visual key-frame analysis is opt-in via `visual_mode` (`auto`/`on`/`off`, default `auto`).

## Commands

```bash
./start_local.sh            # Docker Postgres+Redis → backend:8000, frontend:8081. Requires backend/.env.
docker-compose up -d        # Infra only (Postgres 5432, Redis 6379)
cd backend && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
cd backend && pytest app/tests/<file>::<test>      # tests live in backend/app/tests/, test_*.py
cd frontend && npm run dev -- --port 8081 --host 0.0.0.0
cd frontend && npm run build && npm run lint
```

Health: `:8000/health` · Swagger: `:8000/docs` · Frontend: `:8081` (not 5173).

## Architectural gotchas (silently break if violated)

- **Workspace jobs are `asyncio.Task`s, NOT Celery.** `core/celery_app.py` exists but `include=[]` and is unused; the real executor is `services/workspace_job_service.py` (`self.tasks: Dict[str, asyncio.Task]`). Don't wire jobs into Celery.
- **Planner is deliberately rule-based** (`services/planner_service.py`, P0). Query → `SkillPlan` via keyword/term matching, kept deterministic so the golden-set can score it reproducibly. LLM planning must slot behind the same `SkillPlan` contract, not replace it.
- **Transcript is the single source of truth.** Don't infer visuals unless `visual_mode` resolves to needing them. Notes/QA must cite transcript timestamps.

## Configuration

- All env reads centralized in `backend/app/core/config.py` — add new settings there, never inline. Load order (each fills missing): **system env > project-root `.env` > `backend/.env`**. `start_local.sh` hard-fails if `backend/.env` is missing.
- `DASHSCOPE_API_KEY` precedence (computed): `TRANSCRIPT_SERVICE_API_KEY > QWEN_API_KEY > DASHSCOPE_API_KEY`.
- **Real Paraformer transcription needs OSS enabled** (it fetches audio via a signed URL). For planner-only work, leave `ENABLE_OSS_UPLOADS=false`.
- `JWT_SECRET` auto-generates per-process if unset — production must set a stable value via env.

## YouTube downloads

`FetchYouTube` is a thin wrapper — it does NOT bypass YouTube anti-bot. All three are required for real downloads: **Deno** (`brew install deno`) + **bgutil PO Token provider** (script mode, `BGUTIL_SCRIPT_PATH=...`) + browser cookies (`YOUTUBE_COOKIES_FROM_BROWSER=chrome`). Data-center IPs trigger the strictest regime. See README for the full three-piece config.

## Conventions

- Python: 4-space indent, explicit `async` service code. Route modules named by feature (`workspace.py`, `video.py`); service modules end in `_service.py`.
- Frontend: `@/` alias → `frontend/src`. Components PascalCase, hooks `useSomething`.
- **Commits and code comments are frequently in Chinese — match surrounding style.** Conventional Commits (`feat:`, `fix:`, `chore:`, `refactor:`), imperative, scoped. PR includes summary + affected areas + config/migration notes + verification commands.

## Security

Never commit secrets, cookies, logs, or `.env`. Before any open-source release, run `SECURITY_PREPUBLISH_CHECKLIST.md` (rotate leaked keys, scrub git history). Production: replace the auto-generated `JWT_SECRET`, tighten CORS (no `allow_origins=["*"]`), inject secrets only via env/secret-manager.