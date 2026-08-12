# Agentic Video Benchmark Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a bounded Qwen-selected acquisition plan to VidSnap Harness and run a reproducible 54-case internal comparison against Direct and fixed-order Harness baselines after a six-case smoke gate.

**Architecture:** `probe_media` remains mandatory and deterministic. In `agentic` mode, Qwen 3.8 Max receives only typed probe metadata and the user goal, returns a schema-validated plan choosing zero or more acquisition skills from `transcribe_audio` and `sample_evidence`, and the existing deterministic inspect/synthesize/verify stages execute only when their required evidence exists. A benchmark adapter consumes locally cached Video-MME and MVBench files, keeps all case manifests, downloaded media, transcripts, RunBundles, raw responses, and reports outside the repository, then reports paired accuracy, tool-choice quality, and resource usage across the three variants.

**Tech Stack:** Python 3.10, Pydantic v2, httpx, FFmpeg/ffprobe, Typer, pytest/pytest-asyncio, Qwen 3.8 Max through the Token Plan compatible endpoint read from local Hermes configuration.

## Global Constraints

- Use only `qwen3.8-max`; the live launcher reads the endpoint and key from Hermes and never accepts them in a benchmark manifest or HTTP request.
- Read the Hermes credential only in the launcher process, inject it through `VIDSNAP_QWEN_API_KEY`, and never print, write, commit, hash, or include it in a RunBundle.
- Retain the LoopSpec allow-list, `max_iterations <= 3`, `max_model_calls <= 12`, `max_evidence_frames <= 96`, and the six existing terminal states.
- `probe_media`, result synthesis, and verification remain harness-controlled; Qwen may select only acquisition skills `transcribe_audio` and `sample_evidence`.
- `fixed` remains the default policy so existing callers retain the current behavior; agentic selection is opt-in as `tool_mode="agentic"`.
- Do not commit benchmark media, source annotations, generated manifests, RunBundles, raw model responses, credentials, or result reports.
- Write experiment files under a caller-provided directory outside the repository; record source URLs, dataset versions, local SHA-256s, selected case IDs, and a UTC timestamp in its local manifest.
- Use Video-MME and MVBench only for private, non-commercial internal research; cite their official repositories in the local report.
- Every baseline uses the same Qwen model, question text, answer options, source video, transcript availability, and randomized case order. Direct uses complete-video input when supported, otherwise the complete timeline at exactly 2 fps.
- Run six smoke cases before the formal experiment and derive the formal cost projection only from provider-reported smoke usage.
- Run exactly 54 formal cases: 36 `Video-MME` and 18 `MVBench`.

---

## File Structure

- `src/vidsnap/contracts/tool_plan.py`: strict, minimal model-selected acquisition-plan contract.
- `src/vidsnap/contracts/__init__.py`: exports the public tool-plan types.
- `src/vidsnap/providers/base.py`: typed planner response and optional tool-planning port.
- `src/vidsnap/providers/qwen.py`: fixed-endpoint Qwen request and parser for tool planning.
- `src/vidsnap/harness.py`: policy-gated planning event and conditional acquisition execution.
- `src/vidsnap/benchmark/formal.py`: local-case models, exact MCQ parsing, paired accuracy, bootstrap interval, and tool-selection metrics.
- `src/vidsnap/benchmark/__init__.py`: exports formal benchmark public types.
- `src/vidsnap/benchmark/live.py`: fixed-model MCQ client and Direct/Fixed/Agentic execution engine with complete usage accounting.
- `scripts/run_agentic_benchmark.py`: local-only CLI that validates a pre-downloaded six- or 54-case manifest, runs Direct/Fixed/Agentic in counterbalanced order, and emits a report outside the repository.
- `scripts/run_with_hermes_qwen.py`: non-printing process launcher that injects Hermes endpoint and credential only into its child.
- `benchmarks/agentic/README.md`: dataset acquisition, license, manifest, and reproduction instructions without distributing dataset material.
- `tests/contracts/test_tool_plan.py`: public contract validation.
- `tests/providers/test_qwen.py`: Qwen request/parse contract for the planner call.
- `tests/test_harness.py`: fixed compatibility and agentic conditional-acquisition behavior.
- `tests/benchmark/test_formal.py`: exact answer parsing, bootstrap determinism, and tool-decision metric tests.
- `tests/benchmark/test_live.py`: three-path execution, fixed-model request, usage, fallback, and verifier behavior.
- `tests/test_agentic_benchmark_script.py`: launcher rejects in-repository output and accepts an external manifest path.
- `tests/test_hermes_launcher.py`: child-only environment injection without value disclosure.

