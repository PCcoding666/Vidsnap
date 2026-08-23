# Short-Video Smoke Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the failing mixed-duration smoke set with the approved six-case short-video set, prevent it from unlocking the full-duration formal experiment, and run one credential-safe Qwen 3.8 smoke after CI.

**Architecture:** Keep the benchmark engine unchanged. Update the registered cases, phase-specific composition check, report scope, formal gate, and external manifest digest. Use the existing Hermes launcher for exactly one live child process.

**Tech Stack:** Python 3.10, Pydantic, pytest, Ruff, mypy, ffprobe/ffmpeg, Qwen 3.8 Token Plan, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-08-17-short-video-smoke-design.md`

## Global Constraints

- All provider calls use Qwen 3.8 through Token Plan.
- Direct sends the complete timeline as image frames at exactly 2 fps.
- Smoke is exactly Video-MME `069-1`, `069-2`, `069-3` and MVBench Action Antonym `6`, `18`, `19`.
- All smoke cases are short and retain explicit, independently reviewed tool labels.
- A short smoke cannot authorize the 54-case formal run.
- No videos, manifests, reports, outcomes, raw provider data, RunBundles, or credentials enter git.
- Any live failure stops execution; do not run formal and do not merge.

---

### Task 1: Lock selection and composition

**Files:**
- Modify: `tests/benchmark/test_manifest_preparation.py`
- Modify: `tests/test_agentic_benchmark_script.py`
- Modify: `src/vidsnap/benchmark/manifest.py`
- Modify: `scripts/run_agentic_benchmark.py`

**Interfaces:**
- Consumes: `SMOKE_SELECTION` and `_validate_composition(cases, phase)`.
- Produces: the exact three/three selection and all-short smoke validation; formal validation stays unchanged.

- [ ] **Step 1: Write failing selection assertions**

```python
assert [item.case_id for item in SMOKE_SELECTION["Video-MME"]] == [
    "069-1", "069-2", "069-3"
]
assert [item.case_id for item in SMOKE_SELECTION["MVBench"]] == ["6", "18", "19"]
assert len(SMOKE_SELECTION["Video-MME"]) == 3
assert len(SMOKE_SELECTION["MVBench"]) == 3
```

Keep the existing formal/smoke disjointness assertion.

- [ ] **Step 2: Write a failing all-short composition test**

Make `_write_smoke_manifest` emit `short` for every row and add:

```python
def test_smoke_composition_accepts_only_short_videos(tmp_path) -> None:
    namespace = runpy.run_path("scripts/run_agentic_benchmark.py")
    cases = namespace["_load_manifest"](_write_smoke_manifest(tmp_path))
    assert namespace["_validate_composition"](cases, "smoke") == {
        "MVBench": 2, "Video-MME": 4,
    }
    mixed = list(cases)
    mixed[0] = mixed[0].model_copy(update={"duration_stratum": "medium"})
    with __import__("pytest").raises(ValueError, match="short videos"):
        namespace["_validate_composition"](mixed, "smoke")
```

- [ ] **Step 3: Verify RED**

```bash
.venv/bin/python -m pytest -q \
  tests/benchmark/test_manifest_preparation.py::test_registered_selection_has_required_counts_and_no_smoke_overlap \
  tests/test_agentic_benchmark_script.py::test_smoke_composition_accepts_only_short_videos
```

Expected: old IDs/counts fail and all-short composition is rejected.

- [ ] **Step 4: Register the exact cases**

```python
SMOKE_SELECTION = {
    "Video-MME": (
        _registered("069-1", "Counting Problem", ("speech",),
                    ("transcribe_audio",), "speech-required"),
        _registered("069-2", "Object Recognition", ("visual",),
                    ("sample_evidence",), "visual-required"),
        _registered("069-3", "Action Recognition", ("visual",),
                    ("sample_evidence",), "visual-required"),
    ),
    "MVBench": tuple(
        _registered(case_id, "Action Antonym", ("visual", "temporal"),
                    ("sample_evidence",), "visual-required")
        for case_id in ("6", "18", "19")
    ),
}
```

- [ ] **Step 5: Make duration validation phase-specific**

```python
duration_strata = {case.duration_stratum for case in cases}
if phase == "smoke" and duration_strata != {"short"}:
    raise ValueError("smoke manifest must contain only short videos")
if phase == "formal" and duration_strata != {"short", "medium", "long"}:
    raise ValueError("formal manifest must cover short, medium, and long durations")
```

- [ ] **Step 6: Verify GREEN and commit**

```bash
.venv/bin/python -m pytest -q tests/benchmark/test_manifest_preparation.py \
  tests/test_agentic_benchmark_script.py
