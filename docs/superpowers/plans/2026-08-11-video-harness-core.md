# Video Harness Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace VidSnap's SaaS application with an installable, local-first video-analysis harness that exposes a Python SDK, CLI, stateless local API, bounded evidence loop, and fair Direct-vs-Harness benchmark.

**Architecture:** Build a new `src/vidsnap` core beside the legacy application, lock its contracts and LoopSpec through offline conformance tests, then migrate deterministic media functions behind ports. `VideoHarness` owns the bounded state machine and produces a filesystem RunBundle. CLI and optional FastAPI are thin adapters; no adapter owns accounts, provider credentials, or cross-request jobs. Once the new surface is verified, remove legacy frontend/SaaS code and add CI guards preventing its return.

**Tech Stack:** Python 3.10+, Pydantic v2, Typer, optional FastAPI/Uvicorn, httpx, FFmpeg/ffprobe, pytest/pytest-asyncio, Ruff, mypy, build.

## Global Constraints

- Publish package `vidsnap-harness`; import `vidsnap`; CLI `vidsnap`.
- Core model is exactly `qwen3.8-max`; compatible endpoint defaults to the approved Token Plan URL.
- Read credentials only from `VIDSNAP_QWEN_API_KEY`, then `QWEN_API_KEY`; never emit, save, accept through HTTP, or commit a key.
- Provider concurrency defaults to one and cannot exceed two.
- Direct baseline submits complete video at `fps=2`; Harness submits adaptive timestamped evidence.
- All live model calls remain out of normal CI; missing local credentials yield `BLOCKED_LIVE_BENCHMARK`, never fake success.
- Core has no database, Redis, Celery, SQLAlchemy, FastAPI-Users, OAuth, JWT, SMTP, frontend, or cloud-persistence dependency.
- FastAPI is an optional localhost-only, stateless adapter. It has no jobs, users, history, WebSocket notifications, or provider-key request fields.
- Every new production behavior follows RED → GREEN → REFACTOR. Run target and relevant regression tests after each task.
- Do not commit datasets, video media, RunBundles, cookies, `.env`, credentials, or generated benchmark results.

---

### Task 1: Package spine and offline quality tooling

**Files:**
- Create: `pyproject.toml`
- Create: `src/vidsnap/__init__.py`
- Create: `src/vidsnap/cli.py`
- Create: `tests/test_package_smoke.py`
- Create: `tests/conftest.py`
- Modify: `.gitignore`
- Delete: `backend/requirements.txt` only after Task 11 migrates all retained functionality

**Interfaces:**
- Produces `vidsnap.__version__` and a console entry point `vidsnap`.
- Produces optional dependency groups `server`, `providers`, `dev`.

- [x] **Step 1: Write the failing package contract test**

```python
from vidsnap import __version__
from vidsnap.cli import app


def test_package_exposes_version_and_cli_app() -> None:
    assert __version__ == "0.1.0"
    assert app.info.name == "vidsnap"
```

- [x] **Step 2: Run it to verify RED**

Run: `python -m pytest tests/test_package_smoke.py -q`

Expected: FAIL with `ModuleNotFoundError: No module named 'vidsnap'`.

- [x] **Step 3: Add the smallest installable package**

```toml
[project]
name = "vidsnap-harness"
version = "0.1.0"
requires-python = ">=3.10"

[project.scripts]
vidsnap = "vidsnap.cli:main"
```

```python
# src/vidsnap/__init__.py
__version__ = "0.1.0"
```

```python
# src/vidsnap/cli.py
import typer
app = typer.Typer(name="vidsnap")
def main() -> None:
    app()
```

Add `.venv/`, `.mypy_cache/`, `.ruff_cache/`, `run/`, and `benchmark-results/` to `.gitignore` without modifying user-owned content in the original worktree. `src/` remains tracked source code and must never be ignored.

- [x] **Step 4: Verify GREEN and build metadata**

Run: `python -m pytest tests/test_package_smoke.py -q && python -m pip install -e '.[dev]'`

Expected: PASS and editable install succeeds.

- [x] **Step 5: Commit**

```bash
git add pyproject.toml src tests .gitignore
git commit -m "feat: scaffold vidsnap harness package"
```

### Task 2: Versioned contracts and LoopSpec conformance

