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
