# VidSnap Harness

VidSnap Harness is a local-first, evidence-grounded framework for video-analysis agents. It replaces the former web SaaS with an installable Python package, CLI, SDK, stateless localhost API, reproducible RunBundles, and a fair Direct-vs-Harness benchmark.

## Install

    python -m pip install -e '.[server,dev]'

FFmpeg and ffprobe must be available on PATH. Live calls are optional: the framework reads only VIDSNAP_QWEN_API_KEY, falling back to QWEN_API_KEY; neither is accepted by the API or stored in a RunBundle.

## Use

    vidsnap analyze /absolute/path/video.mp4 --goal "Summarize the demonstration"
    vidsnap manifest run/<run-id>
    vidsnap serve

The SDK has the same stateless contract:

    result = await VideoHarness().run(
        VideoSource(path=Path("/absolute/path/video.mp4")),
        VideoGoal(objective="Summarize the demonstration"),
        HarnessPolicy(output_dir=Path("run/example")),
    )

qwen3.8-max is fixed as the main model. The Direct benchmark baseline always submits complete video at fps=2; the Harness uses timestamped adaptive evidence, verifier gates, and at most two targeted repair rounds.

## Current guarantees

- Plugin trust boundary: only allow-listed, dependency-checked plugins run, and runs can never mutate them.
- The Agentic policy is a true iterative loop: the model chooses only allowed tools and receives tool results; budgets and verifier gates still bound every run.
- Fixed remains the default policy and keeps transcribe_audio before sample_evidence (ASR before visual evidence).
- `vidsnap trace export <run-dir> -o out.html` renders one run offline; legacy result directories are summary-only and are never reconstructed.
- Infrastructure validation is not evidence that Harness beats Direct; that question requires actual benchmark evidence.
- These pages make no live result claims.

See [the migration guide](docs/migration-to-harness.md), [implementation state](docs/implementation/2026-08-11-video-harness-loop-state.md), [benchmark status](docs/benchmark-status.md), and the [default tools and data review checklist](docs/default-tools-and-data-review.md).

## Surfaces

- Python import: vidsnap
- CLI: vidsnap analyze, serve, benchmark run, benchmark compare, conformance, manifest
- API: GET /health, GET /v1/manifest, POST /v1/analyze, POST /v1/analyze/stream

The API binds to 127.0.0.1 by default, has no accounts/jobs/history/WebSockets, and deletes its temporary RunBundle when the request finishes or is cancelled.