**Files:**
- Create: `src/vidsnap/contracts/__init__.py`
- Create: `src/vidsnap/contracts/models.py`
- Create: `src/vidsnap/contracts/loopspec.py`
- Create: `src/vidsnap/contracts/schemas/video_analysis.v1.json`
- Create: `tests/contracts/test_loopspec.py`
- Create: `tests/contracts/test_models.py`

**Interfaces:**
- Produces `TerminalState`, `VideoSource`, `VideoGoal`, `HarnessPolicy`, `Evidence`, `Claim`, `VideoAnalysisResult`, `LoopSpec`, and `default_loop_spec()`.
- `LoopSpec.digest()` returns a stable SHA-256 over canonical JSON.

- [ ] **Step 1: Write failing conformance tests**

```python
from vidsnap.contracts import TerminalState, default_loop_spec


def test_default_loop_spec_is_versioned_and_bounded() -> None:
    spec = default_loop_spec()
    assert spec.api_version == "vidsnap.loop/v1"
    assert spec.id == "grounded-video-understanding"
    assert spec.budgets.max_iterations == 3
    assert spec.budgets.max_model_calls == 12
    assert spec.budgets.max_evidence_frames == 96
    assert TerminalState.SUCCEEDED in spec.terminal_states
    assert len(spec.digest()) == 64
```

```python
import pytest
from vidsnap.contracts import Claim, EvidenceReference


def test_claim_requires_evidence_reference() -> None:
    with pytest.raises(ValueError):
        Claim(text="The speaker demonstrates a workflow", evidence=[])
    claim = Claim(text="The speaker demonstrates a workflow", evidence=[EvidenceReference(evidence_id="ev-1")])
    assert claim.evidence[0].evidence_id == "ev-1"
```

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/contracts -q`

Expected: FAIL because contracts do not exist.

- [ ] **Step 3: Implement strict Pydantic contracts**

Use `extra="forbid"`, explicit UTC timestamps, bounded policy fields, and terminal-state enums. `Claim` validation rejects an empty evidence list. `LoopSpec` embeds the approved allow-list, gates, budget values, and terminal states. Store the analysis output JSON Schema as a package asset and validate `VideoAnalysisResult` against it through Pydantic serialization.

- [ ] **Step 4: Verify GREEN and schema determinism**

Run: `python -m pytest tests/contracts -q && python -c 'from vidsnap.contracts import default_loop_spec; print(default_loop_spec().digest())'`

Expected: all tests pass; repeated digest output is identical.

- [ ] **Step 5: Commit**

```bash
git add src/vidsnap/contracts tests/contracts
git commit -m "feat: add versioned harness contracts"
```

### Task 3: RunBundle, redaction, and bounded event ledger

**Files:**
- Create: `src/vidsnap/loop/run_bundle.py`
- Create: `src/vidsnap/loop/events.py`
- Create: `tests/loop/test_run_bundle.py`
- Create: `tests/loop/test_events.py`

**Interfaces:**
- Produces `RunBundle.create(path, manifest)`, `append_event(event)`, `write_evidence(evidence)`, `write_result(result)`, `finalize(reason)` and `temporary_run_bundle()`.
- Produces `redact_provider_url()` and `RunEvent` typed event records.

- [ ] **Step 1: Write failing RunBundle tests**

```python
import json
from vidsnap.contracts import default_loop_spec
from vidsnap.loop.run_bundle import RunBundle


def test_run_bundle_writes_required_files_without_secrets(tmp_path) -> None:
    bundle = RunBundle.create(tmp_path / "run", loop_spec=default_loop_spec(), provider_url="https://key@host/v1")
    bundle.append_event("probe", {"duration_seconds": 3.0})
    bundle.finalize("SUCCEEDED")
    manifest = json.loads((tmp_path / "run" / "manifest.json").read_text())
    assert (tmp_path / "run" / "events.jsonl").exists()
    assert manifest["provider"]["base_url"] == "https://host/v1"
    assert "key" not in (tmp_path / "run" / "manifest.json").read_text()
```

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/loop/test_run_bundle.py -q`

Expected: FAIL with missing `vidsnap.loop.run_bundle`.

- [ ] **Step 3: Implement atomic JSON writes and JSONL events**

