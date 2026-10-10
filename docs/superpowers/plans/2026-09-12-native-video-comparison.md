# Native Video Comparison Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans with Qoder as the sole code and test author. The lead agent independently checks each batch. User has already approved execution; do not request another design approval.

**Goal:** Compare source-faithful Chinese notes and short summaries from a bounded Qwen 3.8 Harness and Bailian native audiovisual input, retaining actual calls and evidence for human review.

**Architecture:** Add an opt-in experiment runner; keep the existing short subtitle pilot and all default behavior unchanged. Reuse the real HarnessKernel, registered tools, RunBundle and trace export. A separate typed native-video adapter is pinned before execution; local cached Whisper supplies the Harness transcription port and records its real execution.

**Tech Stack:** Existing Python 3.10 environment, HTTPX streaming, Pydantic, FFmpeg, installed local Whisper. No new services, database, uploads, or frontend application.

**Spec:** User-approved two-route experiment in the current conversation; local inventory and preflight live outside the repository. This plan contains no media, credentials or results.

## Global Constraints

- Work only in the current isolated codex/eval-studio-workbench checkout. Preserve preexisting dirty files.
- Qoder authors all source, tests and executable scripts. Lead agent writes only instructions, reviews, runs verification and approved experiments.
- Do not commit, push, merge, modify other PRs, or run formal benchmark cases.
- Harness remains qwen3.8-max at its existing Token Plan endpoint; no provider/model switch within a run.
- Native Direct is qwen3.5-omni-plus at the documented Beijing DashScope compatible endpoint; stream text with include_usage enabled. No automatic alternate model, endpoint, retry or credential fallback.
- Keys enter via the existing Hermes launcher, only in the child environment. Never read or echo credential files in development. Scrub credentials from any local ASR child environment.
- No raw provider requests, responses, headers, hidden reasoning, signed URLs or environment dumps in artifacts. Store validated task output, safe failure categories, allowlisted configuration and measured usage only.
- Native video has audio; Harness ASR is a separate local model. State this confound clearly; this is a solution comparison, not evidence of model-matched superiority. No LLM judge.
- Use original source hash, actual derived clip hash and duration, explicit offsets. No silent truncation or skipped tail. Provider-internal frames and unavailable tokens are unknown, never invented.
- All outputs and derived media must be outside every linked repository checkout. Refuse existing output directories to preserve earlier evidence.

## Batch 1: Native audiovisual request and local ASR ports

**Files:** Create focused provider modules under src/vidsnap/providers/ and their tests under tests/providers/. Do not repoint QwenProvider or repair the unrelated legacy ASR implementation.

**Interfaces:** Native port accepts an already prepared bounded local clip and a fixed task, returning validated notes, usage, fixed identity and safe failure metadata. Local transcription implements existing TranscriptionPort, with an observer for actual local execution metrics; no remote usage is manufactured.

- [x] Qoder writes failing offline tests only, using HTTPX MockTransport at the HTTP boundary and a fake process boundary for expensive local ASR.
- [x] Lead independently observes RED and checks behavior coverage: one streaming request, text-only output, correct model and video payload, no request for oversize data, no retry on HTTP/network/invalid-stream failure, safe errors, exact serialized request bytes, unknown missing usage, no reasoning persisted. Review requested additional tests for encoded size, text-only modalities, partial usage, stream completion and safe failure accounting before GREEN.
- [x] Local ASR tests cover independent valid media input, explicit cached model path, no model downloads, bounded subprocess timeout, restricted environment, no credential or subprocess output leakage, failure recorded as failure rather than empty successful text. Review additionally covers empty/truncated PCM, cancellation cleanup, attempted versus confirmed-started processes, and unknown exit status.
- [x] Qoder implements minimal ports; lead independently observes 51 focused tests passing and mypy passing for 79 source files. The full repository gates remain pending the experiment runner. Tests do not depend on real videos, credentials or network.

## Batch 2: Opt-in two-route runner and review artifact

