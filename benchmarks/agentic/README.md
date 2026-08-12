# Agentic Video Harness Internal Benchmark

This protocol is for private, non-commercial internal research. It compares the
same `qwen3.8-max` model on Direct, Fixed Harness, and Agentic Harness video MCQ
paths. It is not a leaderboard submission or a product-performance claim.

## Dataset boundaries

- Video-MME: use the official
  [benchmark repository](https://github.com/MME-Benchmarks/Video-MME) and
  [LMMS-Lab dataset](https://huggingface.co/datasets/lmms-lab/Video-MME). The
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

## Registered composition

The smoke manifest contains six cases across both datasets and covers short,
medium, and long duration; audio and no-audio; and visual, speech, and temporal
requirements. The formal manifest contains exactly 54 cases: 36 Video-MME and
18 MVBench, with the same strata represented.

Direct first attempts complete-video input. If the endpoint rejects that media
type during smoke, the runner records the compatibility limitation and uses the
complete timeline sampled at exactly 2 fps. The formal run reuses the smoke
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
can unlock formal validation and execution:

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
accuracy intervals, tool metrics, cost fields, case provenance, and limitations.
The only positive label is `HARNESS_SUPERIOR`, and it is emitted only when the
Agentic-minus-Fixed paired 95% bootstrap CI lower bound is strictly above zero.
Every other measured result is `NOT_YET_SUPERIOR`.
