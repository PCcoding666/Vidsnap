# Changelog

All notable changes to this project are documented here, in
Keep a Changelog style.

## [Unreleased]

## [0.1.0] - Unreleased

### Added

- Local-first video-agent harness: a bounded agent loop over one local video
  and one goal that calls only allow-listed tools (`transcribe_audio`,
  `sample_evidence`) under declared budgets, verifies drafts with the gates
  `claims_are_supported` and `required_sections_covered`, and records every
  run as an immutable RunBundle replayable as an offline HTML trace.
- Zero-key offline demo (`vidsnap demo`) replaying packaged synthetic
  fixtures — no key, account, network request, or model call.
- Plugin developer kit: the static `vidsnap.plugin-project/v1` contract,
  `vidsnap plugin validate` and `vidsnap plugin test` commands, and a
  complete example under `examples/plugin-template/`.
- Typed provider ports with application-injected `ProviderProtocol`, the
  reference Qwen provider (locked to `qwen3.8-max`, concurrency at most two,
  keys from environment variables only), and an offline `MockProvider`.
- Source-preserving interview recipe (`vidsnap recipe interview`) producing
  transcript, article, brief, and trace artifacts with editorial provenance.
- Offline benchmark trust evaluation (`vidsnap benchmark evaluate`) with
  deterministic, content-sealed reports; no live benchmark results claimed.
- Stateless localhost API adapter (`vidsnap serve`), the `vidsnap
  conformance` gate, and community files (CONTRIBUTING, CODE_OF_CONDUCT,
  SECURITY, MAINTAINERS, ROADMAP, issue forms).

### Changed

- Replaced the VidSnap SaaS stack with the local-first Video Harness core.
