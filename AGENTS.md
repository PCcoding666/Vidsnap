# Repository Guidelines

Public instructions for any coding agent working in this repository. Follow them exactly. If a requested change conflicts with this document, surface the conflict instead of proceeding silently.

## Architecture

VidSnap Harness is a Python src-layout package. All runtime code lives in src/vidsnap/, organized around these components:

- contracts — typed public contracts shared across every module. This is the integration surface of the project.
- Core runtime — the bounded loop that orchestrates a run. It executes only registered tools and plugins through contracts, under declared budgets. It calls model/provider capabilities only through typed ports — never raw clients, endpoints, or credentials.
- Local video ports — file-system-backed ports for local video and subtitle ingestion. These are the only components that touch user media.
- Providers — model adapters behind typed provider ports. Qwen is the locked default/reference provider (qwen3.8-max); the bundled Qwen provider enforces concurrency of at most two; keys come only from local environment variables. An application may inject a conforming ProviderProtocol before a run; provider, model, or base_url cannot be switched during a run.
- Bounded tools and plugins — the capability layer. Tools and plugins are registered explicitly, validated against allow-lists, and constrained by explicit budgets. Neither spawns shells, browsers, or network connections on its own.
- Recipes — versioned task packages with fixed goals and budgets, implemented as typed Python models plus their adapters, runners, and renderers — not merely declarative data.
- RunBundles — write-once run artifacts recording immutable, auditable events plus outputs. They are never committed to the repository.
- API adapter — thin adapter exposing the core runtime; it holds no business logic.
- Benchmark and prompts — benchmark definitions and prompt templates. Benchmark profiles under benchmarks/ are documentation only.
- Offline trace/replay — every run records immutable events; traces replay offline against recorded fixtures with no network and no model calls.

Dependency direction: contracts depend on nothing; tools and plugins implement contract interfaces; providers implement the typed provider ports; the core runtime depends on contracts and the typed provider ports, calling model/provider capabilities only through them; the API adapter depends on the core runtime; trace/replay depends only on contracts and event records. Nothing depends on the API adapter.

## Scope and boundaries

VidSnap Harness is a local, single-user harness for bounded video analysis runs with Qwen as the locked default/reference provider behind typed provider ports (a conforming ProviderProtocol is injectable before a run). It intentionally excludes:

- Users, authentication, accounts, multi-tenancy, or SaaS integration.
- Databases, queues, Redis, Celery, or OSS persistence.
- Frontend code or job/history state.
- Arbitrary prompt/model/provider proxy endpoints.

Stay within this scope. Changes outside it require an explicit, separate decision; do not fold them into unrelated work.

## Tests

- Add or update tests before changing production behavior.
- Tests must be offline and deterministic: no network, no model calls, no real media. Use recorded fixtures and offline replay.
- Preserve compatibility: public contracts, recipe and RunBundle formats, CLI behavior, and conformance checks change only through an explicit, versioned, tested change — never silently.
- Keep changes minimal and scoped to the task; no drive-by refactors.
- Preserve user/source data: never modify, move, or delete user data or fixtures as a side effect of a change or cleanup.
- Every change must pass the exact public gates:
  - ruff format --check src tests scripts
  - ruff check .
  - mypy src
  - python -m pytest -q
  - python -m build
  - vidsnap conformance
  - python scripts/secret_scan.py
  - git diff --check

Four-space Python indentation and strict typed public contracts are enforced by these gates.

## Security

Never commit, publish, or embed in artifacts or fixtures: credentials, API keys, cookies, .env files, media, datasets, RunBundles, benchmark results, or raw provider requests/responses.

- Keys come only from local environment variables; never log them, serialize them into traces, or hard-code them.
- Never weaken, bypass, or rewrite gates, conformance checks, or security tooling to make a change pass.

## Allowed patterns

- Typed ports: model and video access only behind explicit typed interfaces.
- Allow-lists: tools, paths, commands, and URL schemes validated against explicit lists.
- Explicit budgets: step, time, token, and size limits declared up front and enforced by the core runtime.
- Immutable, auditable events: append-only run records that replay offline.
- Provider pinning: Qwen (qwen3.8-max) as the locked default/reference; a conforming ProviderProtocol may be injected by the application before a run; concurrency of at most two, enforced by the bundled Qwen provider (custom providers may differ); environment-variable key sourcing; no provider, model, or base_url switching during a run.

## Forbidden patterns

- Arbitrary shell, browser, URL, model, prompt, or provider execution — anything not routed through an allow-listed, budgeted tool.
- Silent contract changes: altering contracts, formats, defaults, or conformance behavior without tests and a versioned change.
- Networked unit tests: any test requiring network, model endpoints, or credentials.
- SaaS, accounts, databases, queues, frontend code, or job/history state.