Create the five required paths, use a temporary file plus rename for JSON writes, include the LoopSpec hash and package code version in the manifest, and redact URLs/user-info/query values. `temporary_run_bundle()` must remove its directory when its context exits.

- [ ] **Step 4: Verify GREEN plus cleanup behavior**

Run: `python -m pytest tests/loop/test_run_bundle.py tests/loop/test_events.py -q`

Expected: PASS; tests assert final terminal reason and temporary directory cleanup.

- [ ] **Step 5: Commit**

```bash
git add src/vidsnap/loop tests/loop
git commit -m "feat: add auditable run bundles"
```

### Task 4: State machine, budgets, and verifier gates

**Files:**
- Create: `src/vidsnap/loop/state_machine.py`
- Create: `src/vidsnap/loop/verifier.py`
- Create: `tests/loop/test_state_machine.py`
- Create: `tests/loop/test_verifier.py`

**Interfaces:**
- Produces `LoopState`, `LoopController`, `BudgetExceeded`, and `VerificationReport`.
- `LoopController.transition(target)` rejects invalid transitions and `record_model_call()` terminates with `EXHAUSTED` at budget.

- [ ] **Step 1: Write failing loop tests**

```python
import pytest
from vidsnap.contracts import HarnessPolicy, TerminalState
from vidsnap.loop.state_machine import BudgetExceeded, LoopController, LoopState


def test_model_call_budget_terminates_without_success() -> None:
    controller = LoopController(HarnessPolicy(max_model_calls=1))
    controller.record_model_call()
    with pytest.raises(BudgetExceeded):
        controller.record_model_call()
    assert controller.terminal_state is TerminalState.EXHAUSTED
    assert controller.state is LoopState.TERMINAL
```

```python
from vidsnap.contracts import Claim, Evidence, EvidenceReference
from vidsnap.loop.verifier import verify_claims


def test_verifier_rejects_missing_evidence_and_out_of_bounds_timestamp() -> None:
    report = verify_claims(
        claims=[Claim(text="fact", evidence=[EvidenceReference(evidence_id="missing")])],
        evidence=[Evidence(id="ev-1", start_seconds=0, end_seconds=1, modality="frame")],
        duration_seconds=1,
    )
    assert report.passed is False
    assert "referenced_evidence_exists" in report.failed_gates
```

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/loop/test_state_machine.py tests/loop/test_verifier.py -q`

Expected: FAIL because the state machine and verifier do not exist.

- [ ] **Step 3: Implement deterministic transitions and gates**

Allow only `probe -> plan -> gather -> understand -> synthesize -> verify`, `verify -> repair -> gather`, and terminal transitions. Enforce iteration, model-call, frame, and wall-clock limits. The verifier checks schema validity, in-bounds timestamps, evidence existence, claim support, and non-empty required sections. Empty output is `NO_OP` or `PARTIAL`, never success.

- [ ] **Step 4: Verify GREEN and error cases**

Run: `python -m pytest tests/loop -q`

Expected: PASS; add assertions for invalid transition, empty output, and exhausted iteration budget.

- [ ] **Step 5: Commit**

```bash
git add src/vidsnap/loop tests/loop
git commit -m "feat: enforce bounded evidence loop"
```

### Task 5: Deterministic media probe and adaptive evidence sampler

**Files:**
- Create: `src/vidsnap/video/ports.py`
- Create: `src/vidsnap/video/probe.py`
- Create: `src/vidsnap/video/sampling.py`
- Create: `tests/video/test_probe.py`
- Create: `tests/video/test_sampling.py`
- Create: `tests/fixtures/make_synthetic_video.py`

**Interfaces:**
- Produces `MediaProbe`, `FrameCandidate`, `EvidenceSamplingPolicy`, `FFmpegPort`, and `AdaptiveSampler`.
- `AdaptiveSampler.select(candidates, max_frames)` returns unique ordered candidates at or below budget.

- [ ] **Step 1: Write failing sampler tests**

```python
from vidsnap.video.sampling import AdaptiveSampler, FrameCandidate


