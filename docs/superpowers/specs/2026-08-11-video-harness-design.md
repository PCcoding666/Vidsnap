# Video Harness Core Design

## Goal

Replace VidSnap's stateful FastAPI/React product with `vidsnap-harness`: a local-first Python package, CLI, SDK, and optional stateless FastAPI adapter for evidence-grounded video analysis. The system compares a bounded adaptive-evidence loop against a direct `qwen3.8-max` baseline that submits full video at 2 fps.

## Product Contract

VidSnap is a **video-agent runtime and evaluation harness**, not a hosted end-user workspace. Every execution has a bounded lifecycle, a structured run bundle, evidence-backed claims, a terminal state, and no user or cross-request state.

The public SDK is:

```python
result = await VideoHarness(config).run(
    source=VideoSource(path="lecture.mp4"),
    goal=VideoGoal(objective="Explain the argument with timestamps"),
    policy=HarnessPolicy(),
)
```

The package is published as `vidsnap-harness`, imports as `vidsnap`, and exposes the `vidsnap` CLI.

## Security and Provider Boundary

- The only model used by core runners is `qwen3.8-max`.
- Provider credentials are read only from `VIDSNAP_QWEN_API_KEY`, falling back to `QWEN_API_KEY` for local compatibility. They are never accepted from HTTP input, stored in a RunBundle, logged, or committed.
- The default compatible endpoint is `https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1`.
- Token Plan use is single-user, non-pooled, non-resold, low-concurrency. The default model concurrency is one; configuration cannot exceed two.
- FastAPI binds to `127.0.0.1` by default and is a thin in-process adapter, never a proxy for arbitrary prompts, models, or provider keys.
- If no local key is available, all deterministic and fake-provider tests run. Live benchmarks terminate as `BLOCKED_LIVE_BENCHMARK` rather than substituting fake success.

## Package Layout

```text
pyproject.toml
src/vidsnap/
  __init__.py
  harness.py
  cli.py
  config.py
  contracts/
  loop/
  skills/
  video/
  providers/
  api/
  benchmark/
  prompts/
tests/
benchmarks/
```

The core has no FastAPI, database, Redis, Celery, React, or cloud-storage dependency. FastAPI is an optional `server` extra. Provider-specific SDKs are optional extras. FFmpeg remains an external executable behind a port.

## Contracts

`contracts/` contains versioned Pydantic models and JSON schemas for:

- `VideoSource`, `VideoGoal`, `HarnessPolicy`, `VideoAnalysisResult`;
- `Evidence`, `EvidenceReference`, `Claim`, `VerificationReport`;
- `RunManifest`, `RunEvent`, `TerminalState`, and `RunBundle` metadata;
- `LoopSpec` with API version `vidsnap.loop/v1` and ID `grounded-video-understanding`.

Evidence is the common temporal representation for transcript segments, sampled frames, OCR, and deterministic media observations. Every factual claim must include one or more evidence IDs or time ranges. The verifier rejects out-of-bounds timestamps, missing evidence, invalid output schemas, unsupported claims, and absent required sections.

`LoopSpec` carries the approved allow-list (`probe_media`, `transcribe_audio`, `sample_evidence`, `inspect_evidence`, `synthesize_result`, `verify_claims`), budgets, verification gates, terminal states, and the run-bundle memory format. Its canonical JSON hash is embedded in prompts, manifests, and conformance results.

## Bounded Loop

The runtime state machine is:

```text
probe -> plan -> gather -> understand -> synthesize -> verify
                                                    |       |
                                                    |       +-> terminal
                                                    +-> repair -> gather
```

The loop may run at most three iterations and make at most twelve model calls. It terminates as `SUCCEEDED`, `PARTIAL`, `NO_OP`, `BLOCKED`, `EXHAUSTED`, or `FAILED`; exceptions, empty model output, or exhausted budget must never become `SUCCEEDED`.

The runtime persists only structured state transitions and decisions. It does not save hidden reasoning. Cancellation propagates through the SDK/API task and causes temporary source and RunBundle cleanup.

## Adaptive Evidence Strategy

`video/` supplies deterministic FFmpeg/ffprobe-based reconnaissance: duration, stream properties, scene candidates, motion/visual-change scores, perceptual deduplication, uniform coverage, and bounded frame extraction. It combines those candidates with ASR semantic anchors and OCR-change anchors when available.

Sampling policy is media-aware:

