# Video Harness Implementation Loop State

## Current state

- Decision: execute the approved clean Harness Core migration on `codex/video-harness-core` in an isolated worktree.
- Decision: no credential from chat will be used; only local environment variables are eligible for a future live benchmark.
- Baseline: `cd backend && python -m pytest -q` passed, 49 tests; one `pytest-asyncio` deprecation warning from the legacy stack.
- Existing user modifications remain only in the original worktree and are not part of this branch.

## Active slice

Create the bounded Qwen/ASR provider ports, versioned prompt assets, and offline missing-key behavior with TDD tests.

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

## Next step

Write configuration/provider/prompt tests, observe missing-module RED states, then implement the fixed-model compatible client without making a network request.