def test_sampler_preserves_coverage_and_deduplicates_near_identical_frames() -> None:
    candidates = [
        FrameCandidate(timestamp=0.0, score=1.0, perceptual_hash="a"),
        FrameCandidate(timestamp=0.1, score=0.9, perceptual_hash="a"),
        FrameCandidate(timestamp=5.0, score=0.8, perceptual_hash="b"),
        FrameCandidate(timestamp=10.0, score=0.7, perceptual_hash="c"),
    ]
    selected = AdaptiveSampler().select(candidates, max_frames=3)
    assert [item.perceptual_hash for item in selected] == ["a", "b", "c"]
    assert len(selected) <= 3
```

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/video/test_sampling.py -q`

Expected: FAIL with missing sampler module.

- [ ] **Step 3: Implement ports and pure selection first**

Define FFmpeg as a protocol. Implement candidate merging from uniform coverage, scene changes, visual/motion scores, ASR anchors, and OCR anchors. Select by type-aware score while retaining start/end coverage and perceptual-hash uniqueness. Add an FFmpeg implementation that probes media and extracts only selected frames. The synthetic fixture must be generated locally in test setup, never committed as media.

- [ ] **Step 4: Verify GREEN with FFmpeg microbenchmark**

Run: `python -m pytest tests/video -q`

Expected: PASS; if FFmpeg is installed, the synthetic test verifies duration, extracted timestamp bounds, and fewer selected frames than a 2-fps baseline.

- [ ] **Step 5: Commit**

```bash
git add src/vidsnap/video tests/video tests/fixtures
git commit -m "feat: add adaptive video evidence sampling"
```

### Task 6: Provider ports, prompt assets, and offline Qwen behavior

**Files:**
- Create: `src/vidsnap/config.py`
- Create: `src/vidsnap/providers/base.py`
- Create: `src/vidsnap/providers/qwen.py`
- Create: `src/vidsnap/providers/asr.py`
- Create: `src/vidsnap/prompts/*.json`
- Create: `tests/providers/test_config.py`
- Create: `tests/providers/test_qwen.py`
- Create: `tests/prompts/test_prompt_metadata.py`

**Interfaces:**
- Produces `HarnessConfig.from_env()`, `QwenCompatibleClient`, `SpeechRecognizer`, `ModelResponse`, and `PromptAsset`.
- `HarnessConfig.from_env()` caps requested concurrency at two and does not expose key values in `repr`.

- [ ] **Step 1: Write failing provider/security tests**

```python
from vidsnap.config import HarnessConfig


def test_config_prefers_vidsnap_key_and_caps_concurrency(monkeypatch) -> None:
    monkeypatch.setenv("VIDSNAP_QWEN_API_KEY", "rotated-secret")
    monkeypatch.setenv("QWEN_API_KEY", "fallback-secret")
    monkeypatch.setenv("VIDSNAP_MODEL_CONCURRENCY", "99")
    config = HarnessConfig.from_env()
    assert config.model == "qwen3.8-max"
    assert config.model_concurrency == 2
    assert "rotated-secret" not in repr(config)
```

```python
import pytest
from vidsnap.providers.qwen import QwenCompatibleClient, ProviderUnavailable


async def test_qwen_client_blocks_without_local_key() -> None:
    with pytest.raises(ProviderUnavailable):
        await QwenCompatibleClient(api_key=None).analyze_evidence([], "goal")
```

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/providers tests/prompts -q`

Expected: FAIL because configuration/provider/prompt assets are missing.

- [ ] **Step 3: Implement typed ports and versioned prompts**

Use httpx only inside the compatible client. Fix the model to `qwen3.8-max`, do not offer arbitrary model forwarding, and accept only typed evidence/goal payloads. Implement Base64 ASR chunk request construction without OSS. Store prompt JSON metadata with `prompt_id`, semver, input/output schema IDs, LoopSpec hash, and fixed model config. Treat all transcript/OCR strings as quoted data in prompts.

- [ ] **Step 4: Verify GREEN without network**

Run: `python -m pytest tests/providers tests/prompts -q`

Expected: PASS; mock `httpx.AsyncClient` only at the transport boundary and assert no secret reaches RunBundle/event serialization.

- [ ] **Step 5: Commit**

```bash
git add src/vidsnap/config.py src/vidsnap/providers src/vidsnap/prompts tests/providers tests/prompts
git commit -m "feat: add bounded qwen and asr providers"
```

### Task 7: Harness orchestration and evidence-grounded result synthesis

**Files:**
- Create: `src/vidsnap/harness.py`
- Create: `src/vidsnap/skills/base.py`
- Create: `src/vidsnap/skills/builtin.py`
- Create: `tests/test_harness.py`
- Create: `tests/skills/test_builtin_skills.py`

**Interfaces:**
- Produces `VideoHarness(config, ffmpeg, model, recognizer)` and `await run(source, goal, policy)`.
- Produces executable built-in skills matching the LoopSpec allow-list.

- [ ] **Step 1: Write failing end-to-end fake-provider test**

```python
import pytest
from vidsnap.contracts import HarnessPolicy, VideoGoal, VideoSource
from vidsnap.harness import VideoHarness