### Task 1: Define the safe model-selected acquisition contract

**Files:**
- Create: `src/vidsnap/contracts/tool_plan.py`
- Modify: `src/vidsnap/contracts/__init__.py`
- Test: `tests/contracts/test_tool_plan.py`

**Interfaces:**
- Produces `AcquisitionTool`, `ToolPlan`, and `ToolMode`.
- `ToolPlan(tools=("transcribe_audio",))` is valid; duplicate tools and tools outside the two acquisition skills raise `ValueError`.

- [ ] **Step 1: Write the failing test**

```python
import pytest

from vidsnap.contracts import ToolPlan


def test_tool_plan_allows_only_unique_acquisition_skills() -> None:
    assert ToolPlan(tools=("transcribe_audio",)).tools == ("transcribe_audio",)
    with pytest.raises(ValueError, match="duplicate"):
        ToolPlan(tools=("sample_evidence", "sample_evidence"))
    with pytest.raises(ValueError):
        ToolPlan(tools=("verify_claims",))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/contracts/test_tool_plan.py -q`

Expected: FAIL because `ToolPlan` is not importable.

- [ ] **Step 3: Write minimal implementation**

```python
class ToolPlan(StrictModel):
    tools: tuple[Literal["transcribe_audio", "sample_evidence"], ...] = Field(max_length=2)

    @model_validator(mode="after")
    def reject_duplicate_tools(self) -> ToolPlan:
        if len(set(self.tools)) != len(self.tools):
            raise ValueError("tool plan contains duplicate tools")
        return self
```

Define `ToolMode = Literal["fixed", "agentic"]`, export all three types, and permit an empty tuple so the model can truthfully request no acquisition for a goal with no observable evidence requirement.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/contracts/test_tool_plan.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/vidsnap/contracts/tool_plan.py src/vidsnap/contracts/__init__.py tests/contracts/test_tool_plan.py
git commit -m "feat: add bounded tool-plan contract"
```

### Task 2: Add a fixed Qwen planner port

**Files:**
- Modify: `src/vidsnap/providers/base.py`
- Modify: `src/vidsnap/providers/qwen.py`
- Test: `tests/providers/test_qwen.py`

**Interfaces:**
- Produces `ToolPlanResponse(plan: ToolPlan, input_tokens: int, output_tokens: int)` and `ToolPlanningPort.plan_tools(probe: MediaProbe, goal: VideoGoal) -> ToolPlanResponse`.
- `QwenCompatibleClient.plan_tools` always posts to the fixed endpoint with model `qwen3.8-max`, `response_format={"type": "json_object"}`, typed probe fields, typed goal fields, and no evidence artifacts.

- [ ] **Step 1: Write the failing test**

```python
@pytest.mark.asyncio
async def test_qwen_tool_planner_uses_fixed_model_and_strict_plan() -> None:
    captured: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["payload"] = json.loads(request.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"tools":["transcribe_audio"]}'}}]})

    response = await QwenCompatibleClient(api_key="test", transport=httpx.MockTransport(handler)).plan_tools(
        MediaProbe(duration_seconds=12, fps=24, width=640, height=360, has_audio=True),
        VideoGoal(objective="What did the speaker say?"),
    )

    assert captured["payload"]["model"] == "qwen3.8-max"
    assert response.plan.tools == ("transcribe_audio",)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/providers/test_qwen.py::test_qwen_tool_planner_uses_fixed_model_and_strict_plan -q`

Expected: FAIL because `plan_tools` does not exist.

- [ ] **Step 3: Write minimal implementation**

```python
async def plan_tools(self, probe: MediaProbe, goal: VideoGoal) -> ToolPlanResponse:
    payload = {"model": QWEN_MODEL, "messages": [...], "response_format": {"type": "json_object"}}
    response = await self._post(payload)
    return ToolPlanResponse(plan=ToolPlan.model_validate(json.loads(content)), ...)
