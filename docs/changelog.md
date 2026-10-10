# Changelog

All notable changes to this project are documented here, in
Keep a Changelog style.

## [Unreleased]

### Added

- `vidsnap eval`: task evaluation of "harness + model" against models that read
  the video natively, on four eval sets (`benchmarks/eval/`): long video to an
  illustrated article, explainer storyboard, podcast/clip review, and teacher
  recording to wrong questions, notes and a teaching-video storyboard. Every
  evaluated item is an ordinary traced RunBundle (new `NativePolicy` for the
  native path); deterministic machine graders, per-stage attribution (ASR,
  sampling, synthesis), oracle ablations, a Markdown report, and a blind A/B
  human review page. Live systems require a price table and a spending cap.
  See [Task evaluation](eval.md). No released behaviour or trace semantics
  change.

### Changed

- Speech recognition now sends compressed audio instead of Base64 WAV. The
  video port gains `extract_audio_segments`, which cuts the audio into
  standalone 16 kHz mono MP3 files at 48 kbps (ADTS AAC if FFmpeg has no LAME
  encoder), at most 240 s each, so duration rather than bytes is the limit
  (`qwen3-asr-flash` takes 5 minutes and 10 MB per request). Each file is one
  request with its real MIME type (`audio/mpeg`) and the transcripts are
  joined with a newline, as before. This is about 5.3 times fewer bytes: 360 KB
  per minute instead of 1.9 MB, or about 480 KB against 2.6 MB once Base64. A
  192 s clip went from 8.2 MB to 1.5 MB, and over an uplink of about 9 KB/s
  it now completes where the WAV upload ended in `write_timeout` (one live
  `vidsnap eval` run, 74.6 s in the ASR stage). `FFmpegPort` gains the method,
  `vidsnap.video.AudioSegment` and `vidsnap.video.audio` hold the types and
  constants, and a final segment under 1 s is merged into the previous one.
  A recognizer is sent compressed audio only if it sets
  `accepts_compressed_audio = True` (`QwenAsrRecognizer` and the evaluation
  recognizer do, with a `local_fallback` only if the fallback does too); all
  others still get one mono WAV file, so custom recognizers and the benchmark
  transcriber are unchanged. A custom `FFmpegPort` without the method keeps
  the WAV path. `Base64AudioChunker.encode` takes a `mime_type` (default
  `audio/wav`): only WAV is cut by size, and compressed audio is sent whole or
  refused above 10 MB of Base64. The `transcribe_audio` phase event gains
  `audio_format`, `audio_segments`, `audio_bytes` and `audio_segment_seconds`
  payload keys; `asr_upload_bytes` in `vidsnap eval` counts MP3 and AAC
  artifacts. A kept bundle now holds MP3 segments (about 22 MB per hour)
  instead of a WAV (about 115 MB per hour) when the built-in recognizer is
  used.
- Speech recognition now calls the public DashScope compatible-mode endpoint
  (`https://dashscope.aliyuncs.com/compatible-mode/v1`) instead of Token Plan,
  which serves text models only, so every run with audio failed at ASR with
  `model_not_found`. The endpoint is a fixed constant
  (`vidsnap.config.DASHSCOPE_ASR_BASE_URL`), not an argument or an environment
  variable, and `QWEN_ASR_IDENTITY.base_url` reports it. The text model
  (`qwen3.8-max`) stays on Token Plan, and `HarnessConfig.base_url` still
  accepts only the Token Plan URL. **Action needed:** the ASR key is read from
  `VIDSNAP_ASR_API_KEY`, falling back to `VIDSNAP_QWEN_API_KEY` and then
  `QWEN_API_KEY`. Do not assume a Token Plan key is accepted by the public
  endpoint; set `VIDSNAP_ASR_API_KEY` to a public DashScope key.
  `HarnessConfig` gains `asr_api_key` and `resolved_asr_api_key`. The audio
  of a run now goes to a second endpoint, which has its own data terms.
- `Base64AudioChunker`'s default `chunk_bytes` is now 7,000,000 bytes instead
  of 8 MiB. Base64 of 8 MiB is about 11.2 MB, over the 10 MB request limit the
  provider documents for `qwen3-asr-flash`; 7,000,000 bytes encode to about
  9.3 MB and are about 218 s of 16 kHz mono 16-bit audio. Audio between the two
  sizes that used to go out as one request is now split in two.
- A WAV file larger than the chunk limit that cannot be split (a format other
  than PCM) and any other oversized audio now raise `ProviderError`; they used
  to be sent as undecodable fragments.

### Fixed

- The ASR client had no explicit timeout, so httpx's 5 s default applied and
  large Base64 request bodies failed with `write_timeout`. It now uses
  `HarnessConfig.request_timeout_seconds` (120 s by default), like the text
  client. `QwenAsrRecognizer` takes a new `timeout_seconds` argument.
- `Base64AudioChunker` cut audio every 8 MiB, so every chunk after the first
  had no WAV header (audio longer than about 262 s at 16 kHz mono 16-bit). A
  PCM WAV file larger than the limit is now cut on sample-frame boundaries and
  each chunk gets its own header with the input's sample rate, channels and
  bit depth. Audio that fits is still sent unchanged.

