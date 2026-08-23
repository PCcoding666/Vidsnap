# Contributing

Use Python 3.10+ and install the development extras:

    python -m pip install -e '.[server,dev]'

Before submitting a change, add offline TDD coverage and run:

    ruff format --check .
    ruff check .
    mypy src
    python -m pytest -q
    python -m build
    vidsnap conformance

Do not commit credentials, local media, datasets, generated RunBundles, benchmark outputs, cookies, or .env files. Changes may not introduce SaaS state, databases, queues, accounts, arbitrary model routing, or a frontend.

## AI-native Development Protocol

Read PROJECT_STATE.md first; it is the single source of truth for the current main objective, task cards, and state transitions. All work starts from a task card with six required fields: objective, non-goals, acceptance evidence, authority/data/secret boundaries, owner/executor/reviewer, and next human gate. Exactly one main objective may be IN_PROGRESS at a time.

Task states use only this seven-state vocabulary: PROPOSED, APPROVED, IN_PROGRESS, READY_FOR_REVIEW, VERIFIED, BLOCKED, RELEASED. Every transition is recorded in PROJECT_STATE.md with its reason.

The main loop: Qoder CLI is the implementation worker for maintainer-run agentic changes, implementing in TDD batches on one shared branch; human contributors may implement directly, provided they follow the Task Contract, tests, CI, and the user merge gate. Codex reviews each batch and independently reruns the focused gate; CI independently verifies the single Draft PR; only the user decides whether to merge. The executor never self-certifies completion.

Do not commit prohibited artifacts: credentials, media, datasets, RunBundles, benchmark results, cookies, .env files, or raw provider requests/responses. Do not configure GitHub rulesets, security-scanning switches, or the default branch without explicit user authorization.
