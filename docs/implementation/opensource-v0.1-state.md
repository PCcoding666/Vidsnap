# Open Source v0.1 — Program State

This page records the phase state of the open-source v0.1 program on branch
`codex/opensource-v0.1`. It records observed facts only. Phase status values
are restricted to `NOT_STARTED`, `IN_PROGRESS`, `BLOCKED`, `VERIFIED`.

No live benchmark has been run and no provider call has been made for this
program. This page claims no Harness performance conclusion of any kind.

## Isolation

- Baseline commit: `31a7d365b019280ed7d3a8b7f75ce44b22b83ca5` (merge of PR #16).
- Worktree: `/Users/chengpeng/MyProject/Vidsnap-opensource-v0.1`, branch
  `codex/opensource-v0.1`; working tree clean at baseline.
- The original worktree `/Users/chengpeng/MyProject/Vidsnap` (holding the
  user's uncommitted changes) has not been touched. No push, merge, or
  force-push has been performed from this worktree.

## Phase 0 — Repository Reality Check

### Goal

Record the truthful baseline before any open-source repositioning:
architecture, CLI, tests, build, conformance, secret scan, Core/Plugin/Recipe
boundaries, new-user obstacles, and environment findings. Changes in this
phase are record-only.

### Changes

- Added this file only. No production code, test, CI, README, or project
  metadata was modified.

### Current architecture (observed)

Python src-package `src/vidsnap` (~60 modules), strict typing, Python >= 3.10,
runtime deps httpx/pydantic/typer, optional fastapi/uvicorn (server extra).

- Core: `runtime/kernel.py` (`HarnessKernel`: bounded execution, enforced
  budgets, call fingerprints, payload redaction), `runtime/policies.py`
  (`FixedPolicy` default, `AgenticPolicy`, `DirectPolicy`), `loop/`
  (state machine, `RunBundle`, events, trace recorder, claim verifier),
  `contracts/` (strict models, LoopSpec `vidsnap.loop/v1`, output schema
  `vidsnap.video-analysis/v1`), `tasks/video_analysis.py` (verifier gates
  `claims_are_supported`, `required_sections_covered`).
- Plugins: `plugins/` with strict manifests (`vidsnap.plugin/v1`; kinds
  tool/policy/task/observer), an allow-list registry frozen before runs and
  never mutated by runs, and entry-point discovery restricted to explicitly
  allow-listed IDs. Built-in model-visible tools: `transcribe_audio`,
  `sample_evidence`. There is no external plugin SDK, no
  `vidsnap plugin validate/test`, and no template.
- Providers: typed ports (`VideoModelPort`, `ToolPlanningPort`,
  `AgentModelPort`); the only concrete client is Qwen-compatible with model
  fixed to `qwen3.8-max`, concurrency capped at 2, key read only from
  `VIDSNAP_QWEN_API_KEY` / `QWEN_API_KEY`.
- Trace: `trace/` offline HTML export (`vidsnap trace export`); template
  assets ship in the wheel.
- API: `api/app.py` stateless localhost FastAPI (`/health`, `/v1/manifest`,
  `/v1/analyze`, `/v1/analyze/stream`); temporary RunBundle deleted after
  the request.
- Benchmark: `benchmark/` modules, `scripts/`, and `benchmarks/` profiles
  (documentation only). CLI `benchmark run/compare` honestly report
  `BLOCKED_LIVE_BENCHMARK` when no key is configured.

### Current CLI (observed)

`vidsnap analyze | manifest | serve | conformance | benchmark run |
benchmark compare | trace export`. `--help` and `conformance` pass locally
(conformance report `passed=true`, all twelve checks green).

### Tests / build / install / gates (observed)

- 333 offline tests collected; 333 pass when the import path resolves to
  this worktree (see environment pollution below).
- `ruff format --check` (124 files) and `ruff check .`: pass (ruff 0.11.0).
- `mypy src` strict: 60 source files. One error under the old shared
  environment's mypy 1.10.0 + pydantic 2.10.0 (see environment section);
  clean venv gate: PASS, 60 source files.
- The committed wheel ships the output schema, all five prompt JSON assets,
  and `trace/assets/trace.html` + `timeline.js`, and registers the
  `vidsnap` console script.
- `python scripts/secret_scan.py`: pass. `git diff --check`: clean. No
  tracked media or binary assets (166 tracked files total).
- CI (`.github/workflows/ci.yml`) already gates: ruff, mypy, pytest, build,
  wheel smoke (`vidsnap --help`, `vidsnap conformance` in a fresh venv),
  secret scan, and `git diff --check`.
- No `examples/` directory exists.

### Core / Plugin / Recipe boundaries (real, today)

- Core exists and is genuinely bounded (kernel, budgets, verifier gates,
  RunBundle, replayable trace).
- Plugins exist only as an internal mechanism (two builtin tool plugins plus
  the registry/manifest machinery). Extension by external developers is
  source-reading only.
- Recipes do not exist as a layer: no recipe concept, registry, CLI surface,
  or documentation. The only task is the built-in video-analysis adapter.

### Obstacles for a new GitHub user (observed)

- Understand: the README leads with internal guarantees and benchmark
  framing; a stranger cannot tell in 30 seconds what VidSnap is or how it
  differs from a video summarizer.
- Try: there is no zero-key path. Any run requires a local Qwen key; no
  offline demo, no shipped replay fixture, no `vidsnap demo`.
- Extend: no recipe layer, no plugin developer documentation, no template,
  no examples directory.
- Community surface gaps: no `CODE_OF_CONDUCT.md`, `ROADMAP.md`,
  `MAINTAINERS.md`, or `examples/`. `CONTRIBUTING.md`, `AGENTS.md`,
  `SECURITY.md`, and the Task Contract templates exist and are consistent
  with `PROJECT_STATE.md`.

### Environment pollution and dependency drift (observed; not code defects)

The shell's active Python is the old shared conda env
`miniconda3/envs/yt_summarizer` (Python 3.10.16, pytest 8.3.5), in which
`import vidsnap` resolves to
`/Users/chengpeng/MyProject/Vidsnap-youtube-publishing-pilot/src/vidsnap` —
not this worktree. Verified consequences:

- Full suite in that env: 1 failed / 332 passed (earlier baseline run).
  The failing test is `test_manifest_preparer_rejects_repository_root`:
  `src/vidsnap/benchmark/manifest.py:31` derives `REPOSITORY_ROOT` from the
  imported package location (`Path(__file__).resolve().parents[3]`), so with
  the wrong `vidsnap` imported the assertion compares different roots.
  With `PYTHONPATH=src` in this worktree the focused test passes and the
  full suite is 333 passed. Root cause: environment import-path pollution.
- mypy 1.10.0 + pydantic 2.10.0: exactly 1 error in 60 files —
  `src/vidsnap/trace/reader.py:25`,
  `_USAGE_FIELDS = frozenset(EventUsage.model_fields)`
  (`call-overload` on `model_fields`). Clean venv (mypy 1.20.2 +
  pydantic 2.13.4): 60 source files, no issues. Dependency drift; no code
  was changed for it.
- Conformance vacuous-scan risk: `conformance.py`
  `_check_forbidden_dependencies` walks `Path(__file__).resolve().parents[2] / "src"`.
  In a wheel-installed context that directory does not exist, the scan
  finds no files, and the check passes vacuously. Recorded as a risk;
  deliberately not fixed in Phase 0.
- No SaaS runtime remains in `src/` (offline tests
  `test_no_saas_dependencies.py` / `test_repository_governance.py` guard
  this), but `.gitignore` still carries legacy SaaS-era entries
  (`backend/`, `frontend/`, `node_modules`, `hf_space`,
  `backend/youtube_cookies.txt`, `storage/`, `run/`,
  `benchmark-results/`). Documentation-only residue.

### Observed problems

1. Baseline verification environment is polluted (wrong `vidsnap` import
   path), producing one false test failure.
2. Toolchain drift: the declared version ranges admit a
   mypy/pydantic combination that fails `mypy src` (1 error).
3. Conformance forbidden-dependency scan can be vacuous in wheel installs.
4. No zero-key demo, no recipe layer, no plugin developer surface.
5. Community/community-surface files incomplete; `examples/` missing.
6. `.gitignore` contains SaaS-era residue.

### Repairs

None in Phase 0. This is a record-only phase; the environment findings must
not be "fixed" by code changes as part of the baseline.

### Verification evidence (this session, this worktree)

- `PYTHONPATH=src python -m pytest --collect-only -q` → 333 collected.
- `PYTHONPATH=src python -m pytest -q` → 333 passed.
- `PYTHONPATH=src python -m pytest tests/test_prepare_agentic_manifests_script.py -q`
  → 1 passed.
- `python -c "import vidsnap; print(vidsnap.__file__)"` (no PYTHONPATH) →
  resolves to `Vidsnap-youtube-publishing-pilot/src/vidsnap` (pollution
  reproduced).
- `python -m mypy src` → 1 error, `src/vidsnap/trace/reader.py:25` (old
  mypy 1.10.0 + pydantic 2.10.0).
- `python -m ruff format --check src tests scripts` → 124 files formatted;
  `python -m ruff check .` → all checks passed.
- `python scripts/secret_scan.py` → pass. `git diff --check` → clean.
- `PYTHONPATH=src vidsnap --help` → usage renders;
  `PYTHONPATH=src vidsnap conformance` → `passed=true`.

### Clean-environment full gate (verified)

The main agent reran the complete Phase 0 gate in a clean venv
(`/tmp/vidsnap-v01-check.mfVkWs/venv`). All gates PASS:

- `ruff format --check src tests scripts`: PASS, 124 files already formatted.
- `ruff check .`: PASS.
- `mypy src`: PASS, 60 source files.
- `python -m pytest -q`: PASS, 333 passed in 5.39s.
- `python -m build`: PASS, built `vidsnap_harness-0.1.0.tar.gz` and
  `vidsnap_harness-0.1.0-py3-none-any.whl`.
- `vidsnap conformance`: PASS, `passed=true`, all 12 checks green; default
  model-visible tools `sample_evidence` and `transcribe_audio`; fixed order
  `transcribe_audio` then `sample_evidence`.
- `python scripts/secret_scan.py`: PASS.
- `git diff --check`: PASS.
- Separate brand-new temporary wheel venv: installed the built wheel;
  `vidsnap --help` PASS; `vidsnap conformance` PASS (`passed=true`).

### Commit

`601a4b94 docs: record open source v0.1 baseline` — committed on branch
`codex/opensource-v0.1`. The clean-environment full gate had passed before
the commit.

### Remaining risks

- Environment pollution is environmental, not a code defect: gates rerun in
  the old shared environment can still produce one false test failure and a
  spurious mypy error. Re-run gates in a clean venv (as recorded above).
- The declared dependency ranges (`mypy>=1.10,<2`, `pydantic>=2.7,<3`)
  admit a version combination that fails `mypy src`.
- Conformance forbidden-dependency scan may be vacuous for wheel installs.
- Benchmark evidence is absent by design (no live runs); this is recorded
  honestly rather than filled with claims.

### Status

`VERIFIED`

## Phase 1 — GitHub Product Identity

### Goal

Reposition README/metadata so a stranger understands VidSnap in 30 seconds:
newcomer-first README, truthful documentation landing page, and exact project
identity metadata, driven by RED acceptance tests.

### Changes

Four identity surfaces changed plus this state record; no runtime behavior changed:

- `README.md`: rebuilt newcomer-first (# VidSnap hero, tagline, pipeline
  line, What VidSnap does, Quick Start, What is a trace, Why VidSnap exists,
  not another video summarizer, Core/Plugin/Recipe, evidence grounding,
  replayable trace, plugin/recipe boundaries, bounded safety, current
  guarantees, benchmark evidence, surfaces, contributing).
- `docs/README.md`: concise landing page with the wrapped tagline, correct
  `../README.md#...` anchors (quick-start, trace, plugin, recipe, benchmark,
  contributing), preserved detailed-doc links, and the nine discoverability
  topics.
- `pyproject.toml`: exact description `Auditable video-agent runtime with
  bounded tools, pluggable tasks, evidence-grounded outputs, and replayable
  traces.` plus the nine keywords (video-ai, agent-harness, multimodal,
  ai-agents, video-analysis, llm-evaluation, python, observability,
  agent-runtime).
- `tests/test_project_identity.py`: four acceptance tests (RED first),
  later reformatted to Ruff's single-line `keywords_match` form
  (formatting only; test behavior unchanged).
- `docs/implementation/opensource-v0.1-state.md`: records observed Phase 1
  evidence (TDD states, regression, repair, gates, stranger audit).

### TDD evidence (this session, this worktree)

- RED: `tests/test_project_identity.py` → 4 failed (acceptance unmet).
- GREEN after README/docs/pyproject implementation: 4 passed.
- Legacy documentation regression: 1 failed / 336 passed (documentation
  contract phrases missing from the rewritten pages).
- Repair: added compact `Current guarantees` blocks to README.md and
  docs/README.md preserving the six exact contiguous contract phrases.
- Focused identity + documentation run: 10 passed.

### Final full clean gate (verified)

- `ruff format --check`: PASS, 125 files already formatted.
- `ruff check .`: PASS.
- `mypy src`: PASS, 60 source files.
- `python -m pytest -q`: PASS, 337 passed.
- `python -m build`: PASS (sdist and wheel).
- `vidsnap conformance`: PASS, 12 checks green.
- `python scripts/secret_scan.py`: PASS.
- `git diff --check`: PASS.

### Stranger audit (Gate 1)

All six questions are answered in the first half of README.md: What VidSnap
does, Why VidSnap exists, not another video summarizer, Quick Start, What is
a trace, How to extend; the words Core, Plugin, Recipe appear in the first
half, with the real install (`python -m pip install -e '.[server,dev]'`),
`vidsnap --help` / `vidsnap conformance`, and the real
`vidsnap trace export RUN_DIR -o trace.html` command.

### Truthful boundaries recorded

- Core is public and working; Plugin is internal and allow-listed with only
  `transcribe_audio` and `sample_evidence` model-visible by default; external
  plugin DX comes later; Recipe does not exist yet and comes later.
- No zero-key demo is claimed (that is Phase 2). No performance,
  superiority, public plugin SDK, recipes, or live benchmark conclusion is
  claimed.

### Commit

`591e3012 docs: reposition VidSnap for open source developers` — committed on
branch `codex/opensource-v0.1`. The final full clean gate had passed before
the commit.

### Status

`VERIFIED`

## Phase 2 — Zero-Key Offline Demo

### Goal

Zero-key offline packaged synthetic replay: `vidsnap demo` replays a packaged
synthetic fixture run into a fresh output directory with no key, account,
network request, model call, GPU, or private media.

### Changes

- `vidsnap demo` CLI command (`--output-dir`, default `vidsnap-demo/`); it
  calls the replay, converts `FileExistsError`/`ValueError` to a safe stdout
  refusal with exit code 2, and on success prints the replay headings, exact
  counts, and resolved final artifact and trace paths.
- `src/vidsnap/demo/`: replay validator and report (`DemoReplayReport`,
  `replay_demo_run`) that validate provenance, manifest hashes, the RunEvent
  ledger, evidence and claim counts, and policy bounds before publishing
  `run/`, `trace.html`, and `demo-report.json`.
- Packaged fixture: CC0-1.0, media-free (no media, private data, or provider
  output), a real RunBundle with `manifest.json`, `events.jsonl`,
  `result.json`, and 11 strict evidence JSON items.
- Fixture run shape: 6 agent decisions, exactly two bounded tools
  (`transcribe_audio` and `sample_evidence`), 8 grounded claims.
- Package data: the demo fixture files force-included in both wheel and
  sdist.
- `.gitignore`: narrow ordered exceptions unignore only the publishable demo
  fixture JSON/JSONL source assets (provenance, run bundle, evidence), and a
  governance test prevents them from becoming ignored.
- README 30-second demo section.
- Tests: new `tests/test_demo.py`; distribution test switched to full-build
  verification.

### TDD evidence (this session, this worktree)

- Initial focused RED: 13 failed / 6 passed because the command, packaged
  assets, and docs were absent.
- Trace review found `agent.step` invisible and the manifest incomplete;
  repaired to `agent.decision` events plus 11 `evidence.added` events and
  real RunBundle fields.
- Focused GREEN: 19 passed.
- Initial full build then exposed the wheel-from-sdist missing fixture;
  changed the distribution test to full build (sdist then wheel-from-sdist),
  observed RED (`FileNotFoundError` for the forced include
  `src/vidsnap/demo/fixtures/provenance.json`), and added precise sdist
  force-includes for the 15 fixture files.
- Distribution GREEN: 5 passed; full build green (sdist and wheel).
- Pre-fix `git check-ignore` showed `provenance.json` ignored by `*.json`
  and the fixture run bundle ignored by `run/`.
- Focused governance RED was repaired with the narrow ordered exceptions in
  `.gitignore`; governance GREEN: 10 passed.
- All 15 fixture files are now visible as untracked source assets before
  commit.

### Clean wheel smoke (verified)

- Built the wheel, force-installed it outside the source context, and unset
  both key environment variables.
- `vidsnap demo` succeeded: report counts 6 steps, 11 evidence, 8/8 claims;
  usage 0 model calls, 2 tool calls, 12 frames; `trace.html` 34603 bytes;
  no media, private data, or provider output.

### Final full clean gate (verified)

- `ruff format --check`: PASS, 128 files already formatted.
- `ruff check .`: PASS.
- `mypy src`: PASS, 62 source files.
- `python -m pytest -q`: PASS, 351 passed.
- `python -m build`: PASS, sdist and wheel.
- `vidsnap conformance`: PASS, 12 checks green.
- `python scripts/secret_scan.py`: PASS.
- `git diff --check`: PASS.

### Remaining risks

- The demo is an explicit replay, not live generation: it proves
  distribution, DX, and trace integrity only — not model quality or harness
  superiority.
- The fixture is synthetic; no live benchmark or provider call occurred.

### Commit

`cb1d557b feat: add zero-key offline demo` — committed on branch
`codex/opensource-v0.1`. The final full clean gate had passed before the
commit.

### Status

`VERIFIED`

## Phase 3 — Trace Viewer

### Goal

Extend the offline trace export into a shareable, static, privacy-safe HTML
projection of run overview, budget, agent timeline, evidence, claims, and a
privacy panel across all terminal states, with a sanitized truth-only reader
boundary between raw RunBundle ledgers and the projected TraceDocument.

### Changes

- `src/vidsnap/trace/models.py`: frozen typed Pydantic projection models
  (`FrozenProjectionModel`, `TraceOverview`, `TraceBudgetCounter`,
  `TraceBudget`, `TraceEvidence`, `TraceClaim`) with safe defaults;
  `TraceDocument` extended with `overview`, `budget`, `evidence`, `claims`;
  budget counters are `int | None` so missing values stay missing.
- `src/vidsnap/trace/reader.py`:
  - Overview projected from recorded truth only: `goal`/`input_sha256` from
    the `run.started` item payload; `status` from the manifest terminal
    state; `duration_ms` from the recorded run span; provider marker exactly
    `configured (identity redacted)` when the manifest provider is
    configured, otherwise `not recorded`; `recipe` from `loop_spec.id`.
  - Budget projected from the latest `budget.updated` event (`model_calls`,
    `evidence_frames`, `iterations`) and manifest resources
    (`max_model_calls`, `max_evidence_frames`, `max_iterations`;
    `runtime_ms.limit = max_wall_seconds * 1000`, `runtime_ms.used` = run
    duration); missing values remain `None`.
  - Evidence projected from `*.json` directly under `run/evidence`, sorted,
    parsed strictly with `Evidence.model_validate_json`, 280-character
    content preview, artifact bytes never opened; claims projected from
    `result.json` via strict `VideoAnalysisResult.model_validate_json`;
    invalid/unreadable files are skipped with one truthful limitation;
    summary-only stays empty.
  - Recursive projection-boundary sanitizer applied before any raw event
    payload enters `TraceItem` or the budget/overview projection: sensitive
    keys and containers are dropped case-insensitively (authorization/auth
    headers, api/access/PAT/credential/secret/password/cookie keys, env and
    environment containers including arbitrary env vars,
    chain_of_thought/reasoning/internal_reasoning/scratchpad/thoughts,
    header containers) while legitimate usage keys such as
    `input_tokens`/`output_tokens` are preserved; remaining string values
    that expose provider URLs with credentials, secret-bearing query
    strings, or absolute local user paths (`/Users/...`, `/home/...`) are
    redacted. No sensitive marker or sensitive key name remains in the
    `TraceDocument` JSON.
- `src/vidsnap/trace/assets/trace.html`: accessible named sections with
  exact visible labels Run Overview, Budget, Agent Timeline, Evidence,
  Claims, Privacy and stable container IDs; renderers for
  overview/budget/evidence/claims wired into `renderVariant`;
  `textContent`-only data injection; missing values shown as 未记录;
  truthful empty states; minimal responsive CSS; the page remains fully
  offline and self-contained (no external resources, network, backend,
  login, or telemetry).
- Tests (all trace test files changed in this phase):
  - `tests/trace/test_phase3_projection.py` — new: projection coverage for
    overview/budget/evidence/claims plus the adversarial raw-ledger
    sentinel boundary test.
  - `tests/trace/conftest.py` — shared trace-suite fixtures updated for the
    Phase 3 trace document shape.
  - `tests/trace/test_export.py` — offline export expectations updated to
    the Phase 3 document/section shape.
  - `tests/trace/test_reader.py` — legacy payload expectation repaired to
    the authoritative Phase 3 contract (see conflict below).
  No production behavior beyond the above.

### TDD evidence

- RED (privacy boundary): the new adversarial test built a finalized bundle,
  appended a sensitive-laden event line directly to `events.jsonl`
  (bypassing write-time redaction), and verified the raw ledger still held
  every sentinel. `read_trace` then projected the raw `model.request`
  payload verbatim: the test failed with
  `AssertionError: trace document leaked sensitive marker 'sentinel-bearer-auth-9d2f1c'`.
- GREEN after the sanitizer: the focused trace suite passed.
- Earlier phase-3 slices (overview, budget, evidence, claims, HTML sections
  and renderers) were implemented slice-by-slice with focused runs after
  each edit.

### Observed old-test conflict and repair

- After the sanitizer, `tests/trace/test_reader.py::test_payload_and_usage_stay_typed_and_redacted`
  failed (1 failed / 33 passed): the legacy expectation required
  `api_key: "***REDACTED***"` to remain inside the projected
  `tool.call.started` payload, while the new Phase 3 contract requires
  sensitive key names to be absent even when their values were already
  write-time redacted.
- Resolution: the Phase 3 privacy contract was treated as authoritative.
  The legacy expectation was repaired to require omission of `api_key`
  (payload equals `{"name": "sample_evidence"}`) with an added explicit
  `assert "api_key" not in serialized` while preserving the benign payload
  field and the usage-counter assertions. The sanitizer was not weakened
  and the new adversarial test was not modified. Result: all trace tests
  green.

### Verification evidence (recorded independent results)

- Trace tests: `PYTHONPATH=src python -m pytest -q tests/trace` → 34 passed.
- Full suite: 359 passed.
- `ruff format --check`: PASS, 129 files already formatted.
- `ruff check .`: PASS.
- `mypy src`: PASS, 62 source files.
- `python -m build`: PASS (sdist and wheel).
- `vidsnap conformance`: PASS, 12 checks green.
- `python scripts/secret_scan.py`: PASS.
- `git diff --check`: PASS (clean).
- Zero-key demo replay plus re-export produced two byte-identical
  45,629-byte `trace.html` files.
- All five terminal-state exports (SUCCEEDED, PARTIAL, FAILED, EXHAUSTED,
  BLOCKED) passed the offline export tests: terminal state present; no
  scheme URLs, no `fetch(`/`WebSocket`, no secret host or query values.
- Application in-app browser refused direct `file://` navigation by its
  security policy, so visual browser inspection could not be performed and
  was not bypassed; recorded as an explicit limitation below.

### Remaining risks

- Visual-browser inspection of the exported HTML remains an explicit
  limitation: the in-app browser refused `file://` navigation by security
  policy, so rendering was validated by tests only, not by a human in a
  browser.
- The sanitizer is a targeted key/value boundary, not a general PII
  anonymizer: it removes the enumerated sensitive key families and redacts
  credentialed/secret-query URLs and absolute local user paths; other
  benign-looking strings are not scanned for secrets.
- Conformance forbidden-dependency scan vacuity and the dependency-drift
  risks recorded in Phase 0 remain.
- No live benchmark was run; the demo is an explicit synthetic replay, so
  no model-quality or performance conclusion is claimed.

### Commit

`325f3cc8 feat: add portable trace viewer` — committed on branch
`codex/opensource-v0.1`.

### Status

`VERIFIED`

## Phase 4 — Source-Preserving Interview Recipe

### Goal

Add the first real Recipe-layer workflow: `vidsnap recipe interview VIDEO --output-dir OUT`, producing exactly `transcript.zh.md`, `interview.article.md`, `brief.md`, and `trace.html`.

### Changes and boundaries

Input is a local video only; the model configuration is fixed to qwen3.8-max;
only `transcribe_audio` and `sample_evidence` are model-selectable; the CLI
exposes no model, prompt, URL, budget, or tool options; the kernel owns probe,
result, and verifier; the existing Fixed Harness remains unchanged. Editorial
provenance records speaker, times, transcript evidence, optional frame
evidence, and the statuses `source`, `faithful_translation`,
`edited_for_clarity`, `model_commentary`, `unknown`, `unverified`, `partial`.
Source material and model commentary remain visibly separate. Artifacts are
created only for verified SUCCEEDED; BLOCKED, PARTIAL, and FAILED create none,
and the CLI never prints `failure_reason`; a SUCCEEDED run without artifacts
also exits 1. Hardening recorded: the trace reader rejects malformed recipe
provenance all-or-none (no partial claims); `edited_for_clarity` is a
Unicode-aware removal-only edit check that rejects punctuation-only rendered
text and invented words in any script while accepting removal-only CJK and
Arabic; the renderer stages all four artifacts in a private staging directory
and publishes them with one atomic rename, removing only the staging directory
on late write failure; the CLI treats SUCCEEDED without artifacts as a failure
(exit 1). Duplicate-ID hardening recorded: recipe models reject duplicate
segment ids, duplicate block ids across source/commentary blocks, and
duplicate brief-point ids; the portable trace projection enforces the same
all-or-none. The trace reader projects valid recipe results generically and
emits no partial claims for malformed results.

### Deterministic verification

The gates are exactly `dialogue_present`, `dialogue_retained`,
`timestamps_in_bounds`, `referenced_evidence_exists`, `source_text_supported`,
`provenance_complete`. Speaker labels and transcript-evidence time spans are
checked.

### TDD and verification evidence

Trace-projection hardening was RED with 3 failures then GREEN 9 passed; the
renderer late-write atomicity test was RED with 1 failure then GREEN 8 passed;
the CLI missing-artifacts test was RED with 1 failure then GREEN 9 passed; the
editorial Unicode hardening was RED with 2 failures then GREEN (focused
models+renderer 54 passed); duplicate-ID hardening was RED with 3 model
failures then GREEN 49 model tests, and RED with 2 trace failures then GREEN
combined 60 focused tests. Final gate: Ruff 139 files; mypy 67 source files;
pytest 455 passed; build PASS; conformance all 12 checks green with unchanged
tools/order; secret scan and diff check passed. Clean-wheel: the wheel was
imported from its venv site-packages, recipe help PASS, and 8 renderer tests
passed.

### Truthful limits

No live provider/model call was made and no benchmark or quality/performance
claim is recorded. Validation is synthetic/offline; preservation is bounded by
captured ASR/evidence; speaker verification requires explicit labels in
transcript evidence; live provider/media behavior remains unproven.

### Commit

`feat: add source-preserving interview recipe` — pending until the main agent
commits on `codex/opensource-v0.1`.

### Status

`VERIFIED`

## Later phases

The entries below are the remaining Phase 5–9 goals; each is `NOT_STARTED`.
Status values are restricted to `NOT_STARTED` / `IN_PROGRESS` / `BLOCKED` /
`VERIFIED`. Completed Phase 4 is recorded above.

- Phase 5 — Plugin Developer Experience: plugin contract docs,
  `vidsnap plugin validate/test`, example template. `NOT_STARTED`
- Phase 6 — Provider Decoupling: stable provider protocol, reference and
  mock providers, contract test suite; no in-run provider switching.
  `NOT_STARTED`
- Phase 7 — Community Surface: CONTRIBUTING/AGENTS/MAINTAINERS/
  CODE_OF_CONDUCT/ROADMAP/SECURITY completion and good first issues.
  `NOT_STARTED`
- Phase 8 — Benchmark as Trust Layer: honest, reproducible methodology;
  no marketing numbers. `NOT_STARTED`
- Phase 9 — v0.1 Release Readiness: clean-environment build/install/smoke
  checklist and release verification. `NOT_STARTED`