```

Use a planner system message that explicitly forbids model-selected endpoints, budgets, arbitrary tool names, and evidence instructions. Reuse the existing semaphore and error translation; do not add a second credential path.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/providers/test_qwen.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/vidsnap/providers/base.py src/vidsnap/providers/qwen.py tests/providers/test_qwen.py
git commit -m "feat: add qwen tool planner port"
```

### Task 3: Execute only Qwen-selected acquisition skills in agentic mode

**Files:**
- Modify: `src/vidsnap/contracts/models.py`
- Modify: `src/vidsnap/harness.py`
- Test: `tests/test_harness.py`

**Interfaces:**
- `HarnessPolicy(tool_mode: ToolMode = "fixed")` preserves fixed behavior.
- `VideoHarness(..., planner: ToolPlanningPort | None = None)` obtains a `ToolPlan` only when `tool_mode="agentic"`.
- `RunBundle/events.jsonl` receives a `tool_plan` event containing only mode, selected skills, and provider-reported token counts.

- [ ] **Step 1: Write the failing test**

```python
@pytest.mark.asyncio
async def test_agentic_harness_uses_only_planned_audio_acquisition(tmp_path) -> None:
    media = FakeMediaPort(has_audio=True)
    planner = FakePlanner(ToolPlan(tools=("transcribe_audio",)))
    result = await VideoHarness(media=media, model=FakeModel(), planner=planner).run(
        VideoSource(path=tmp_path / "input.mp4"),
        VideoGoal(objective="What was said?"),
        HarnessPolicy(tool_mode="agentic", output_dir=tmp_path / "run"),
    )

    events = (tmp_path / "run" / "events.jsonl").read_text()
    assert '"selected_tools":["transcribe_audio"]' in events
    assert media.visual_candidate_calls == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_harness.py::test_agentic_harness_uses_only_planned_audio_acquisition -q`

Expected: FAIL because `tool_mode` and `planner` do not exist.

- [ ] **Step 3: Write minimal implementation**

In the `PLAN` state, call the planner after deterministic probing, record one bounded model call, store the returned `ToolPlan`, and append the redacted `tool_plan` event. In `GATHER`, run `transcribe_audio` and/or `sample_evidence` only when fixed mode is active or their names appear in the plan. For an agentic audio-only plan, `inspect_evidence` must leave transcript evidence intact and continue to synthesis instead of requiring frames. A missing planner or unavailable provider in agentic mode terminates `BLOCKED`.

- [ ] **Step 4: Run focused and full harness tests**

Run: `python -m pytest tests/test_harness.py -q`

Expected: PASS, including fixed-mode compatibility and new audio-only behavior.

- [ ] **Step 5: Commit**

```bash
git add src/vidsnap/contracts/models.py src/vidsnap/harness.py tests/test_harness.py
git commit -m "feat: let harness select acquisition tools"
```

### Task 4: Build deterministic formal-evaluation primitives

**Files:**
- Create: `src/vidsnap/benchmark/formal.py`
- Modify: `src/vidsnap/benchmark/__init__.py`
- Test: `tests/benchmark/test_formal.py`

