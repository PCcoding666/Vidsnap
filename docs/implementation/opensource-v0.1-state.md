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

`bf635179 feat: add source-preserving interview recipe` — committed on branch
`codex/opensource-v0.1`.

### Status

`VERIFIED`

## Phase 5 — Plugin Developer Experience

### Goal

A developer installs and verifies their first VidSnap tool plugin in 30
minutes: a statically validated `vidsnap.plugin-project/v1` project contract,
`vidsnap plugin validate/test` CLI commands, and a complete example template.

### Changes

- Static project contract `vidsnap.plugin-project/v1`
  (`src/vidsnap/plugins/project.py`): a strict, closed manifest covering id,
  name, version, capabilities (provides/requires), `input_schema`,
  `output_schema` (fixed `vidsnap://schemas/tool-result/v1` reference),
  `permissions`, `budget_impact`, and the entry point; validation reads
  `vidsnap.plugin.json` and the real
  `[project.entry-points."vidsnap.plugins"]` TOML from `pyproject.toml` and
  never imports or executes plugin code.
- CLI (`src/vidsnap/cli.py`): `vidsnap plugin validate .` checks the static
  contract only; `vidsnap plugin test .` performs the same static validation,
  then resolves the exactly-one allow-listed plugin through entry-point
  discovery: it imports the entry-point module, calls the zero-argument
  factory, and checks the returned object satisfies the `ToolPlugin`
  protocol, the manifest/contract match, and semantic input-schema equality.
  It never calls `ToolPlugin.execute`.
- `examples/plugin-template/`: a complete deterministic, zero-model-call
  `video_metadata` tool plugin that reads only the harness-computed
  `MediaProbe` and returns seven metadata fields; ships `pyproject.toml`,
  `vidsnap.plugin.json`, the plugin package, an offline pytest, and an
  example run (`probe.json`, `expected_result.json`) whose structured
  content must exactly equal `result.model_dump(mode="json")`. The README
  documents the 30-minute flow and the trust model.
- Trust model recorded: installed plugin Python is trusted code, not a
  sandbox, and runs with host-process permissions; the Agent still invokes
  tools only through a typed, bounded `ToolExecutionContext`, and the static
  `permissions`/`budget_impact` declarations cannot dynamically expand
  harness policy or budget.

### TDD evidence

- Contract, CLI, and template behaviors were driven RED→GREEN; an
  independent review pass hardened `additionalProperties: false`
  enforcement, `required` completeness checks, real TOML parsing, and the
  semantic schema comparison (title/description-stripped, sorted
  `required` lists).
- The external Gate first failed on an equivalence gap: a contract schema
  `{type: object, properties: {}, required: [], additionalProperties: false}`
  versus Pydantic's semantically identical empty `StrictModel` schema that
  omits `required` was misreported as ERROR. A new unit test was RED
  (1 failed); a minimal normalization in `_normalize_json_schema` made a
  missing `required` list equivalent to an empty one on object schemas only
  (non-empty `required` and all other fields still compared exactly), then
  GREEN (1 passed). Final focused plugin tests: 65 passed.
- The release checklist Gate found the global `*.json` ignore rule hiding the
  three public template JSONs (`vidsnap.plugin.json`, `example_run/probe.json`,
  `expected_result.json`); a new release regression test was RED (1 failed),
  three exact `.gitignore` unignores were added with no other JSON rule
  relaxed, then GREEN (1 passed).

### Verification evidence (final full gate)

- `ruff format --check`: PASS, 147 files already formatted; `ruff check .`: PASS.
- `mypy src`: PASS, 68 source files.
- `python -m pytest -q`: PASS, 520 passed.
- Template offline pytest: 1 passed.
- `python -m build`: PASS (sdist and wheel).
- `vidsnap conformance`: PASS, all 12 checks green; default model-visible
  tools and their order unchanged.
- `python scripts/secret_scan.py`: PASS; `git diff --check`: PASS.
- Out-of-repository Gate `/tmp/vidsnap-plugin-gate.8hQS3x`: fresh venv with
  the core wheel plus the copied template plugin installed; `vidsnap plugin
  validate .`, `vidsnap plugin test .`, discovery of the installed plugin,
  and the fixture invoke matching `expected_result.json` — all PASS.
