# VidSnap Documentation

Build auditable video agents with bounded tools, plugins, and replayable traces.

Topics: video-ai, agent-harness, multimodal, ai-agents, video-analysis, llm-evaluation, python, observability, agent-runtime.

## Start here

- [Quick Start](../README.md#quick-start) — install, `vidsnap --help`, `vidsnap conformance`, and a first real run.
- [Traces and replay](../README.md#what-is-a-trace) — export a finished run and replay it offline with `vidsnap trace export`.
- [Harness architecture](superpowers/specs/2026-08-11-video-harness-design.md) — the bounded-loop design: run lifecycle, RunBundle, and verifier gates.

## Extend

- [Plugin and recipe extension](../README.md#how-to-extend-core-plugin-recipe) — the extension boundaries in the main README.
- [Plugin template](../examples/plugin-template/README.md) — build and test a tool plugin from a working example.
- [Interview recipe](../src/vidsnap/recipes/) — source-preserving recipe that keeps original media references intact end to end.
- [Provider guide](providers.md) — typed provider ports, the fixed model, and local-only key handling.

## Project

- [Contributing](../CONTRIBUTING.md) — setup, quality gates, and how to submit changes.
- [Contributing and project links](../README.md#contributing) — the README's contributing section.
- [Roadmap](../ROADMAP.md) — Now / Next / Later priorities and explicit non-goals.
- [Security](../SECURITY.md) — supported versions and private vulnerability reporting.
- [Good first issues](good-first-issues.md) — scoped starter tasks with acceptance criteria.

## Reference

- [Migration from the legacy SaaS](migration-to-harness.md) — what was removed and how bounded runs work now.
- [Default tools and data review](default-tools-and-data-review.md) — what the built-in tools read, their budgets, and what leaves the machine.
- [Benchmark status](benchmark-status.md) — no live comparison is published; infrastructure validation is not proof that Harness beats Direct, and these pages make no performance claims.
- [Benchmark methodology](benchmark-methodology.md) — the offline trust metrics, fairness registration rules, and the deterministic `vidsnap benchmark evaluate` command; no results are published.
- [Benchmark evidence](../README.md#benchmark-evidence) — the benchmark infrastructure exists, but no live benchmark results are published.
- [Release checklist](release-checklist.md) — the reusable release steps and the currently verified release evidence.

## Current behavior

- trust boundary
- the model chooses only allowed tools and receives tool results
- transcribe_audio before sample_evidence
- summary-only and are never reconstructed
- Infrastructure validation is not evidence that Harness beats Direct
- no live result claims
