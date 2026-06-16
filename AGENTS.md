# Repository Guidelines

## Project Structure & Module Organization

VidSnap is a FastAPI backend plus a Vite/React frontend. Backend code lives in `backend/app/`: `api/routes/` for endpoints, `services/` for video/transcript/AI/database workflows, `models/` for data models, and `core/` for config, auth, logging, Celery, and app setup. SQL lives in `backend/sql/` and `backend/database/migrations/`.

Frontend code lives in `frontend/src/`: `pages/` for route screens, `components/` for shared and feature UI, `components/ui/` for shadcn/ui primitives, `contexts/` for React context, `services/` for API clients, and `integrations/` for Supabase wiring. Public assets belong in `frontend/public/`.

## Build, Test, and Development Commands

- `./start_local.sh`: starts PostgreSQL/Redis with Docker Compose, then backend `8000` and frontend `8081`.
- `docker-compose up -d`: starts only PostgreSQL and Redis.
- `cd backend && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload`: runs the API.
- `cd frontend && npm run dev`: runs Vite.
- `cd frontend && npm run build`: builds `frontend/dist/`.
- `cd frontend && npm run lint`: runs ESLint.
- `cd backend && pytest`: runs backend tests when present.

## Coding Style & Naming Conventions

Use 4-space indentation for Python. Keep async service code explicit, name route modules by feature (`video.py`, `analysis.py`), and end service modules with `_service.py`. Keep environment reads centralized in `backend/app/core/config.py`.

Frontend code uses TypeScript, React function components, Tailwind CSS, and the `@/` alias for `frontend/src`. Name components in `PascalCase`, hooks as `useSomething`, and follow `frontend/eslint.config.js`.

## Testing Guidelines

There is currently no committed test suite in the active tree. Add backend tests under `backend/app/tests/` using `test_*.py` names and `pytest`/`pytest-asyncio` for async paths. Prefer focused service tests for transcript, video, database, and pipeline logic. Frontend tests are not configured; add tooling before committing UI tests.

## Commit & Pull Request Guidelines

Git history mostly uses concise Conventional Commit prefixes such as `feat:`, `fix:`, `chore:`, and `refactor:`. Keep messages imperative and scoped, for example `fix: handle empty transcript response`.

Pull requests should include a summary, affected backend/frontend areas, config or migration notes, and verification commands. Include screenshots or recordings for visible UI changes, and link issues when applicable.

## Security & Configuration Tips

Do not commit secrets, cookies, logs, or local `.env` files. Backend config expects values such as `DATABASE_URL`, `QWEN_API_KEY`, Aliyun OSS credentials, Google OAuth values, and SMTP credentials from the environment or `backend/.env`.