- No live model/provider call was made and no benchmark was run.

### Commit

`29f7df0c feat: add plugin developer kit` — committed on branch
`codex/opensource-v0.1`.

### Status

`VERIFIED`

## Phase 6 — Provider Decoupling

### Goal

Decouple the model provider behind stable typed ports: a stable
runtime-checkable provider protocol with an immutable identity, a reference
Qwen provider, a deterministic mock provider, allow-listed provider-plugin
discovery, and application-selected provider injection into the Harness and
recipes, with no in-run provider switching.

### Changes

- Stable runtime-checkable `ProviderProtocol` and immutable
  `ProviderIdentity`.
- The application-selected provider is fixed for a run; no in-run switching.
- Agent schemas carry no provider, model, or base_url fields.
- `QwenProvider` reference provider, deterministic `MockProvider`, explicit
  allow-listed `vidsnap.providers` entry-point discovery, and an async shared
  provider contract checker.
- `VideoHarness` and `InterviewRecipeRunner` accept provider injection;
  conflicting configuration is rejected, and provider mode performs no
  implicit Qwen ASR (an explicit recognizer is required).
- Legacy/default Fixed Harness behavior and the default tool order are
  unchanged.
- The RunBundle records the provider-injected identity redacted.
- `BenchmarkProfile` remains locked to `qwen3.8-max`.

### TDD evidence

- Initial collection was RED because the provider modules did not exist yet.
- Discovery was RED with 3 failures caused by a direct `entry_points` import
  (repaired, see below).
- The documentation contract was RED with 10 failures (repaired, see below).
- Final focused runs: provider tests 59 passed, focused Harness regression
  19 passed, Interview runner 4 passed.

### Observed problems and repairs

- Discovery failed 3 tests because of a direct `entry_points` import; it was
  repaired to the runtime `importlib.metadata.entry_points` call.
- mypy found one redundant cast; it was repaired.
- The documentation contract had 10 failures; provider documentation and
  links were added to satisfy it.

### Independent post-implementation review (TDD)

- Four RED failures exposed non-callable or required-argument entry-point
  factories leaking `TypeError`, and over-broad third-party credential
  documentation.
- After the factory repair, one remaining RED documentation assertion
  exposed a contradictory universal sentence.
- Repairs: provider discovery wraps those factory violations as `ValueError`
  naming the entry point, and denied entries are never loaded; the
  credential-free RunBundle guarantee is scoped to built-in providers, while
  custom identity authors must exclude credentials.

### Verification evidence (final full gate)

- `ruff format --check`: PASS, 151 files already formatted.
- `ruff check .`: PASS.
- `mypy src`: PASS, 71 source files.
- `python -m pytest -q`: PASS, 548 passed in 10.48s.
- `python -m build`: PASS.
- `vidsnap conformance`: PASS, all 12 checks green; default tools and their
  order unchanged.
- `python scripts/secret_scan.py`: PASS; `git diff --check`: PASS.
- Clean wheel (repeated after the review fix): a fresh venv installed the
  wheel from its site-packages; MockProvider contract, `vidsnap --help`,
  and `vidsnap conformance` all PASS.

### Remaining risks

- No live provider or model call was made; no benchmark, quality, or
  performance claim is recorded.
- Provider plugins are trusted, unsandboxed code.
- Provider injection does not supply ASR and requires an explicit recognizer.
- `BenchmarkProfile` stays locked to `qwen3.8-max`.

### Commit

`031d8da6 feat: decouple model providers` — committed on branch
`codex/opensource-v0.1`.

### Status

`VERIFIED`

## Phase 7 — Community Surface

### Goal

Turn the repository into a credible open-source contribution target without
touching runtime behavior: a newcomer README/docs surface, complete community
governance files, GitHub issue forms and a pull-request template, scoped good
first issues, and offline community acceptance tests.

### Changes

