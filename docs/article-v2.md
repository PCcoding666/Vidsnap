# Reviewed article recipe v2

Article v2 adds actual-image caption review and one targeted editorial revision to
`recipe article`. Enable it explicitly; v1 remains the default, with its original
prompt, sampling behavior and gates.

```sh
vidsnap recipe article /absolute/path/video.mp4 \
  --recipe-version v2 --endpoint token-plan \
  --output-dir /absolute/path/article-v2 --runs-root /absolute/path/runs
```

The article recipe selects its approved model and endpoint before the run, using
`--model` (default `qwen3.8-max`) and `--endpoint` (default `dashscope`, unchanged).
For Token Plan set `VIDSNAP_QWEN_API_KEY`; for DashScope set
`VIDSNAP_DASHSCOPE_API_KEY`. Videos with audio use the existing separate DashScope
ASR adapter and require the DashScope key even when synthesis uses Token Plan.
Keys stay in local environment variables. V2 never changes providers mid-run.

## Workflow and limits

1. Probe the local video and transcribe audio through the existing typed ports.
2. Sample at most 32 frames and write the draft.
3. Review every cited image with its caption, article context and transcript.
   The reviewer must distinguish supported, contradicted and insufficient evidence.
   It also checks factual support, repetition, flow and instructional clarity.
4. If needed, sample at most 24 additional frames across up to three problem
   windows (five seconds on either side of each affected figure, clipped to the
   video). These are newly requested timestamps inside the windows, independent
   of the global candidate pool. Editorial-only issues need no new frames.
5. Replace only flagged sections once. Global fields can change only when the
   review identifies a global issue. Review the resulting article again.

The run declares at most four article-model calls, three tool calls, two
iterations, 96 retained evidence frames and 900 seconds. The recipe normally
uses no more than 56 frames; unused frame headroom is not automatically spent.
Article model operations have cancellation deadlines based on the remaining run
budget. Probe and media tools retain their existing timeout behavior; they are
checked against the wall budget at phase boundaries. ASR calls are recorded as
separate speech-recognition usage, as before, rather than article-model calls.

A successful initial review skips patching and uses two article-model calls.
Otherwise the run performs at most one patch and one final review. Missing review
entries, invalid citations and mismatched timestamps cannot count as visual
support. Unknown/duplicate review coordinates and edits outside the flagged scope
fail closed. Remaining validly reported issues end in `PARTIAL`. Provider failures
end in `FAILED`/`BLOCKED`, and budget exhaustion in `EXHAUSTED`. The most recent
valid article remains available if drafting already completed. An available
`article.md` alone does **not** mean the run passed; check `terminal_state`.

## Local outputs and audit

The output directory keeps the existing `article.md`, `output.json` and `images/`
layout. V2 renders only captured evidence images; missing citations never trigger
extra extraction after the run. ArticleOutput and RunBundle schemas remain
compatible. The run header
identifies `recipe/article` version `2.0.0`, and the dense sampler identifies its
separate versioned plugin. The run index exposes failed visual/editorial gates.

Validated intermediate outputs are written once under the private RunBundle:

```text
artifacts/article-v2/
  draft.json
  review-1.json    # vidsnap.article-review/v1
  patch.json       # vidsnap.article-patch/v1, only when revised
  revised.json    # only when revised
  review-2.json    # only when the second review completed
```

The bundle manifest hashes these artifacts. They are local run data and must not
be committed. Traces contain phase/usage/gate records, not raw provider traffic,
images or editorial prose. Export the normal offline trace with:

```sh
vidsnap trace export /absolute/path/runs/RUN_ID -o /absolute/path/trace.html
```

From Python, `ArticleRecipeRunner(recipe_version="v2", synthesis_port=port)`
accepts a conforming `SynthesisPort` before the run. All four steps use that same
port. Offline tests inject scripted replies and synthetic frames; the generic
`harness+mock` article generator alone does not generate review/patch schemas.

## What this establishes

Offline tests establish control flow, image delivery, scope enforcement, budget
accounting, preserved drafts and trace compatibility. Visual review is a model
judgment; it is not independent proof that every statement in an article is true.
This change has not yet been measured on real videos against v1 or Codex. It does
not add article splitting, a new publishing layout, resumable runs or publishing.
