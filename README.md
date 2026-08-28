# VidSnap

Build auditable video agents with bounded tools, plugins, and replayable traces.

Video → Agent → Tools → Evidence → Verified Output → Replayable Trace

VidSnap is a local-first Python runtime for video-analysis agents. Point it at
one local video and one goal: it runs a bounded agent loop, checks the draft
output against sampled evidence, and records the whole run as a replayable
trace. Nothing leaves your machine except model calls to your configured
provider — no accounts, no job queue, no stored history.

## What VidSnap does

Point VidSnap at one local video and one goal. The core runtime plans a
bounded agent loop, calls only registered allow-listed tools
(`transcribe_audio`, `sample_evidence`) under declared budgets, verifies the
draft output against sampled evidence with the built-in gates
`claims_are_supported` and `required_sections_covered`, and records every
event in a RunBundle you can export and replay offline. Unsupported claims
fail the run instead of being returned.

## 30-second demo

No key, account, network request, model call, GPU, or private media needed:

    vidsnap demo

This replays packaged synthetic fixtures — an explicit replay, not live model
generation — and writes a real RunBundle, a verified result, and an offline
HTML trace to `vidsnap-demo/`.

## Quick Start

For a live run against your own local video you need Python >= 3.10, FFmpeg and
ffprobe on PATH, and a provider key in `VIDSNAP_QWEN_API_KEY` (fallback
`QWEN_API_KEY`):

    python -m pip install -e '.[server,dev]'
    vidsnap --help
    vidsnap conformance
    vidsnap analyze /absolute/path/video.mp4 --goal "Summarize the demonstration"
    vidsnap manifest run/<run-id>

## Why VidSnap exists

Most video tools compress footage and hide their work. VidSnap is
not another video summarizer: it grounds every output claim in sampled
evidence, fails runs the evidence cannot support, and records every step
in a RunBundle you can replay and audit offline.

## What is a trace

- Bounded tool calls. The Fixed policy (default) keeps a deterministic tool
  order (`transcribe_audio` before `sample_evidence`); the Agentic policy lets
  the model choose only allow-listed tools under enforced budgets.
- Verifier gates. The output contract `vidsnap.video-analysis/v1` requires
  sections and claims that pass the built-in gates `claims_are_supported` and
  `required_sections_covered` against the evidence actually collected.
  Unsupported claims fail the run instead of being returned.
- RunBundles. Each run writes a bundle recording the plan, every tool call with
  its payload fingerprint, the sampled evidence, verifier gates, repair rounds,
  and the final output.
- Offline replayable traces. Export a finished run as a fully offline HTML page
  and replay it step by step in a browser:

      vidsnap trace export RUN_DIR -o trace.html

## How to extend: Core, Plugin, Recipe

Five boundaries, each separately documented:

- Core — the bounded loop, policies, typed contracts, and verifier gates.
- Plugin — tool plugins load only from a validated, allow-listed registry that a
  run can never mutate. Only `transcribe_audio` and `sample_evidence` are
  model-visible by default; `vidsnap plugin validate .` and
  `vidsnap plugin test .` check a plugin statically and contractually. Start
  from the [Plugin template](examples/plugin-template/README.md).
- Recipe — packaged task configurations on top of Core. The source-preserving
  [Interview recipe](src/vidsnap/recipes/) ships in the package.
- Provider — every model call goes through a typed provider port; the loop,
  verifier, and tools never see a raw client, endpoint, or credential. Built-in
  providers are `QwenProvider` and the offline `MockProvider`. See the
  [Provider guide](docs/providers.md).
- Trace — the RunBundle event log and its offline HTML export.

## Current guarantees

- trust boundary
- the model chooses only allowed tools and receives tool results
- transcribe_audio before sample_evidence
- summary-only and are never reconstructed
- Infrastructure validation is not evidence that Harness beats Direct
- no live result claims

## Benchmark evidence

The `vidsnap benchmark` infrastructure exists, but there are no published
live benchmark results. Status: benchmark infrastructure ready; current results are not statistically meaningful.

Evaluate recorded results fully offline — no key, no provider, no network:

    vidsnap benchmark evaluate INPUT_JSON --output REPORT_JSON

The input envelope uses exactly the strict top-level keys `manifest` and
`outcomes`; the report is deterministic and carries a stable `report_sha256`.
The formulas and fairness rules are specified in
[benchmark methodology](docs/benchmark-methodology.md). No superiority,
quality, latency, or cost claims are published.

## CLI and API surfaces

- CLI: `vidsnap demo`, `analyze`, `manifest`, `serve`, `conformance`,
  `trace export`, `benchmark run`, `benchmark compare`, `plugin validate`,
  `plugin test`.
- Python import: `vidsnap`; `VideoHarness().run(...)` exposes the same
  stateless contract as the API.
- Localhost API: `GET /health`, `GET /v1/manifest`, `POST /v1/analyze`,
  `POST /v1/analyze/stream`.

## Honest limitations

- The built-in provider is pinned to one model (qwen3.8-max) with concurrency
  capped at two. Keys come only from local environment variables, are never
  accepted by the API, and are never stored in a RunBundle.
- The API binds to 127.0.0.1 with no accounts, jobs, history, or WebSockets,
  and deletes its temporary RunBundle when the request finishes or is
  cancelled.
- Plugins and providers are trusted code, not sandboxes: they run with your
  process's privileges, and allow-lists express your selection, not a security
  boundary. Only install code you trust.
- Speech recognition is a separate port; without a recognizer, transcription is
  skipped for the run.
- No live benchmark has been published. The `vidsnap benchmark` commands exist,
  and without a configured key they truthfully report
  `BLOCKED_LIVE_BENCHMARK`. See [benchmark status](docs/benchmark-status.md).
- The project is early: typed public contracts should be treated as breaking
  when they change. Check the [Roadmap](ROADMAP.md) for direction and
  non-goals.

## Contributing

- [Contributing](CONTRIBUTING.md)
- [Roadmap](ROADMAP.md)
- [Security](SECURITY.md)
- [Maintainers](MAINTAINERS.md)
- [Documentation](docs/README.md)
