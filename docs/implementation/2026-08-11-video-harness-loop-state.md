# Video Harness Implementation Loop State

## Current state

- Decision: execute the approved clean Harness Core migration on `codex/video-harness-core` in an isolated worktree.
- Decision: no credential from chat will be used; only local environment variables are eligible for a future live benchmark.
- Baseline: `cd backend && python -m pytest -q` passed, 49 tests; one `pytest-asyncio` deprecation warning from the legacy stack.
- Existing user modifications remain only in the original worktree and are not part of this branch.

## Active slice

Implement offline conformance, secret scanning, CI, and release verification.

## Verification evidence

- 2026-08-11: isolated worktree created at `/Users/chengpeng/MyProject/Vidsnap-video-harness-core` on `codex/video-harness-core`.
- 2026-08-11: legacy baseline backend tests: 49 passed.
- 2026-08-11: package smoke test RED (`ModuleNotFoundError: vidsnap`), then GREEN: `2 passed`.
- 2026-08-11: editable package install, installed `vidsnap --help`, Ruff format/check for package files, and sdist/wheel build succeeded.
- 2026-08-11: the source tree is deliberately tracked; only local virtualenv/cache/run output paths were added to `.gitignore`.
- 2026-08-11: contract tests RED on missing `vidsnap.contracts`, then GREEN: strict Pydantic models, an immutable `vidsnap.loop/v1` LoopSpec, and stable SHA-256 digest `e3332f1c43b5800fe296c9082391e1c7988b9675d54a862c6d44a01e2f4a608f`.
- 2026-08-11: a real wheel-build test caught a missing Schema asset; Hatch `force-include` now ships `video_analysis.v1.json`. Package/contract/distribution tests: 7 passed.
- 2026-08-11: RunBundle tests RED on missing loop modules, then GREEN: atomic manifest/result writes, redacted JSONL events, evidence/result file hashes, valid terminal-state finalization, and automatic temporary-directory cleanup (3 passed).
- 2026-08-11: Pydantic 2.10 rejects a handwritten recursive JSON union while generating a Schema. The event ledger uses Pydantic's native `JsonValue`, confirmed by a minimal reproduction before the focused fix.
- 2026-08-11: controller/verifier tests RED on missing modules, then GREEN: strict `probe → plan → gather → understand → synthesize → verify → repair → gather` transitions; all four hard budgets end in `EXHAUSTED`; missing/out-of-bounds evidence, empty claims, and empty required sections cannot pass verification (10 loop tests).
- 2026-08-11: canonical review against the approved contract renamed verifier gates to `claims_are_supported` / `required_sections_covered`, put verification gates in canonical order, and removed unapproved `CANCELLED` from LoopSpec terminal states (16 tests).
- 2026-08-11: media tests RED on missing `vidsnap.video`, then GREEN: local `ffprobe`, scene timestamp parsing, 8×8 grayscale motion/visual-difference scores, perceptual-hash de-duplication, coverage points, ASR/OCR-anchor merging, and 4 fps local-only high-motion resampling. FFmpeg synthetic two-scene probe/extract benchmark: 5 tests.
- 2026-08-11: provider/prompt tests RED on missing modules, then GREEN: only `VIDSNAP_QWEN_API_KEY → QWEN_API_KEY` is read; `qwen3.8-max`, Token Plan URL, and concurrency cap two are fixed; missing key blocks calls; Qwen receives typed JSON evidence only. `qwen3-asr-flash` uses in-memory Base64 data URIs and falls back only to an explicit local plugin. Five prompt layers have metadata and golden rendering tests. Provider/prompt/package-asset tests: 14 passed; wheel build passed.
- 2026-08-11: harness tests RED on missing `vidsnap.harness`/skills, then GREEN: the registry admits exactly the six LoopSpec skills; extracted local JPEG evidence is sent to Qwen as a bounded data URI; every run emits a RunBundle. Success requires verifier support; missing local key is `BLOCKED`, empty or unsupported output is `PARTIAL`, provider error is `FAILED`, and zero model-call budget is `EXHAUSTED` (20 relevant tests).
- 2026-08-11: CLI/API tests RED on missing adapter modules, then GREEN: CLI exposes analyze/serve/benchmark/conformance/manifest; FastAPI serves only health, manifest, analyze, and stream endpoints. HTTP requests reject request-body keys, models, prompts, and provider URLs through strict schemas, create a temporary RunBundle, and remove it after completion. CLI/API tests: 3 passed.
- 2026-08-11: benchmark tests RED on missing modules, then GREEN: Direct creates full-video requests with explicit fps=2; Direct+ASR and Harness-Full retain identity of the caller-supplied transcript object. Local-only profiles and deterministic temporal/grounding metrics: 3 tests passed. Live comparison remains BLOCKED_LIVE_BENCHMARK.
- 2026-08-11: SaaS boundary test RED while frontend/backend existed, then GREEN after Git-aware removal of frontend, backend, Compose, old startup/deploy/analytics scripts, old environment templates, and product docs/screenshots. The last untracked backend cache/log residue was moved recoverably to the system Trash. No legacy runtime dependency remains outside migration/design documentation.

## Next step

Write conformance/secret-scan tests, observe missing release tooling RED state, then make CI enforce the offline quality gate.
