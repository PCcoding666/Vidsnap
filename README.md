# VidSnap

Build auditable video agents with bounded tools, plugins, and replayable traces.

Video → Agent → Tools → Evidence → Verified Output → Replayable Trace

VidSnap is a local-first Python runtime for video-analysis agents. It runs bounded
agent loops over local video files, verifies output against sampled evidence, and
records a replayable trace of every run.

## What VidSnap does

VidSnap takes one local video plus one goal and produces an auditable agent run:

- Fixed policy uses a deterministic bounded tool order (`transcribe_audio` before
  `sample_evidence`); Agentic policy lets the model select only from the allow-listed
  tools under enforced budgets.
- Draft output must pass verifier gates against the evidence actually collected before it is returned.
- The run is written to a RunBundle and exportable as an offline HTML trace you can replay step by step.

Nothing leaves your machine except model calls to your configured provider. There are no accounts, no job queue, and no stored history.

## 30-second demo

Replay a packaged synthetic run with no key, account, network request, model call, GPU, or private media:

    vidsnap demo

The command writes a real RunBundle, verified result, and offline HTML trace to vidsnap-demo/. It is an explicit replay of public synthetic fixtures, not live model generation. Use vidsnap analyze for a credentialed live run against your own local video.

## Quick Start

Live analyze runs require Python >= 3.10, FFmpeg and ffprobe on PATH, and a local
provider key in `VIDSNAP_QWEN_API_KEY` (fallback `QWEN_API_KEY`).

    python -m pip install -e '.[server,dev]'
    vidsnap --help
    vidsnap conformance

A real run:

    vidsnap analyze /absolute/path/video.mp4 --goal "Summarize the demonstration"
    vidsnap manifest run/<run-id>

## What is a trace

Every run records a replayable trace: the plan, each tool call with its payload
fingerprint, the sampled evidence, verifier gates, repair rounds, and the final
output. Export one finished run as a fully offline HTML page:

    vidsnap trace export RUN_DIR -o trace.html

Open `trace.html` in a browser. Legacy result directories are summary-only and are
never reconstructed.

## Why VidSnap exists

Video-agent systems usually fail invisibly: hidden tool calls, unverified summaries,
runs you cannot reproduce. VidSnap exists to make those things visible and bounded —
hard budgets, verifier gates, and a trace you can replay offline after the fact.

## Why this is not another video summarizer

A conventional summarizer returns text and usually discards the process. VidSnap returns verified
output plus the chain behind it:

- Claims must be supported by sampled evidence, or the run fails instead of answering.
- The model can only choose allow-listed tools, within bounded order and budget.
- The run is replayable from its trace, not merely re-runnable.

## How to extend: Core, Plugin, Recipe

VidSnap has three boundaries, and today they are not equally open. Be clear about
what exists now:

- Core — public and working: bounded loop, policies, contracts, verifier gates, trace.
- Plugin — internal and allow-listed today: only `transcribe_audio` and
  `sample_evidence` are model-visible by default. An external plugin developer
  experience is coming later.
- Recipe — does not exist yet: the recipe layer comes later. The only task today is
  the built-in video-analysis adapter.

## Evidence grounding

The output contract `vidsnap.video-analysis/v1` requires sections and claims that
pass verifier gates against collected evidence. The built-in gates are
`claims_are_supported` and `required_sections_covered`; unsupported claims fail the
run rather than being returned.

## Replayable trace

Run events (plan, tool calls, evidence, verification, repair) are recorded into a
RunBundle and exported offline as HTML with `vidsnap trace export`. Trace template
assets ship inside the wheel.

## Plugin boundary

Only allow-listed, dependency-checked plugins run, and a run can never mutate the
allow-list. Built-in model-visible tools today: `transcribe_audio` and
`sample_evidence`. There is no public plugin SDK yet — reading the source is the only
extension path today, and the plugin developer experience is planned for a later phase.

## Recipe boundary

There is no recipe layer today: no recipe concept, registry, CLI surface, or
documentation. Recipes are planned as packaged task configurations on top of Core
and will arrive in a later phase.

## Bounded safety

- Fixed policy is the default and keeps `transcribe_audio` before `sample_evidence`
  (ASR before visual evidence).
- The Agentic policy is a true iterative loop: the model chooses only allowed tools
  and receives their results; budgets and verifier gates still bound every run.
- The main model is fixed to qwen3.8-max, concurrency is capped at two, and keys come
  only from local environment variables; they are never accepted by the API and never
  stored in a RunBundle.
- The API binds to 127.0.0.1, has no accounts/jobs/history/WebSockets, and deletes its
  temporary RunBundle when the request finishes or is cancelled.

## Current guarantees

- Plugin trust boundary: only allow-listed, dependency-checked plugins run, and runs can never mutate them.
- The Agentic policy is a true iterative loop: the model chooses only allowed tools and receives tool results; budgets and verifier gates still bound every run.
- Fixed remains the default policy and keeps transcribe_audio before sample_evidence (ASR before visual evidence).
- Legacy result directories are summary-only and are never reconstructed.
- Infrastructure validation is not evidence that Harness beats Direct; that question requires actual benchmark evidence.
- These pages make no live result claims.

## Benchmark evidence

The repo ships `vidsnap benchmark run` and `vidsnap benchmark compare`, but no live
benchmark has been published. Without a configured key the commands honestly report
`BLOCKED_LIVE_BENCHMARK`. Infrastructure validation is not evidence that Harness beats
Direct; that question requires actual benchmark evidence, and these pages make no live
result claims. See [benchmark status](docs/benchmark-status.md).

## Surfaces

- Python import: `vidsnap`; the SDK exposes the same stateless contract as the API
  (`VideoHarness().run(...)`).
- CLI: `vidsnap analyze`, `manifest`, `serve`, `conformance`, `benchmark run`,
  `benchmark compare`, `trace export`.
- API (localhost): `GET /health`, `GET /v1/manifest`, `POST /v1/analyze`,
  `POST /v1/analyze/stream`.

## Contributing

- [Contributing guide](CONTRIBUTING.md)
- [Documentation landing](docs/README.md)
- [Migration from the legacy SaaS](docs/migration-to-harness.md)
- [Default tools and data review checklist](docs/default-tools-and-data-review.md)
- [Implementation state](docs/implementation/2026-08-11-video-harness-loop-state.md)
- [Harness architecture](docs/superpowers/specs/2026-08-11-video-harness-design.md)
