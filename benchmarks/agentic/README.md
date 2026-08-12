# Agentic Video Harness Internal Benchmark

This protocol is for private, non-commercial internal research. It compares the
same `qwen3.8-max` model on Direct, Fixed Harness, and Agentic Harness video MCQ
paths. It is not a leaderboard submission or a product-performance claim.

## Dataset boundaries

- Video-MME: use the official
  [benchmark repository](https://github.com/MME-Benchmarks/Video-MME) and
  [LMMS-Eval dataset](https://huggingface.co/datasets/lmms-eval/Video-MME). The
  dataset notice limits use to academic research, prohibits commercial use and
  redistribution without approval, and leaves video copyright with the owners.
- MVBench: use the official
  [Ask-Anything repository](https://github.com/OpenGVLab/Ask-Anything) and
  [OpenGVLab dataset](https://huggingface.co/datasets/OpenGVLab/MVBench). The
  repository and dataset card identify MIT terms; source videos also retain the
  terms of their originating datasets. This experiment applies the stricter
  internal non-commercial boundary to all media.

The registered revisions for this run are:

- Video-MME: `ead1408f75b618502df9a1d8e0950166bf0a2a0b`
- MVBench annotations: `230a2d4fac8900333c61754641c7a13e069ac9c6`
- MVBench individual-video branch: `a776e554280b99b70f00cc3eacd69a65e0727efc`

Do not place media, annotations, selected manifests, subtitles, raw model
outputs, RunBundles, or reports in this repository. Use an absolute external
directory. Each manifest line is one `FormalCase` JSON object and records the
official source URL, revision, license notice, case ID, local absolute paths,
video SHA-256, MCQ fields, duration/audio/requirement strata, and expected tools.
`expected_tools` and `tool_annotation_reason` are independent, human-reviewed
pre-registration fields; they are never derived from `requirements` or changed
after outcomes are observed. The runner accepts only the exact smoke/formal
manifest SHA-256 values committed with this protocol, so a post-outcome label
edit cannot be used for another run without an explicit reviewed code change.

## Registered composition

The smoke manifest contains six cases across both datasets and covers short,
medium, and long duration; audio and no-audio; and visual, speech, and temporal
requirements. The formal manifest contains exactly 54 cases: 36 Video-MME and
18 MVBench, with the same strata represented. The MVBench slice contains six
cases each from Action Antonym, Action Sequence, and Action Prediction. It must
cover at least three task families with four cases per family.

Direct first attempts complete-video input. If the endpoint rejects that media
type during smoke, the runner records the compatibility limitation and uses the
complete timeline sampled at exactly 2 fps. The fallback is sent through the
provider's official `video` frame-list content shape, not as unrelated image
parts or sparse adaptive evidence. To reduce request-size pressure, every
Direct fallback frame uses the fixed transport profile: 96 pixels high, JPEG,
FFmpeg qscale 20, and provider `min_pixels=4096` so the endpoint does not upscale
the low-resolution frame list to its larger default minimum. This transport
resolution is reported as a limitation; no timeline frame is omitted. The
endpoint may still enforce a lower frame-count limit, which is a smoke-gate
failure rather than permission to sample sparsely.
The formal run reuses the smoke
mode. Fixed always invokes `transcribe_audio` then `sample_evidence`, skipping
only unavailable physical evidence. Agentic receives a strict JSON tool plan
and can select only those two acquisition tools. A supplied dataset subtitle is
local evidence and does not invoke another model; audio transcription without a
subtitle uses `qwen3.8-max`, never a separate ASR model.

## Reproduce

Install and complete the offline gate before allowing any live request:

```bash
python -m venv .venv
.venv/bin/python -m pip install -e '.[server,dev]'
.venv/bin/ruff format --check src tests scripts
.venv/bin/ruff check .
.venv/bin/mypy src
.venv/bin/python -m pytest -q
.venv/bin/python -m build
.venv/bin/vidsnap conformance
.venv/bin/python scripts/secret_scan.py
git diff --check
```

Validate local manifests without reading Hermes or making a provider call:

```bash
.venv/bin/python scripts/run_agentic_benchmark.py \
  --phase smoke --validate-only \
  --manifest /absolute/external/path/smoke.jsonl \
  --output-dir /absolute/external/path/smoke-results \
  --seed 20260812

.venv/bin/python scripts/run_agentic_benchmark.py \
  --phase formal --validate-only \
  --manifest /absolute/external/path/formal.jsonl \
  --output-dir /absolute/external/path/formal-validation \
  --seed 20260812
```

Run smoke through the non-printing Hermes launcher:

```bash
.venv/bin/python scripts/run_with_hermes_qwen.py -- \
  .venv/bin/python scripts/run_agentic_benchmark.py \
  --phase smoke \
  --manifest /absolute/external/path/smoke.jsonl \
  --output-dir /absolute/external/path/smoke-results \
  --seed 20260812
```

Review `smoke-results/report.json`. It contains measured usage and a 54-case
projection with no guessed currency conversion. Only a `SMOKE_SUCCEEDED` report
with the registered model, six-case manifest hash, complete per-variant usage,
and measured projection can unlock formal execution. The formal report records
the smoke report SHA-256 and carries its projection forward for auditability.
It also atomically writes `smoke-gate.json` in the external formal output
directory before provider initialization, so an interrupted run retains its
authorization provenance:

```bash
.venv/bin/python scripts/run_agentic_benchmark.py \
  --phase formal --validate-only \
  --manifest /absolute/external/path/formal.jsonl \
  --output-dir /absolute/external/path/formal-results \
  --smoke-report /absolute/external/path/smoke-results/report.json \
  --seed 20260812

.venv/bin/python scripts/run_with_hermes_qwen.py -- \
  .venv/bin/python scripts/run_agentic_benchmark.py \
  --phase formal \
  --manifest /absolute/external/path/formal.jsonl \
  --output-dir /absolute/external/path/formal-results \
  --smoke-report /absolute/external/path/smoke-results/report.json \
  --seed 20260812
```

`outcomes.jsonl` contains parsed answers, typed statuses, verifier gates, selected
tools, and measured usage, but no raw response. `report.json` contains paired
accuracy intervals, `pre_registered_tool_selection_alignment`, cost fields,
case provenance, task-family coverage, and the pre-registration manifest hash.
Smoke reports contain no research comparison: only gate/provenance metadata,
per-variant measured usage, and the measured 54-case usage projection. Accuracy,
paired intervals, tool-selection alignment, aggregate verifier rates,
efficiency decisions, superiority, and noninferiority remain formal-only.
Smoke `outcomes.jsonl` retains terminal and verifier states so the execution gate
can still be audited without turning the six cases into a research conclusion.

Formal reports apply the registered evidence-closure rules. Fixed is
`FIXED_HARNESS_EFFICIENT_NONINFERIOR` only when its paired accuracy-delta 95% CI
lower bound versus Direct is at least `-0.056` and its per-case median provider
input bytes or input tokens are at least 25% lower. Agentic uses the same rule
against Fixed and is marked `AGENTIC_HARNESS_EFFICIENT_NONINFERIOR` only when
both gates pass. A failed comparison is `NOT_YET_PROVEN`. The optional
`HARNESS_SUPERIOR` marker is allowed only when the Agentic-minus-Fixed CI lower
bound is strictly positive. Any incomplete or verifier-failed formal path
disables every positive marker.
