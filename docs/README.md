# VidSnap Documentation

Build auditable video agents with bounded tools, plugins, and replayable traces.

## Start here

- [Quick Start](../README.md#quick-start) — install, `vidsnap --help`, `vidsnap conformance`, and a first real run.
- [What is a trace](../README.md#what-is-a-trace) — replay a run offline with `vidsnap trace export`.
- [How to extend](../README.md#how-to-extend-core-plugin-recipe) — what Core, Plugin, and Recipe mean today.

## Reference

- [Plugin boundary](../README.md#plugin-boundary) — internal and allow-listed; only `transcribe_audio` and `sample_evidence` are model-visible by default. No public plugin SDK yet.
- [Recipe boundary](../README.md#recipe-boundary) — no recipe layer exists yet; it comes in a later phase.
- [Benchmark evidence](../README.md#benchmark-evidence) — no live benchmark has been published; these pages make no performance claims.

## Project

- [Contributing](../README.md#contributing) and the main [README](../README.md).

## Detailed docs

- [Migration from the legacy SaaS](migration-to-harness.md)
- [Default tools and data review checklist](default-tools-and-data-review.md)
- [Providers](providers.md)
- [Implementation loop state](implementation/2026-08-11-video-harness-loop-state.md)
- [Harness architecture](superpowers/specs/2026-08-11-video-harness-design.md)
- [Benchmark status](benchmark-status.md)

## Current guarantees

- Plugin trust boundary: only allow-listed, dependency-checked plugins run, and runs can never mutate them.
- The Agentic policy is a true iterative loop: the model chooses only allowed tools and receives tool results; budgets and verifier gates still bound every run.
- Fixed remains the default policy and keeps transcribe_audio before sample_evidence (ASR before visual evidence).
- Legacy result directories are summary-only and are never reconstructed.
- Infrastructure validation is not evidence that Harness beats Direct; that question requires actual benchmark evidence.
- These pages make no live result claims.

## Discoverability

Topics: video-ai, agent-harness, multimodal, ai-agents, video-analysis,
llm-evaluation, python, observability, agent-runtime.
