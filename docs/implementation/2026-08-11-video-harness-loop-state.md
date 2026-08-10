# Video Harness Implementation Loop State

## Current state

- Decision: execute the approved clean Harness Core migration on `codex/video-harness-core` in an isolated worktree.
- Decision: no credential from chat will be used; only local environment variables are eligible for a future live benchmark.
- Baseline: `cd backend && python -m pytest -q` passed, 49 tests; one `pytest-asyncio` deprecation warning from the legacy stack.
- Existing user modifications remain only in the original worktree and are not part of this branch.

## Active slice

Create versioned core contracts and the LoopSpec conformance foundation with offline TDD tests.

## Verification evidence

- 2026-08-11: isolated worktree created at `/Users/chengpeng/MyProject/Vidsnap-video-harness-core` on `codex/video-harness-core`.
- 2026-08-11: legacy baseline backend tests: 49 passed.
- 2026-08-11: package smoke test RED (`ModuleNotFoundError: vidsnap`), then GREEN: `2 passed`.
- 2026-08-11: editable package install, installed `vidsnap --help`, Ruff format/check for package files, and sdist/wheel build succeeded.
- 2026-08-11: the source tree is deliberately tracked; only local virtualenv/cache/run output paths were added to `.gitignore`.

## Next step

Write the LoopSpec and result-contract tests, observe the missing-contract RED state, then implement the strict versioned schemas.