**Interfaces:**
- Produces `FormalCase`, `VariantOutcome`, `parse_mcq_answer`, `tool_selection_score`, and `paired_bootstrap_delta`.
- `FormalCase` contains only local source path, case ID, question/options/answer, expected acquisition tools, dataset name/version/license, and source SHA-256.
- `paired_bootstrap_delta` is seed-controlled and returns the point delta plus a 95% percentile interval over paired binary correctness values.

- [ ] **Step 1: Write the failing test**

```python
def test_bootstrap_delta_is_deterministic_and_reports_harness_gain() -> None:
    report = paired_bootstrap_delta([0, 0, 1, 1], [1, 1, 1, 1], seed=7, resamples=1_000)

    assert report.point_estimate == 0.5
    assert report.lower <= 0.5 <= report.upper
    assert parse_mcq_answer("The best answer is: c.", ("A", "B", "C", "D")) == "C"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/benchmark/test_formal.py -q`

Expected: FAIL because `formal` does not exist.

- [ ] **Step 3: Write minimal implementation**

Implement exact option normalization, a `ToolSelectionScore` with precision/recall/F1 and false-call/missed-call counters, and bootstrap resampling with `random.Random(seed)`. Reject outcome arrays of different lengths, empty arrays, invalid binary values, duplicate options, and answers outside the declared options.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/benchmark/test_formal.py tests/benchmark/test_metrics.py tests/benchmark/test_runners.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/vidsnap/benchmark/formal.py src/vidsnap/benchmark/__init__.py tests/benchmark/test_formal.py
git commit -m "feat: add formal benchmark statistics"
```

### Task 5: Provide a local-only phased runner and reproduction guide

**Files:**
- Create: `scripts/run_agentic_benchmark.py`
- Create: `scripts/run_with_hermes_qwen.py`
- Create: `src/vidsnap/benchmark/live.py`
- Create: `benchmarks/agentic/README.md`
- Test: `tests/test_agentic_benchmark_script.py`

**Interfaces:**
- Smoke command: `python scripts/run_agentic_benchmark.py --phase smoke --manifest /absolute/path/smoke.jsonl --output-dir /absolute/path/smoke-results --seed 20260812`.
- Formal command: `python scripts/run_agentic_benchmark.py --phase formal --manifest /absolute/path/formal.jsonl --output-dir /absolute/path/formal-results --smoke-report /absolute/path/smoke-results/report.json --seed 20260812`.
- Manifest validation requires exactly six distinct cases for smoke or exactly 54 distinct cases for formal. The formal split is 36 `Video-MME` and 18 `MVBench`; every video exists locally, SHA-256 matches, license text is non-empty, and expected tools are a subset of the two acquisition skills.
- Output report includes per-variant accuracy, paired Direct→Fixed and Fixed→Agentic bootstrap deltas, tool-selection precision/recall/F1, false-call/missed-call rates, per-case latency/calls/frames, environment metadata excluding secrets, and `NOT_YET_SUPERIOR` unless Agentic's 95% CI lower bound versus Fixed is greater than zero.

- [ ] **Step 1: Write the failing test**

```python
def test_runner_rejects_output_inside_repository(tmp_path) -> None:
    result = subprocess.run(
        [sys.executable, "scripts/run_agentic_benchmark.py", "--manifest", str(tmp_path / "cases.jsonl"), "--output-dir", "results"],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    assert "outside the repository" in result.stderr
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_agentic_benchmark_script.py::test_runner_rejects_output_inside_repository -q`

Expected: FAIL because the runner script does not exist.

- [ ] **Step 3: Write minimal implementation**

Use `argparse`; resolve paths before reading them; reject any output path under the repository root; validate the JSONL before making a provider call; run variants in a deterministic Latin-square rotation derived from the seed; catch individual provider failures as explicit per-case terminal outcomes; and write only external JSON/JSONL reports. A formal run must reject a missing or unsuccessful smoke report. The guide must state the dataset-specific research/license notices, the exact 36/18 mix, the Direct fps=2 fallback, Hermes environment injection, and that no benchmark result may be committed.

- [ ] **Step 4: Run script tests**

Run: `python -m pytest tests/test_agentic_benchmark_script.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/run_agentic_benchmark.py benchmarks/agentic/README.md tests/test_agentic_benchmark_script.py
git commit -m "feat: add local agentic benchmark runner"
```

### Task 6: Validate package and conduct the six-case smoke evaluation

**Files:**
- Modify: `docs/superpowers/plans/2026-08-12-agentic-video-benchmark.md` (check completed tasks and record only commands/status, not data or metrics)

**Interfaces:**
- Uses an externally generated, six-case JSONL manifest and external result directory.
- Does not modify source code after the final verification gate without restarting verification.

- [ ] **Step 1: Run full offline verification**

Run: `ruff format --check src tests scripts && ruff check . && mypy src && python -m pytest -q && python -m build && vidsnap conformance && python scripts/secret_scan.py && git diff --check`

Expected: all commands exit zero; any dependency warning is recorded without claiming a pristine warning-free environment.

- [ ] **Step 2: Read Hermes configuration safely and inject a process-local credential**

Run: use a launcher that reads the Qwen credential into `VIDSNAP_QWEN_API_KEY` without echoing it, then executes the benchmark script in the same process tree.

Expected: no credential appears in shell output, source files, manifests, RunBundles, or reports.

- [ ] **Step 3: Run the six-case smoke evaluation**

Run: `python scripts/run_agentic_benchmark.py --phase smoke --manifest /absolute/path/smoke.jsonl --output-dir /absolute/path/smoke-results --seed 20260812`

Expected: exactly 18 variant outcomes, a local report with all required usage fields, the chosen Direct input mode, and explicit terminal statuses for failures or unsupported provider requests.

- [ ] **Step 4: Audit the local report**

Run: verify the six-case composition, same model identifier for every outcome, per-case source hash, Direct fps exactly 2 when frame fallback is active, and absence of credential-like strings with `scripts/secret_scan.py` adapted to the external report directory. Compute the 54-case projection from summed provider-reported usage; do not substitute a guessed unit price.

Expected: report either labels Agentic `HARNESS_SUPERIOR` only when the pre-registered CI criterion is met, or `NOT_YET_SUPERIOR`; no other conclusion is allowed.

- [ ] **Step 5: Commit implementation, not research data**

```bash
git add docs/superpowers/plans/2026-08-12-agentic-video-benchmark.md src tests scripts benchmarks/agentic
git commit -m "feat: add agentic video benchmark"
```

### Task 7: Conduct and audit the 54-case formal evaluation

**Files:**
- External only: formal manifest, media, raw outcomes, and report.

**Interfaces:**
- Consumes the successful six-case smoke report and its measured usage projection.
- Produces exactly 162 variant outcomes for 36 Video-MME and 18 MVBench cases.

- [ ] **Step 1: Validate the formal manifest without provider calls**

Run: `.venv/bin/python scripts/run_agentic_benchmark.py --phase formal --validate-only --manifest /absolute/path/formal.jsonl --output-dir /absolute/path/formal-results --smoke-report /absolute/path/smoke-results/report.json --seed 20260812`

Expected: 54 unique cases, a 36/18 dataset split, valid local SHA-256s, and all required strata represented.

- [ ] **Step 2: Run the formal experiment**

Run: use `scripts/run_with_hermes_qwen.py` to execute the same command without `--validate-only`.

Expected: 162 typed variant outcomes or explicit blocked/failed statuses; no implicit model or modality fallback.

- [ ] **Step 3: Audit the report and conclusion rule**

Run: inspect the machine-readable audit summary and run the external artifact secret scan.

Expected: paired accuracy delta and 95% bootstrap CI, tool metrics, usage and verifier pass rate. The conclusion is `HARNESS_SUPERIOR` only when the Agentic-minus-Fixed CI lower bound is greater than zero; otherwise it is `NOT_YET_SUPERIOR`.