git add src/vidsnap/benchmark/manifest.py scripts/run_agentic_benchmark.py \
  tests/benchmark/test_manifest_preparation.py tests/test_agentic_benchmark_script.py
git commit -m "test: preregister short-video smoke cases"
```

---

### Task 2: Mark scope and block formal authorization

**Files:**
- Modify: `tests/benchmark/test_reporting.py`
- Modify: `tests/test_agentic_benchmark_script.py`
- Modify: `src/vidsnap/benchmark/reporting.py`
- Modify: `scripts/run_agentic_benchmark.py`

**Interfaces:**
- Consumes: `build_benchmark_report(...)` and `_load_smoke_gate(path)`.
- Produces: `benchmark_scope="short_video_only"` for smoke and a formal gate requiring `benchmark_scope="full_duration"`.

- [ ] **Step 1: Write failing report assertions**

```python
assert report["benchmark_scope"] == "short_video_only"
assert "Short-video smoke only" in " ".join(report["scope_limitations"])
```

Add a test with all Video-MME cases sharing one `source_sha256` and assert:

```python
assert "Video-MME slice contains three questions from one source video." in report[
    "scope_limitations"
]
```

- [ ] **Step 2: Write a failing formal-gate test**

Build a structurally valid success payload with
`benchmark_scope="short_video_only"`, then assert:

```python
with pytest.raises(ValueError, match="cannot authorize.*formal"):
    namespace["_load_smoke_gate"](report)
```

Change the successful provenance fixture to `benchmark_scope="full_duration"` and expect that field in provenance.

- [ ] **Step 3: Verify RED**

```bash
.venv/bin/python -m pytest -q \
  tests/benchmark/test_reporting.py::test_smoke_report_uses_paired_metrics_and_measured_54_case_projection \
  tests/test_agentic_benchmark_script.py::test_short_video_smoke_cannot_authorize_formal
```

Expected: scope is absent and the short report is accepted.

- [ ] **Step 4: Add report scope and limitations**

```python
if phase == "smoke":
    scope_limitations.append(
        "Short-video smoke only; it does not validate medium or long videos."
    )
    video_mme_sources = {
        case.source_sha256 for case in cases if case.dataset == "Video-MME"
    }
    if len(video_mme_sources) == 1:
        scope_limitations.append(
            "Video-MME slice contains three questions from one source video."
        )
```

Add report field:

```python
"benchmark_scope": "short_video_only" if phase == "smoke" else "full_duration_formal",
```

- [ ] **Step 5: Enforce and audit the gate**

```python
if payload.get("benchmark_scope") != "full_duration":
    raise ValueError("short-video smoke cannot authorize the full-duration formal phase")
```

Add `"benchmark_scope": payload["benchmark_scope"]` to `_smoke_gate_provenance`.

- [ ] **Step 6: Verify GREEN and commit**

```bash
.venv/bin/python -m pytest -q tests/benchmark/test_reporting.py \
  tests/test_agentic_benchmark_script.py
git add src/vidsnap/benchmark/reporting.py scripts/run_agentic_benchmark.py \
  tests/benchmark/test_reporting.py tests/test_agentic_benchmark_script.py
git commit -m "fix: isolate short-video smoke scope"
```

---

### Task 3: Freeze manifest digest and align docs

**Files:**
- Modify: `tests/benchmark/test_manifest_preparation.py`
- Modify: `src/vidsnap/benchmark/manifest.py`
- Modify: `docs/superpowers/specs/2026-08-12-agentic-video-benchmark-design.md`
- Modify: `docs/superpowers/plans/2026-08-12-agentic-video-benchmark.md`
- External rewrite: `/Users/chengpeng/VidsnapBenchmarks/agentic-video-20260812/manifests/smoke.jsonl`

**Interfaces:**
- Consumes: `prepare_manifests(root)`.
- Produces: smoke digest `5e82277f5d4d2774c27dc1d47f26a9fcf394217c99f8b6a99d2d3c8007e0a265`.

- [ ] **Step 1: Write and run a failing digest test**

```python
def test_registered_short_smoke_manifest_digest_is_frozen() -> None:
    assert REGISTERED_MANIFEST_SHA256["smoke"] == (
        "5e82277f5d4d2774c27dc1d47f26a9fcf394217c99f8b6a99d2d3c8007e0a265"
    )
```

```bash
.venv/bin/python -m pytest -q \
  tests/benchmark/test_manifest_preparation.py::test_registered_short_smoke_manifest_digest_is_frozen