- `README.md`: newcomer surface completed — the extension heading names the
  real boundaries (`## How to extend: Core, Plugin, Recipe`), a
  `Current guarantees` section carries the six contract statements one per
  line, a `Benchmark evidence` section states that the infrastructure exists
  but no live benchmark result is published, and the final section is renamed
  `Contributing`.
- `docs/README.md`: landing page links the README anchors (quick-start,
  trace, plugin, recipe, benchmark, contributing), carries one Topics line
  with the nine discoverability keywords, and adds a `Current behavior`
  section with the same six statements; tagline and existing links preserved.
- `CONTRIBUTING.md`, `AGENTS.md`, and `SECURITY.md` updated; `MAINTAINERS.md`,
  `CODE_OF_CONDUCT.md`, and `ROADMAP.md` added (Now / Next / Later with
  explicit non-goals).
- `.github`: the generic task issue template was replaced by issue forms
  (`bug.yml`, `documentation.yml`, `plugin-proposal.yml`,
  `provider-compatibility.yml`, `recipe-proposal.yml`);
  `PULL_REQUEST_TEMPLATE.md` updated.
- `docs/good-first-issues.md`: scoped starter tasks with acceptance criteria.
- `tests/test_community_surface.py`: new offline acceptance tests covering
  the community surface.
- `tests/test_repository_governance.py`: governance coverage extended for the
  community surface files.
- `examples/plugin-template/`: `pyproject.toml` gained a `test` extra
  (`pytest`, `pytest-asyncio`) and the template README install step became
  `python -m pip install -e '.[test]'` before the offline pytest command.
- No runtime code, contracts, recipe or RunBundle formats, or CLI behavior
  changed.

### TDD evidence

- Initial community-surface RED: 16 failed / 11 passed (acceptance unmet);
  GREEN after implementing the surfaces: 27 passed.
- Later focused docs RED: 3 failed; GREEN: 28 passed.
- Clean stranger audit first attempt: `vidsnap plugin validate` and the
  installed `vidsnap plugin test` passed, but the offline template pytest
  failed only because `pytest-asyncio` was not installed (`async def
  functions are not natively supported`, unknown `pytest.mark.asyncio`).
- Protection test RED: 1 failed / 7 passed (template `test` extra and
  `.[test]` install step absent); GREEN: 8 passed after the template fix.

### Clean stranger audit (verified, `/tmp/vidsnap-stranger.q4rd70`)

Fresh venv with the built wheel installed:

- `vidsnap --help` PASS; `vidsnap conformance` PASS; `vidsnap demo` PASS.
- Plugin template copied and renamed, then installed with `-e '.[test]'`.
- `vidsnap plugin validate .` → VALID; `vidsnap plugin test .` → PASS;
  offline pytest → 1 passed.

### Final full clean gate (verified)

- `ruff format --check`: PASS, 152 files already formatted.
- `ruff check .`: PASS.
- `mypy src`: PASS, 71 source files.
- `python -m pytest -q`: PASS, 566 passed.
- `python -m build`: PASS (sdist and wheel).
- `vidsnap conformance`: PASS, all 12 checks green.
- `python scripts/secret_scan.py`: PASS.
- `git diff --check`: PASS.

### Truthful boundaries

- No live provider or model call was made and no benchmark result was
  produced. Infrastructure validation is not evidence that Harness beats
  Direct; no performance or superiority claim is recorded.
- Community and governance files record intent and process; they add no
  runtime capability and are enforced only by offline tests.
- Plugins and providers remain trusted, unsandboxed code; the demo remains an
  explicit synthetic replay.

### Commit

`1e870a12 docs: add community contribution surface` — committed on branch
`codex/opensource-v0.1`.

### Status

`VERIFIED`

## Phase 8 — Benchmark as Trust Layer

### Goal

Benchmark as Trust Layer: honest, reproducible, explainable evaluation of the
Harness against the Direct baseline with no marketing numbers.

### Changes

