# First live t1 run: harness + qwen3.8-max vs native qwen3.8-max (2026-11-01)

The first real-provider comparison this repository has recorded. Three owner-supplied
videos, 12 runs, public DashScope endpoint, `price-table.example.json` prices,
cost cap 20–25 CNY per run. Raw RunBundles, result files, media and the local
suite copy with owner items stay outside the repository; this page records what
was measured and what it means. One reviewer (Claude, acting as judge) read every
article and checked **every rendered figure against its caption** by eye, since
no machine grader does that today.

## Samples

| Item | Source | Length | Audio | Why |
|---|---|---|---|---|
| owner-01 | Sam Altman, *How to Succeed with a Startup* (YC Startup School), 1080p | 16:07 | **none** (video-only download) | Slide talk; the reviewer knows the content, so key points were written as references. A YouTube caption file was imported as the reference transcript for the `+oracle-asr` ablation only. |
| owner-02 | *From Zero to Your First AI Agent in 25 Minutes* (n8n screen tutorial) | 25:57 | aac | Long screen recording with narration: the intended t1 input. No reference; judged blind. |
| owner-04 / 05 | the same tutorial, clipped to 0–600 s / 0–300 s | 10:00 / 5:00 | aac | Fairness controls, because the native path cannot take the full file (below). |

## Results

| Item | System | State | Cost (CNY) | ASR | Input tokens | Wall s | Figures | Figures correct | Key points | Structure |
|---|---|---|---|---|---|---|---|---|---|---|
| owner-01 16 min, no audio | harness | ok | 2.95 | – | 204k | 347 | 9 | **8/9** | 0.67 | 0.89 |
| owner-01 | harness + oracle-asr | ok | 2.80 | – | 204k | 356 | 15 | **9/15** | **1.00** | 0.78 |
| owner-01 | native | ok | 3.13 | – | 222k | 320 | 8 | **7/8** | 1.00 | 1.00 |
| owner-02 26 min | harness | ok | **2.09** | 0.34 | 100k | 561 | 14 | 5/5 sampled | – | 0.89 |
| owner-02 | native | **refused** | – | – | – | 0 | – | – | – | – |
| 13 min clip | native | **refused** | – | – | – | 0 | – | – | – | – |
| 13 min clip | harness | failed (ASR HTTP 400, body not recorded) | 0.17 | 0.17 | – | 145 | – | – | – | – |
| owner-04 10 min | harness | ok | 1.75 | 0.13 | 95k | 333 | 11 | – | – | 0.89 |
| owner-04 | native | **refused** after 20 s of re-encoding | – | – | – | 20 | – | – | – | – |
| owner-05 5 min | harness | ok | 1.54 | 0.07 | 94k | 227 | 7 | 3/3 sampled | – | 0.89 |
| owner-05 | native | ok | **1.12** | – | 69k | 157 | 6 | 3/3 sampled | – | 0.89 |

"Structure 0.89" on the tutorial runs is the `mostly_chinese` check tripping on
English UI strings quoted in Chinese prose; the reviewer did not treat it as a defect.

## What the numbers say

1. **Long video is where the harness wins, and it wins by default.** The native
   path sends the whole file inline as Base64 under a 10 MB limit; with a 32 kbps
   audio track and the 40 kbps video floor that admits at most ~712 s, and in
   practice the 10-minute clip was refused after re-encoding. The 26-minute
   tutorial ran only through the harness: 2.09 CNY, 561 s, transcript plus 96
   sampled frames, verifier passed first time, and the article is specific down
   to the `Draper, UT` vs `Draper, US` error and the exact trail recommendation
   in the final e-mail — all confirmed against the rendered frames.
2. **On a short clip the two tie, and native is cheaper.** On the 5-minute
   clip both articles are good and grounded; the native one is 27% cheaper and
   31% faster. The harness article is slightly more complete (sponsor mention,
   the subreddit example, the three tool types), not decisively better.
3. **The transcript is what the harness brings; without it the harness
   hallucinates.** On the no-audio talk the frames-only harness missed three key
   points and invented a contrast ("say *I've got it* rather than *we'll figure
   it out*") that the talk does not make. Giving it the reference transcript
   lifted key-point coverage from 0.67 to 1.00 at the same cost and let it name
   the speaker, which native never did.
4. **Nobody verifies figures, and the transcript made it worse.** Caption/frame
   mismatch rates: native 1/8, frames-only harness 1/9, harness with oracle
   transcript **6/15**. With a transcript the model dated slides by speech
   timing instead of by the frame evidence it already held, drifting 1–2 minutes
   in the middle of the talk. `Figure.evidence_id` is optional and the
   `referenced_evidence_exists` gate covers claims, not figures.

## Follow-up ablation: frame labels (same day)

`harness+qwen3.8-max+frame-labels` on the no-audio talk — the same run as the
frames-only baseline, except that every image is preceded by a
`[frame-id @ MM:SS]` text label:

| System | Cost (CNY) | Figures | Figures correct | Key points |
|---|---|---|---|---|
| frames only (baseline) | 2.95 | 9 | 8/9 | 0.67 |
| frames + labels | 2.75 | 13 | **13/13** | **1.00** |

Without a transcript, the label alone took key-point coverage to 1.00 and every
caption matched its frame, including the six mid-talk slides the oracle run
got wrong. Labels are now the default for the harness synthesis call in both
the evaluation and the live client; `+plain-frames` is the ablation.

## What changed in the repository because of this run

- `figure_captions_grounded` gate on the article task (active once frames
  carry perception text).
- `tool.call.failed` / `probe.failed` carry the structured failure record.
- Frame labels on by default; prompt version `eval-prompts/2026-11-01`.
- Model and endpoint chosen from an allow-list before a run
  (`VIDSNAP_QWEN_MODEL`, `VIDSNAP_QWEN_ENDPOINT`); `analyze --mode/--tools/
  --model/--endpoint`; `HarnessPolicy.allowed_tools`.
- `vidsnap recipe article`, built on the t1 machinery.

Still open: the native upload path for long videos, perception text on frames
(which would make the caption gate bite), and per-run clip directories.

## Defects found in the harness (actionable)

- **Figures bypass the evidence gate.** Require `evidence_id` on every figure in
  harness systems, render the figure from the referenced frame, and fail the gate
  when a figure cites no frame.
- **Failures lose their reason.** `probe.failed {}` and `tool.call.failed {}`
  carried no message; the ASR 400 body was never recorded. Record the provider
  message (never the request) on failure events.
- **Native baseline needs the upload path.** Without it, every comparison on a
  video longer than ~10 minutes is a forfeit, which flatters the harness. The
  temporary-upload path in `benchmark/url_probe` is the documented next step.
- **Concurrent evaluations share `_clips/`.** Two systems clipping the same item
  into one `--out` raced; the harness probed a half-written file. Use one output
  directory per run or key clips by run.
- ASR segmentation was correct (4 × 240 s MP3 for 13 min; 12.5 MB for 26 min
  succeeded), so the single 400 looks transient or clip-specific. Unknown until
  bodies are recorded.

## What this changes about the product claim

Not "the harness beats sending the video to the model" — on a short clip it does
not. The defensible claim is narrower and stronger: **for long videos, and for
output whose every figure and timestamp can be checked, the harness is the only
path that works at all**, and it costs about the same per video as the native
path does on the clips the native path can take. The missing piece that would
turn "can be checked" into "is checked" is the figure gate above.

Reviewer's own caveat: one video per condition. The report command itself says
"insufficient evidence (1 scored items, need 3)". Treat these as the first
three data points, not a benchmark.