```

Expected: FAIL with old digest `e8e46847...`.

- [ ] **Step 2: Register the exact digest**

Set `REGISTERED_MANIFEST_SHA256["smoke"]` to
`5e82277f5d4d2774c27dc1d47f26a9fcf394217c99f8b6a99d2d3c8007e0a265` and leave the formal digest unchanged.

- [ ] **Step 3: Regenerate and verify external data**

```bash
.venv/bin/python scripts/prepare_agentic_manifests.py \
  --root /Users/chengpeng/VidsnapBenchmarks/agentic-video-20260812
shasum -a 256 \
  /Users/chengpeng/VidsnapBenchmarks/agentic-video-20260812/manifests/smoke.jsonl
```

Expected SHA-256 is the registered digest. Inspect safe fields for ordered IDs, split, labels, reasons, hashes, and all-short strata.

- [ ] **Step 4: Align original protocol docs**

State that replacement smoke is short-only, three/three, cannot authorize full-duration formal, and carries no research conclusion. Keep formal thresholds unchanged.

- [ ] **Step 5: Verify GREEN and commit**

```bash
.venv/bin/python -m pytest -q tests/benchmark/test_manifest_preparation.py \
  tests/test_agentic_benchmark_script.py tests/benchmark/test_reporting.py
git diff --check
git add src/vidsnap/benchmark/manifest.py \
  tests/benchmark/test_manifest_preparation.py \
  docs/superpowers/specs/2026-08-12-agentic-video-benchmark-design.md \
  docs/superpowers/plans/2026-08-12-agentic-video-benchmark.md \
  docs/superpowers/plans/2026-08-21-short-video-smoke.md
git commit -m "docs: register short-video smoke manifest"
```

Do not stage the external manifest.

---

### Task 4: Verify and update Draft PR #8

**Files:** Existing Draft PR `https://github.com/PCcoding666/Vidsnap/pull/8`.

**Interfaces:** Consumes Tasks 1-3; produces a clean pushed branch and passing CI.

- [ ] **Step 1: Run all local gates**

```bash
.venv/bin/ruff format --check src tests scripts
.venv/bin/ruff check .
.venv/bin/mypy src
.venv/bin/python -m pytest -q
.venv/bin/python -m build
.venv/bin/vidsnap conformance
.venv/bin/python scripts/secret_scan.py
git diff --check
```

- [ ] **Step 2: Confirm only approved files are committed**

```bash
git status -sb
git diff origin/codex/agentic-benchmark...HEAD --stat
git log --oneline origin/codex/agentic-benchmark..HEAD
```

- [ ] **Step 3: Push and wait**

```bash
git push origin codex/agentic-benchmark
gh pr checks 8 --watch --interval 10
```

Expected: PR remains Draft against `codex/video-harness-core`; CI passes. Do not merge.

---

### Task 5: Run one live short smoke

**Files:**
- Input: `/Users/chengpeng/VidsnapBenchmarks/agentic-video-20260812/manifests/smoke.jsonl`
- Output: `/Users/chengpeng/VidsnapBenchmarks/agentic-video-20260812/results/smoke-short-20260821`

**Interfaces:** Consumes CI-approved code and Hermes settings; produces 18 redacted outcomes outside git.

- [ ] **Step 1: Validate without credentials**

Ensure output does not exist, then run:

```bash
.venv/bin/python scripts/run_agentic_benchmark.py --phase smoke --validate-only \
  --manifest /Users/chengpeng/VidsnapBenchmarks/agentic-video-20260812/manifests/smoke.jsonl \
  --output-dir /Users/chengpeng/VidsnapBenchmarks/agentic-video-20260812/results/smoke-short-20260821 \
  --seed 20260812
```

Expected: `VALIDATED`, six cases, three per dataset, registered digest.

- [ ] **Step 2: Run one Hermes-isolated child**

```bash
.venv/bin/python scripts/run_with_hermes_qwen.py -- \
  .venv/bin/python scripts/run_agentic_benchmark.py --phase smoke \
  --manifest /Users/chengpeng/VidsnapBenchmarks/agentic-video-20260812/manifests/smoke.jsonl \
  --output-dir /Users/chengpeng/VidsnapBenchmarks/agentic-video-20260812/results/smoke-short-20260821 \
  --seed 20260812
```

Do not pass the Model Studio key CSV; upload no video.

- [ ] **Step 3: Audit and stop**

Verify `short_video_only`, exactly 18 unique outcomes, six per variant,
Direct=`frames_2fps`, one model, matching hashes, complete usage, verifier and
failure fields, and no formal conclusion fields. Scan file names without
printing possible values:

```bash
if rg -l --hidden 'sk-(sp|ws)-[A-Za-z0-9._-]+' \
  /Users/chengpeng/VidsnapBenchmarks/agentic-video-20260812/results/smoke-short-20260821
then
  exit 1
fi
```

Report actual status and usage. Do not run formal and do not merge.