- `src/vidsnap/benchmark/trust.py`: typed sealed registration and evaluation
  — `RegisteredCase`, `RepetitionObservation`, `TrustMeasurement`,
  `TrustOutcome`, `TrustManifest` (content-sealed `manifest_sha256`),
  `TrustMetricValue`, `TrustVariantMetrics`, `TrustReport`, and
  `TrustEvaluationInput`.
- Exact nine deterministic metrics: temporal grounding (interval IoU mean),
  citation precision, unsupported claim rate, evidence coverage, tool budget
  compliance (all three caps), provider regression, latency (median/total/
  count), cost (median/total/count), replay determinism. Missing
  observations are unknown, never zero.
- Fair Direct-vs-Harness gates: the nine fairness fields must match the
  registered case exactly, coverage must be exactly one outcome for every
  registered case×variant (duplicates, missing, and extra rejected), used
  evidence must be a subset of declared evidence, and a stale seal is
  rejected by recomputation.
- Deterministic reports: normalized outcome order, sorted-key compact UTF-8
  canonical JSON, stable `report_sha256` computed over the report content
  excluding the hash itself.
- CLI: offline `vidsnap benchmark evaluate INPUT_JSON --output REPORT_JSON`
  with a strict `manifest`/`outcomes` envelope; output is written only after
  parsing, validation, and evaluation succeed; failures print one generic
  redacted error and exit 2; success stdout prints only status and the
  resolved output path.
- Documentation: `docs/benchmark-methodology.md` added; `docs/
  benchmark-status.md`, `docs/README.md`, and the README `Benchmark evidence`
  section link it and carry the exact no-evidence sentence; `benchmark
  run/compare` truth unchanged.
- Tests: `tests/benchmark/test_trust_fairness.py`,
  `test_trust_metrics.py`, `test_trust_cli.py`,
  `test_trust_methodology_docs.py`.
- One type-check-only `tomli` fallback annotation
  (`src/vidsnap/plugins/project.py`) required by the clean Python 3.12
  environment running mypy configured for Python 3.10 where `tomli` is not
  installed; runtime selection unchanged and Python 3.10 support preserved.

### TDD evidence

- CLI RED: 4 failed / 2 passed before the command existed; GREEN: 6 passed.
- Documentation RED (corrected suite): 8 failed before the docs; GREEN:
  8 passed. The initial documentation test had a repository-root derivation
  mistake (`parents[1]` resolving under `tests/`); review rejected it and it
  was corrected to `parents[2]` before the RED state was accepted.
- Final focused trust suite: 41 passed.

### Review findings

- No socket, provider, key, or network dependency in evaluation.
- CLI errors are generic and redacted (exception class name only).
- `evaluate` validates everything before writing any output file.
- Missing, extra, and duplicate outcomes are all rejected.
- Stale manifest seals and undeclared evidence are rejected.

### Final clean gate (verified, `/tmp/vidsnap-phase8-gate.45LfY3/venv`)

- `ruff format --check`: PASS, 157 files already formatted.
- `ruff check .`: PASS.
- `mypy src`: PASS, 72 source files.
- `python -m pytest -q`: PASS, 607 passed (one existing
  `importlib.abc.Traversable` deprecation warning).
- `python -m build`: PASS (sdist and wheel).
- `vidsnap conformance`: PASS, all 12 checks green.
- `python scripts/secret_scan.py`: PASS.
- `git diff --check`: PASS.

### Truthful boundaries

- Exact no-evidence sentence: benchmark infrastructure ready; current
  results are not statistically meaningful.
- No live provider or model call was made and no benchmark sample result
  occurred; no quality, superiority, latency, or cost claim is recorded.

### Commit

`feat: add reproducible video-agent eval suite` — pending until the main
agent commits on `codex/opensource-v0.1`.

### Status

`VERIFIED`

## Later phases

The entries below are the remaining Phase 9 goals; it is `NOT_STARTED`.
Status values are restricted to `NOT_STARTED` / `IN_PROGRESS` / `BLOCKED` /
`VERIFIED`. Completed Phases 0–8 are recorded above.

- Phase 9 — v0.1 Release Readiness: clean-environment build/install/smoke
  checklist and release verification. `NOT_STARTED`