- static slides favor scene/OCR changes and have sparse visual sampling;
- lectures and interviews favor ASR anchors and sparse visual coverage;
- screen recordings favor UI-difference and before/after frames;
- high-motion windows are locally densified to 4-8 fps only when budget permits.

The verifier can request targeted re-sampling for a bounded time window, never a global restart. An evidence pack always contains timestamped IDs and provenance; it never claims to be a fixed-FPS sequence.

## Ports, Skills, and Prompts

Ports isolate FFmpeg, the speech recognizer, and the Qwen compatible-mode client. The initial speech port attempts `qwen3-asr-flash` Base64 chunk input; a local plugin fallback is supported, but no OSS-backed user persistence is restored.

Skills are executable protocol implementations rather than registry descriptions. Each has typed input/output models, an explicit name/version, and runs against a `RunContext`. The first built-ins are the six skills listed in `LoopSpec`.

Planner, Evidence, Synthesizer, Verifier, and Repair prompts are separate, versioned assets. Each defines an ID, semantic version, input/output schema, LoopSpec hash, and model configuration. Untrusted transcript/OCR/video text is supplied as data only; it cannot alter tool allow-lists, budgets, goals, or termination rules. Golden tests validate prompt metadata and response parsing without live model calls.

## RunBundle

CLI and SDK runs may write:

```text
run/
  manifest.json
  events.jsonl
  evidence.json
  result.json
  artifacts/
```

The manifest includes input SHA-256; code, prompt, LoopSpec, and policy hashes; redacted provider identity; model ID; model-call/token/frame/upload budgets; timings; verification reports; retries; and terminal reason. Secrets and raw authorization headers are forbidden. HTTP requests use a temporary bundle that is removed after the response stream completes or is cancelled.

## Interfaces

### CLI and SDK

The CLI exposes `analyze`, `serve`, `benchmark run`, `benchmark compare`, `conformance`, and `manifest`. `analyze` accepts a local file, goal, output directory, and bounded policy flags. URL/YouTube support, if added, is an optional `SourceAdapter` and may not introduce accounts or job state.

### Stateless HTTP Adapter

The optional FastAPI adapter provides:

- `POST /v1/analyze`;
- `POST /v1/analyze/stream`;
- `GET /v1/manifest`;
- `GET /health`.

Each request runs the harness inside its request lifecycle. There are no jobs, user identities, provider-key fields, histories, WebSocket notifications, or persisted artifacts. Streaming emits structured events from the current run only.

## Benchmark and Conformance

`benchmark/` implements:

- `DirectRunner`: full video at explicit 2 fps through `qwen3.8-max`;
- `HarnessRunner`: adaptive Evidence Pack plus bounded verification;
- ablations: Direct, Direct+ASR, Harness-Visual, Harness-Full.

Direct+ASR and Harness-Full receive the same transcript. All runners share task instructions, model/reasoning parameters, output schema, max output tokens, samples, repetitions, and randomized order. Metrics include official accuracy, Fact F1, Event Recall, temporal IoU/MAE, OCR CER, unsupported-claim rate, evidence precision/coverage, schema/trace completion, retry/terminal rates, tokens, model calls, frames, bytes, latency, cost per supported fact, and bootstrap 95% confidence intervals.

Open profiles describe user-provided local data adapters for the approved public datasets and synthetic adversarial fixtures. Datasets and restricted media are never committed. The benchmark emits `NOT_YET_SUPERIOR` when the published quality/efficiency thresholds are not met; it preserves all sample results.

Conformance validates contract schema, terminal transitions, timestamps, evidence references, prompt metadata, budget enforcement, and absence of deprecated runtime dependencies.

## Migration and Removal

The completed tree removes `frontend/`, authentication and user routes, account models, SMTP, PostgreSQL/migrations, SQLAlchemy, FastAPI-Users, OAuth, Redis, Celery, product job state, WebSocket notifications, OSS user persistence, Docker Compose SaaS services, frontend builds, and legacy deployment scripts. Valuable deterministic video code is migrated before the old tree is removed.

There is no compatibility HTTP job API. Existing consumers must migrate to CLI/SDK or the stateless `/v1/analyze` adapter. A migration document maps retained capabilities to new commands and records removed SaaS surface.

## Verification

The release gate requires offline tests, Ruff lint/format, type checking, build/wheel installation, CLI/API smoke tests, loop conformance, FFmpeg synthetic microbenchmark, metrics tests, provider failure/budget/cancellation tests, secret scan, `git diff --check`, and searches proving banned SaaS runtime references are gone. Live comparison only runs with a locally injected rotated key and is excluded from ordinary CI.
