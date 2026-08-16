# Short-Video Smoke Benchmark Design

## Decision

Run one new six-case smoke benchmark under the existing Qwen 3.8 Token Plan
protocol. Direct always sends the complete timeline as a fixed 2 fps image
sequence. Complete-video input, frame chunking, model fallback, and the 54-case
formal experiment remain out of scope.

The smoke benchmark validates compatibility and measured usage only. It may
report only `SMOKE_SUCCEEDED` or `SMOKE_FAILED`; it must not emit superiority or
noninferiority conclusions.

## Pre-registered cases

The external manifest contains these six cases and no others:

| Dataset | Case ID | Source duration | Requirements | Expected tools | Annotation reason |
| --- | --- | ---: | --- | --- | --- |
| Video-MME | `069-1` | 73.463 s | speech | `transcribe_audio` | `speech-required` |
| Video-MME | `069-2` | 73.463 s | visual | `sample_evidence` | `visual-required` |
| Video-MME | `069-3` | 73.463 s | visual | `sample_evidence` | `visual-required` |
| MVBench | `action_antonym:6` | 4.833333 s | visual, temporal | `sample_evidence` | `visual-required` |
| MVBench | `action_antonym:18` | 4.000000 s | visual, temporal | `sample_evidence` | `visual-required` |
| MVBench | `action_antonym:19` | 5.333333 s | visual, temporal | `sample_evidence` | `visual-required` |

The Video-MME speech label is independently reviewed from the question and
available subtitle: the answer to `069-1` is stated in the narration. The tool
labels remain explicit manifest fields and are not derived by code from
`requirements`.

These case IDs do not overlap the registered 54-case formal selection. The
manifest remains outside git and records dataset revisions, license notices,
source URLs, local paths, case IDs, subtitles when available, and video SHA-256
values. Its final SHA-256 is registered in code before any live call.

## Validation changes

- Smoke composition changes from four Video-MME plus two MVBench cases to three
  plus three.
- Every smoke case must have the `short` duration stratum. Formal composition
  continues to require short, medium, and long strata.
- Smoke still must cover Video-MME and MVBench, audio and no-audio media, and
  speech, visual, and temporal requirements.
- Direct input remains `frames_2fps`. The longest registered source produces
  approximately 147 frames, matching the size of the previously successful
  Direct case.
- A short-video smoke report is marked `short_video_only` and cannot authorize
  the existing full-duration 54-case formal experiment.

## Execution and failure handling

Run all offline tests and manifest validation before loading credentials. After
the Draft PR CI passes, launch exactly one smoke run through the Hermes Qwen
launcher. Credentials exist only in that child process and must not appear in
terminal output, files, reports, git, request logs, or raw response logs.

The run writes to a new external output directory. It must produce exactly 18
outcomes: six each for Direct, Fixed, and Agentic, all using Qwen 3.8. Any
provider failure, missing outcome, verifier failure, model mismatch, provenance
mismatch, or credential-scan hit makes the result `SMOKE_FAILED` and stops the
experiment.

## Interpretation limits

This smoke set is deliberately narrow. Its three Video-MME questions share one
video, and its MVBench cases represent only the `Action Antonym` task family.
Even a successful result establishes only that the short-video evaluation paths
and accounting work under these inputs. It does not establish general video
understanding, long-video compatibility, Harness efficiency, noninferiority, or
superiority, and it does not unlock the 54-case formal experiment.