@pytest.mark.asyncio
async def test_harness_returns_supported_claims_and_trace(tmp_path, fake_media_port, fake_model) -> None:
    result = await VideoHarness(media=fake_media_port, model=fake_model).run(
        VideoSource(path=tmp_path / "input.mp4"),
        VideoGoal(objective="Summarize the demonstration"),
        HarnessPolicy(output_dir=tmp_path / "run"),
    )
    assert result.terminal_state.value == "SUCCEEDED"
    assert result.claims[0].evidence
    assert (tmp_path / "run" / "manifest.json").exists()
```

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/test_harness.py tests/skills -q`

Expected: FAIL because `VideoHarness` and skills do not exist.

- [ ] **Step 3: Implement the smallest bounded orchestrator**

Create a `RunContext` with controller, bundle, source, goal, policy, evidence, and only structured decisions. Invoke each approved skill through the registry, record events, invoke the model only through typed provider methods, run verifier gates, and allow at most two targeted repair gathers. Return `PARTIAL`, `NO_OP`, `BLOCKED`, `EXHAUSTED`, or `FAILED` truthfully.

- [ ] **Step 4: Verify GREEN and terminal behavior**

Run: `python -m pytest tests/test_harness.py tests/skills tests/loop -q`

Expected: PASS; add fake-provider tests for empty response, missing evidence, provider failure, and budget exhaustion.

- [ ] **Step 5: Commit**

```bash
git add src/vidsnap/harness.py src/vidsnap/skills tests/test_harness.py tests/skills
git commit -m "feat: implement grounded video harness loop"
```

### Task 8: CLI, SDK smoke tests, and stateless FastAPI adapter

**Files:**
- Modify: `src/vidsnap/cli.py`
- Create: `src/vidsnap/api/__init__.py`
- Create: `src/vidsnap/api/app.py`
- Create: `tests/test_cli.py`
- Create: `tests/api/test_app.py`

**Interfaces:**
- `vidsnap analyze VIDEO`, `vidsnap serve`, `vidsnap manifest RUN_DIR`, `vidsnap conformance`.
- `create_app(harness_factory)` exposes `/health`, `/v1/analyze`, `/v1/analyze/stream`, `/v1/manifest`.

- [ ] **Step 1: Write failing CLI/API boundary tests**

```python
from typer.testing import CliRunner
from vidsnap.cli import app


def test_cli_help_lists_harness_commands() -> None:
    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "analyze" in result.stdout
    assert "benchmark" in result.stdout
    assert "conformance" in result.stdout
```

