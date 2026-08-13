# Agentic Video Harness Internal Benchmark Design

## Decision

This experiment tests one narrow claim: with the same `qwen3.8-max` model, can a
bounded acquisition planner choose audio transcription and/or visual sampling
with no more evidence cost while matching or improving the fixed Harness on
video multiple-choice QA?

The experiment is internal, non-commercial research. It is not a product claim
and does not change the default fixed Harness behavior.

## Registered comparison

Each case uses the same local video bytes, question, answer options, ground-truth
answer, available subtitle, and Qwen model across three variants:

- `direct`: extract the complete timeline at exactly 2 fps and submit that fixed
  frame sequence for every Direct case. Under the registered Qwen 3.8 Token Plan
  protocol, smoke and formal execution never attempt complete-video input.
- `fixed`: run both acquisition tools in the existing fixed order, skipping only
  a physically unavailable modality such as audio on a silent video.
- `agentic`: after deterministic probing, request one strict JSON `ToolPlan` from
  Qwen. The only selectable tools are `transcribe_audio` and `sample_evidence`.

Probe, answer synthesis, exact-answer parsing, verification, budgets, and
termination remain Harness-controlled. The planner cannot choose a model,
endpoint, prompt, URL, budget, verifier, or arbitrary tool. Existing callers
continue to receive `tool_mode="fixed"` by default.

All benchmark model requests use `qwen3.8-max`. Dataset subtitles are treated as
an available local evidence source, not as a model call. If transcription is
needed without a subtitle, the benchmark uses the same model's audio capability;
an unsupported audio request becomes an explicit blocked outcome rather than a
fallback to another model.

## Cases and phases

The smoke phase contains six cases, stratified across both datasets and covering
audio/no-audio plus visual, speech, and temporal requirements. It validates the
Hermes endpoint, all three execution paths, usage accounting, the fixed Direct
`frames_2fps` input mode, and leak controls. Its provider-reported usage is the
only basis for estimating the 54-case formal run.

The formal phase contains exactly 54 cases: 36 Video-MME and 18 MVBench. Sampling
is deterministic from a local manifest and is stratified by dataset, duration,
audio availability, and visual/speech/temporal requirement. A case records the
official dataset name and revision, research-use/license notice, official source
URL, case ID, local video SHA-256, question, options, answer, subtitle path when
available, duration stratum, audio flag, and expected acquisition tools.

Media, annotations, selected manifests, raw provider responses, RunBundles, and
reports live outside the repository. Nothing in those categories is committed.

## Security boundary

A launcher reads `QWEN_TOKEN_PLAN_CN_BASE_URL` and
`QWEN_TOKEN_PLAN_CN_API_KEY` from the local Hermes environment file, validates
that both are present, and injects them into only the benchmark subprocess as
`VIDSNAP_QWEN_BASE_URL` and `VIDSNAP_QWEN_API_KEY`. It never prints either value
and never writes them to source, events, manifests, reports, or git.

Provider clients keep credentials non-representable, redact request failures,
and report only model ID, usage counts, latency, input mode, and terminal status.
The runner rejects an output directory inside the repository. Live execution is
forbidden until all offline tests, type checks, packaging, conformance, and
secret scans pass.

## Metrics and conclusion rule

The first-order validation question is whether Fixed Harness reduces provider
evidence-input cost relative to Direct without a meaningful MCQ accuracy loss.
MCQ exact-match remains the quality metric; no LLM judge is used. The report
includes:

- paired Fixed-minus-Direct accuracy delta and deterministic 95% bootstrap CI;
- paired Agentic-minus-Fixed accuracy delta and deterministic 95% bootstrap CI;
- Direct, Fixed, and Agentic accuracy;
- per-variant and per-case provider input bytes and input tokens, including the
  median for each comparison;
- tool-selection precision, recall, and F1;
- missed-tool and invalid-tool rates;
- model calls, evidence frames, input bytes, input/output tokens, and latency;
- deterministic verifier-gate pass rate;
- per-stratum counts and outcomes.

Formal conclusions use two pre-registered gates:

- Fixed versus Direct is `FIXED_HARNESS_EFFICIENT_NONINFERIOR` only when the
  Fixed-minus-Direct 95% CI lower bound is at least `-0.056` and Fixed reduces
  the per-case median provider input bytes or input tokens by at least 25%.
- Agentic versus Fixed is `AGENTIC_HARNESS_EFFICIENT_NONINFERIOR` only when the
  Agentic-minus-Fixed 95% CI lower bound is at least `-0.056` and Agentic reduces
  the per-case median provider input bytes or input tokens by at least 25%.
- A comparison failing either gate is `NOT_YET_PROVEN`. `HARNESS_SUPERIOR` may
  appear only as an additional Agentic marker when its paired 95% CI lower bound
  versus Fixed is strictly greater than zero.

Any incomplete or verifier-failed formal path disables all positive markers.
The six-case smoke phase emits only `SMOKE_SUCCEEDED` or `SMOKE_FAILED`, measured
per-variant usage, and its 54-case usage projection. Its report does not emit
accuracy, paired intervals, tool-selection alignment, aggregate verifier rates,
efficiency decisions, superiority, or noninferiority conclusions. Per-outcome
terminal and verifier states remain available for smoke execution auditing.
Provider or dataset blockers remain execution failures and do not become
research claims.

## Failure handling

Malformed plans, unsupported modalities, request failures, missing media, hash
mismatches, invalid answers, budget exhaustion, and verifier failures produce
typed per-case outcomes. A failed case is never silently retried with another
model or broader tool surface. The formal command requires a successful smoke
report and records its cost projection before any formal request is made.