## [0.1.1] - 2026-10-08

Every run now leaves a trace that can be evaluated afterwards. All trace
changes are additive payload keys within `vidsnap.trace/v1`; bundles written
by 0.1.0 and the packaged demo still load, replay, and export. See
[Trace format and run index](trace-format.md).

### Added

- Run header: `run.started` records `vidsnap.run-header/v1` with the goal and
  required sections as given, the input's SHA-256 and byte size, the provider
  and speech-recognizer id and model when known, the recipe id and version,
  the resolved plugin versions, and the package version. The probed input
  duration is repeated on the terminal run event as `input_duration_seconds`.
- Tool calls: `tool.call.started` records the validated arguments, after the
  existing key-based redaction, and the call fingerprint the kernel already
  used to reject duplicate calls. The README's fingerprint statement is now
  true.
- Structured failures: failed and blocked `model.request` events record
  `payload.failure` in the `vidsnap.provider-failure/v1` shape (category, HTTP
  status, request bytes, and token counts only when reported); the terminal
  run event records `payload.failure` in the `vidsnap.run-failure/v1` shape,
  or `null`. `ProviderFailure` and `FailureCategory` are exported from
  `vidsnap.contracts`, and `ProviderError` accepts an optional `failure=`.
- Run index: `vidsnap analyze` and `vidsnap recipe interview` append one
  `vidsnap.run-index/v1` line per finished run to `index.jsonl` under
  `--runs-root` (`VIDSNAP_RUNS_ROOT`, default `./run`). `vidsnap runs list`
  prints it as a table.
- Human review records: `vidsnap runs review RUN` appends edit minutes,
  published or not, factual errors found, images replaced, and a note.
- Cost: `--price-table` (`VIDSNAP_PRICE_TABLE`) accepts your own
  `vidsnap.price-table/v1` file. Without one, cost is `null`; with one, a
  run's model requests are priced only when there was at least one, its model
  is listed, and every request reported its usage. `complete` is `false` when
  speech recognition ran, because it is not priced. VidSnap ships no prices.
- `InterviewRecipeRunner.run(..., run_dir=...)` keeps the RunBundle at
  `run_dir` whatever the outcome and reports it as `run_path`.

### Changed

- `vidsnap recipe interview` keeps its RunBundle under the runs root
  (`./run/<uuid>/` by default) on success and failure, and adds `run_path` to
  its JSON output. A kept bundle holds a full-length 16 kHz mono WAV of the
  video's audio (about 115 MB per hour), the sampled frame JPEGs, the
  transcripts, the structured result, and the event ledger, as `analyze`
  bundles already did. The folder is yours to delete; move the runs root with
  `--runs-root` or `VIDSNAP_RUNS_ROOT`, or pass `--no-keep-bundle` to restore
  the 0.1.0 behavior of a temporary bundle removed when the command ends (no
  index line is written then). The output directory still holds exactly the
  four recipe artifacts. Library callers that pass no `run_dir` keep the
  temporary bundle.
- `vidsnap recipe interview` refuses a non-empty `--output-dir`, and both
  `recipe interview` and `analyze` without `--output-dir` refuse a runs root
  they cannot write (exit 2), before any model call.
- `vidsnap analyze` without `--output-dir` writes its bundle under the runs
  root; with the default root this is the same `./run/<id>` as before.
- The Qwen client raises `ProviderError` for HTTP failures and non-JSON
  response bodies in analysis and tool planning, as agent decisions already
  did. Such runs still end `FAILED`, now with the reason `provider error`
  instead of `unexpected kernel error`.
- Rejected tool calls raise `ToolArgumentError` and wall-clock exhaustion
  raises `WallClockExceeded`; both subclass the exception types raised before
  (`ValueError` and `BudgetExceeded`), and messages are unchanged.
- RunBundle redaction keeps an unreported usage counter as `null` instead of
  masking it.
- A failed model request whose request size was measured now carries `usage`
  (`model_calls: 1`, `input_bytes`, `provider_reported: false`) instead of
  `null`, so usage totals in traces now count failed attempts.
- `vidsnap analyze --output-dir X` writes its bundle to `X` as before, but
  also appends to `./run/index.jsonl` in the working directory unless
  `--runs-root` or `VIDSNAP_RUNS_ROOT` points elsewhere.
- The recipe's `trace.html`, and any exported trace, now shows the input's
  SHA-256 and byte size, the goal, and every tool call's arguments and
  fingerprint. Review it before publishing it.
- Export 0.1.1 bundles with VidSnap 0.1.1 or later: the 0.1.0 exporter does
  not drop the run header's provider identity, so its HTML would show the
  provider id and model (never the URL or key).
- Exported HTML traces drop the run header's `provider` and
  `speech_recognizer` keys, keeping the guarantee that a projected trace never
  carries provider identity.

## [0.1.0] - 2026-10-05

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