**Files:** Create scripts/native_video_review.py and tests/test_native_video_review.py; focused helpers may live in a new experiment module. Existing scripts/podcast_review_pilot.py remains compatible.

**Review correction:** The existing trace reader drops unknown event prefixes. A separate Qoder-owned, additive change to src/vidsnap/trace/reader.py and a focused trace test must make actual local.asr events visible in the tools lane and allowlisted runtime configuration visible in the input lane. Do not fabricate remote calls or change existing event schemas/default behavior.

**Pre-live review controls:** This experiment uses a fail-fast agentic policy through the existing kernel: no automatic format retry or verifier repair, while the model still chooses the two registered tools and their sequence. Reject a visual sampling request above remaining frame headroom before extraction. The public default policies remain unchanged. Missing/invalid provider counters are unreported, not observed zero. Preserve usage already received before a native stream failure. Model completion, trace export completion and overall review completion are separate states; an export failure preserves the completed model outcome and stops further calls.

**Interfaces:** CLI accepts source clip, original source and offset, new external output directory, validate-only, and explicit local ASR executable/model paths. Runner pins both routes and applies a fixed common source-faithful Chinese notes task. The native route is run first; failure prevents the Harness route and all later videos.

- [ ] Qoder writes failing tests for validate-only doing no model/process inference or output writes, external-only paths (including linked worktrees/symlinks), immutable output directories, matching source/task provenance, failure-stop, unknown statistics and true local/remote call distinction.
- [ ] Tests exercise real HarnessKernel with deterministic provider/media doubles, rather than inventing event dictionaries as the whole integration test.
- [ ] Lead observes RED; Qoder implements the runner, reusing registered transcribe_audio/sample_evidence and their existing bounds. Explicit budget: at most 6 Harness remote calls, 4 tool calls, 24 evidence frames for the first clip. No arbitrary tools, prompts, endpoints or URLs exposed to the model.
- [ ] RunBundles contain actual environment allowlist (software versions, platform, model/provider identity, effective budgets, task hash, source/clip hashes), tool arguments/results, model evidence snapshots, local ASR execution, timings, verifier outcomes and terminal status.
- [ ] HTML/Markdown review gives both actual outputs and inspectable events; source timestamps distinguish source-backed citations from unverified native timestamps. Existing trace export should read the Harness bundle. Native hidden processing is explicitly not reconstructed.
- [ ] Report separately gives remote calls, local ASR calls and seconds, evidence frames, exact HTTP request bytes, provider tokens when present, wall latency, failures and structural verifier results. Do not equate schema acceptance with truth.
- [ ] Lead observes GREEN, reviews all new files and runs all eight repository gates. Scan new files as well as tracked files for credential exposure.

## Batch 3: Live evidence, then bounded full-video expansion

- [ ] Validate the prepared remobi clip (actual duration about 119 seconds) with the opt-in runner; output remains external.
- [ ] Run exactly one initial native request through the existing Hermes launcher with the approved workspace key; on failure preserve safe trace and stop, do not retry or process full videos.
- [ ] If native succeeds, run the bounded Harness route with real local ASR and Token Plan. Audit actual outputs, calls, hashes, measured usage, missing usage, failure state and credential scan before claiming compatibility success.
- [ ] Only after this pair succeeds, finalize a deterministic full-video chunk plan. Every clip must stay within the native inline size cap, retain audio, and map to the same original intervals for both routes. Test gap/tail coverage and model request budgets before full execution.
- [ ] Process full remobi before the other four videos. Preserve unfavorable outcomes. No automatic repeat to fill failures.
- [ ] Present real source-linked review artifacts and limitations; request user quality review before choosing new default tools or making open-source product claims.

## Verification

Use the existing isolated venv and PYTHONPATH=src. Run ruff format --check src tests scripts; ruff check .; mypy src; python -m pytest -q; python -m build with artifacts outside the repo; vidsnap conformance; python scripts/secret_scan.py; git diff --check. Tests passing prove implementation behavior, not live compatibility or output quality.

The user has already chosen continuous execution with batch review. Leave all changes uncommitted; do not present merge options.