```python
from fastapi.testclient import TestClient
from vidsnap.api import create_app


def test_api_is_local_stateless_health_surface(fake_harness_factory) -> None:
    response = TestClient(create_app(fake_harness_factory)).get("/health")
    assert response.status_code == 200
    assert response.json()["stateful_jobs"] is False
```

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/test_cli.py tests/api/test_app.py -q`

Expected: FAIL because commands and API factory are incomplete.

- [ ] **Step 3: Implement adapters without SaaS state**

CLI calls the SDK and renders a terminal summary. `serve` binds host `127.0.0.1` unless an explicit safe local override is set. API rejects fields named `api_key`, `model`, `prompt`, `provider_url`, and job/history routes do not exist. Each API call makes a temporary RunBundle; stream cancellation cancels the task and removes it.

- [ ] **Step 4: Verify GREEN and packaging smoke**

Run: `python -m pytest tests/test_cli.py tests/api -q && vidsnap --help && python -m build`

Expected: PASS; built wheel installs in a clean temporary venv and `vidsnap --help` succeeds.

- [ ] **Step 5: Commit**

```bash
git add src/vidsnap/cli.py src/vidsnap/api tests/test_cli.py tests/api
git commit -m "feat: add cli and stateless api adapter"
```

### Task 9: Fair Direct/Harness benchmark and metrics

**Files:**
- Create: `src/vidsnap/benchmark/runners.py`
- Create: `src/vidsnap/benchmark/metrics.py`
- Create: `src/vidsnap/benchmark/profiles.py`
- Create: `benchmarks/core-open/README.md`
- Create: `benchmarks/research-long/README.md`
- Create: `tests/benchmark/test_runners.py`
- Create: `tests/benchmark/test_metrics.py`

**Interfaces:**
- Produces `DirectRunner`, `HarnessRunner`, `BenchmarkCase`, `BenchmarkResult`, `compare_results()`.
- Direct runner uses exactly `fps=2`; Direct+ASR and Harness-Full share a supplied transcript object.

- [ ] **Step 1: Write failing fairness and metrics tests**

```python
from vidsnap.benchmark.runners import DirectRunner


def test_direct_runner_sets_explicit_two_fps_baseline(fake_model) -> None:
    runner = DirectRunner(model=fake_model)
    runner.prepare("video.mp4", transcript=None)
    assert fake_model.video_requests[0].fps == 2
```

```python
from vidsnap.benchmark.metrics import temporal_iou, unsupported_claim_rate


def test_deterministic_metrics_cover_temporal_and_grounding_quality() -> None:
    assert temporal_iou((0, 10), (5, 15)) == 1 / 3
    assert unsupported_claim_rate([True, False, False]) == 2 / 3
```

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/benchmark -q`

Expected: FAIL because benchmark runners and metrics are missing.

- [ ] **Step 3: Implement local-only runners and metrics**

Implement four ablations and shared `BenchmarkSettings` so model/output/task/randomization settings cannot diverge. Record every sample, bootstrap confidence intervals, and terminal states. Profile adapters only resolve local user paths and dataset metadata/licenses/SHA-256; they never download or include data in Git. Emit `NOT_YET_SUPERIOR` when thresholds are unmet.

- [ ] **Step 4: Verify GREEN**

Run: `python -m pytest tests/benchmark -q && vidsnap benchmark --help`

Expected: PASS; fake models prove transcript sharing and fixed fps.

- [ ] **Step 5: Commit**

```bash
git add src/vidsnap/benchmark benchmarks tests/benchmark
git commit -m "feat: add fair video harness benchmarks"
```

### Task 10: Remove legacy SaaS tree and protect the new boundary

**Files:**
- Delete: `frontend/`
- Delete: `backend/`
- Delete: `docker-compose.yml`
- Delete: `docker-compose.prod.yml`
- Delete: `start_local.sh`, `dev.sh`, `prod.sh`, `deploy.sh`
- Modify: `README.md`, `AGENTS.md`, `CONTRIBUTING.md`, `docs/README.md`, `docs/changelog.md`
- Create: `tests/test_no_saas_dependencies.py`
- Create: `docs/migration-to-harness.md`

**Interfaces:**
- Produces a repository with only package-oriented instructions and no legacy runtime imports.

- [ ] **Step 1: Write failing banned-surface test**

```python
from pathlib import Path


def test_repository_has_no_saas_runtime_tree() -> None:
    root = Path(__file__).parents[1]
    assert not (root / "frontend").exists()
    assert not (root / "backend").exists()
    forbidden = ("sqlalchemy", "fastapi_users", "celery", "redis", "oauth", "smtp", "jwt")
    runtime = "\n".join(path.read_text(errors="ignore") for path in (root / "src").rglob("*.py"))
    assert not any(token in runtime.lower() for token in forbidden)
```

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/test_no_saas_dependencies.py -q`

Expected: FAIL because the legacy tree still exists.

- [ ] **Step 3: Remove only after migrated replacements are green**

Delete exact legacy targets listed above with Git-aware deletion. Replace README with SDK/CLI/API/benchmark quickstarts, describe optional extras, document the breaking migration, and update repository instructions. Remove all product deployment docs and screenshots from active documentation; keep only an explicitly labelled historical archive if it contains no runtime instruction or secret.

- [ ] **Step 4: Verify GREEN and scan**

Run: `python -m pytest tests/test_no_saas_dependencies.py -q && rg -n -i 'sqlalchemy|fastapi-users|oauth|smtp|celery|redis|react|vite' --glob '!docs/project-archive/**' .`

Expected: test PASS; search returns only migration/archive mentions, never runtime/config/CI references.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor: remove legacy saas application"
```

