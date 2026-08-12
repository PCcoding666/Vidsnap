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

- `direct`: submit the complete video when the endpoint accepts it. If the smoke
  probe shows that complete-video input is unsupported, extract the complete
  timeline at exactly 2 fps and use that frame sequence for every Direct case.
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
Hermes endpoint, all three execution paths, usage accounting, Direct input mode,
and leak controls. Its provider-reported usage is the only basis for estimating
the 54-case formal run.

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

The primary metric is MCQ exact-match. No LLM judge is used. The report includes:

- paired Agentic-minus-Fixed accuracy delta and deterministic 95% bootstrap CI;
- Direct, Fixed, and Agentic accuracy;
- tool-selection precision, recall, and F1;
- missed-tool and invalid-tool rates;
- model calls, evidence frames, input bytes, input/output tokens, and latency;
- deterministic verifier-gate pass rate;
- per-stratum counts and outcomes.

`HARNESS_SUPERIOR` is allowed only when the Agentic-minus-Fixed 95% CI lower
bound is greater than zero. Every other measured outcome is
`NOT_YET_SUPERIOR`. Provider or dataset blockers are reported separately and do
not become a superiority claim.

## Failure handling

Malformed plans, unsupported modalities, request failures, missing media, hash
mismatches, invalid answers, budget exhaustion, and verifier failures produce
typed per-case outcomes. A failed case is never silently retried with another
model or broader tool surface. The formal command requires a successful smoke
report and records its cost projection before any formal request is made.
