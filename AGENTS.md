# Repository Guidelines

## Structure

VidSnap Harness is a Python src package. Runtime code is in src/vidsnap/: contracts, bounded loop, local video ports, providers, skills, API adapter, benchmark, and prompts. Offline tests are under tests/; benchmark profiles contain documentation only under benchmarks/.

## Commands

- python -m pytest -q: offline test suite.
- ruff format --check . and ruff check .: formatting and linting.
- mypy src: strict type checks.
- python -m build: sdist and wheel build.
- vidsnap --help and vidsnap conformance: package smoke and conformance checks.

## Rules

Use four-space Python indentation and strict typed public contracts. Add tests before production behavior. Keep model calls behind typed provider ports; model is fixed to qwen3.8-max, concurrency is at most two, and keys come only from local environment variables.

Never add users, authentication, databases, queues, Redis, Celery, OSS persistence, frontend code, job/history state, or arbitrary prompt/model/provider proxy endpoints. Do not commit credentials, media, RunBundles, datasets, benchmark results, cookies, or .env files.

## AI-native Development Protocol

Read PROJECT_STATE.md before any work; it is the single source of truth for the current main objective, task cards, and state transitions. Exactly one main objective may be IN_PROGRESS at a time.

Task states use only this seven-state vocabulary: PROPOSED, APPROVED, IN_PROGRESS, READY_FOR_REVIEW, VERIFIED, BLOCKED, RELEASED. Every transition is recorded in PROJECT_STATE.md with its reason.

Qoder CLI (Qwen3.8-Max or Kimi-K3) implements in TDD batches in an isolated worktree. Codex reviews each batch and independently reruns gates; the executor never self-certifies completion. CI is the independent verifier and its results are never rewritten or bypassed. Only the user decides whether to merge.

Never commit prohibited artifacts: credentials, media, datasets, RunBundles, benchmark results, cookies, .env files, or raw provider requests/responses. GitHub rulesets, security-scanning switches, and default-branch changes require explicit user authorization and remain only recorded in PROJECT_STATE.md until then.