### Task 11: CI, conformance command, release verification, and review package

**Files:**
- Modify: `.github/workflows/ci.yml`
- Create: `src/vidsnap/conformance.py`
- Create: `tests/test_conformance.py`
- Create: `scripts/secret_scan.py`
- Modify: `README.md`, `CONTRIBUTING.md`

**Interfaces:**
- `vidsnap conformance` returns nonzero on a contract/LoopSpec/banned-dependency violation.
- CI runs lint, format check, mypy, offline pytest, build, wheel smoke, CLI/API smoke, conformance, `git diff --check`, and secret scan.

- [ ] **Step 1: Write failing conformance test**

```python
from vidsnap.conformance import run_conformance


def test_conformance_passes_for_default_package() -> None:
    report = run_conformance()
    assert report.passed is True
    assert report.checks["loop_spec"] == "passed"
```

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/test_conformance.py -q`

Expected: FAIL because conformance implementation is missing.

- [ ] **Step 3: Implement offline release gates**

Conformance validates LoopSpec digest, prompt metadata, output schema, state machine, and forbidden dependencies. The secret scanner uses high-signal patterns and allow-listed false positives; it scans tracked source/config/docs but not fixture hashes. CI must never make live requests and must pin Python versions compatible with project metadata.

- [ ] **Step 4: Run the full verification gate**

Run:

```bash
ruff format --check .
ruff check .
mypy src
python -m pytest -q
python -m build
python -m pip install --force-reinstall dist/*.whl
vidsnap --help
vidsnap conformance
python scripts/secret_scan.py
git diff --check
```

Expected: every command succeeds without secrets, network model calls, or legacy runtime references.

- [ ] **Step 5: Commit**

```bash
git add .github src tests scripts README.md CONTRIBUTING.md
git commit -m "ci: enforce video harness conformance"
```

### Task 12: Live benchmark gate, independent review, push, and ready PR

**Files:**
- Create: `docs/benchmark-status.md`
- Modify: `docs/implementation/2026-08-11-video-harness-loop-state.md`

**Interfaces:**
- Produces an honest benchmark status: `BLOCKED_LIVE_BENCHMARK`, `NOT_YET_SUPERIOR`, or validated comparison results.

- [ ] **Step 1: Record offline benchmark status before live work**

```markdown
Status: BLOCKED_LIVE_BENCHMARK
Reason: no rotated local `VIDSNAP_QWEN_API_KEY` was available to run a real comparison.
Completed: deterministic runners, fairness tests, metric tests, and FFmpeg synthetic microbenchmark.
```

- [ ] **Step 2: Run live comparison only when a local rotated key is present**

Run: `VIDSNAP_QWEN_API_KEY=... vidsnap benchmark compare --profile core-open --limit 3`

Expected: real per-sample RunBundles outside the repository and either metrics or `NOT_YET_SUPERIOR`; never paste the key in a command history, log, document, or PR.

- [ ] **Step 3: Perform independent review**

Review the complete diff for SaaS remnants, API state, budget/terminal rules, prompt injection, evidence/timestamp correctness, fairness, licenses, secret exposure, and package usability. Fix P0/P1 findings; document any P2 decision in the PR.

- [ ] **Step 4: Push and create ready PR**

```bash
git push -u origin codex/video-harness-core
gh pr create --base vidsnap_slim --head codex/video-harness-core --title "refactor: replace VidSnap SaaS with video harness core" --fill
```

Expected: non-draft PR includes removal summary, architecture, migration/configuration, benchmark honesty, verification evidence, and security/data-license notes. Request an authorized non-author reviewer; do not merge.

- [ ] **Step 5: Wait for CI and record final state**

Run: `gh pr checks --watch`

Expected: all CI checks pass. If live credentials are absent, final project state remains `BLOCKED_LIVE_BENCHMARK` while implementation/PR delivery can otherwise complete.
