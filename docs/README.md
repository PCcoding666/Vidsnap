# VidSnap Harness Documentation

- [Migration from the legacy SaaS](migration-to-harness.md)
- [Default tools and data review checklist](default-tools-and-data-review.md)
- [Implementation loop state](implementation/2026-08-11-video-harness-loop-state.md)
- [Harness architecture](superpowers/specs/2026-08-11-video-harness-design.md)
- [Benchmark status](benchmark-status.md)

## Current guarantees

These statements hold across every public page in this repository:

- Plugin trust boundary: only allow-listed, dependency-checked plugins run, and runs can never mutate them.
- The Agentic policy is a true iterative loop: the model chooses only allowed tools and receives tool results; budgets and verifier gates still bound every run.
- Fixed remains the default policy and keeps transcribe_audio before sample_evidence (ASR before visual evidence).
- Legacy result directories exported by `vidsnap trace export` are summary-only and are never reconstructed.
- Infrastructure validation is not evidence that Harness beats Direct; that question requires actual benchmark evidence.
- These pages make no live result claims.
