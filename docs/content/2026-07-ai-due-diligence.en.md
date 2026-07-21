# I asked an AI to run due diligence on my own project. It found my docs were lying.

> Status: draft v1 (for: dev.to / Hacker News / X thread) · Image slots marked · 中文版 in the same folder (`.zh.md`)

---

I handed an AI a "technical due diligence" prompt and pointed it at my own open-source project. A few hours later it came back with a table titled **"Claimed vs. Actual."**

Five rows. Every single one was my documentation lying to me.

## Context

The project is [VidSnap](https://github.com/PCcoding666/Vidsnap): upload a local video, state a goal in natural language, and it turns the video into searchable, citable text assets (transcript, summaries, illustrated notes, Q&A). A typical "one human + AI pair" project — features shipped fast. Faster than the docs, the comments, and even the code's own self-descriptions could keep up.

I originally just wanted to ask: *"What should I build next?"* But instead of asking for advice, I made the AI walk a six-phase process first:

```
1. Build a factual model of the project (describe, don't judge)
2. Capability inventory (every capability needs code/doc/commit evidence)
3. Gap analysis
4. Opportunity analysis (quick wins / high leverage / what to delete)
5. Roadmap
6. Decision (one week of dev time — what's in, what's out)

Iron rules: no vibes; label every conclusion Confirmed / Likely / Unknown;
if evidence is missing, write Unknown — never invent.
```

## The lies it found

<!-- image slot: "Claimed vs. Actual" table screenshot -->

| # | Docs/comments claimed | Code actually | Evidence |
|---|---|---|---|
| 1 | "Key-frame / visual analysis is disabled — text only" | Frame analysis was **on by default**, and it's the project's most differentiated feature (frames + VLM + OCR notes) | `WORKSPACE_FRAMES_ENABLED=true` in `config.py` |
| 2 | The planner tells users "YouTube downloading is out of scope" | The `/jobs` endpoint **actually downloads YouTube videos** | `planner_service.py:198` vs `workspace.py:104` |
| 3 | "Residential IPs barely get bot-checked; this is a thin wrapper" | Reality requires Deno + a PO-token provider + cookies, **all three or it fails** | comment vs. the README's own prerequisites |
| 4 | requirements.txt: "transcription via SenseVoice" | A different ASR model entirely | `pipeline_service.py:30` |
| 5 | "Supabase is disabled" | The frontend still bundled the Supabase client — **with a leaked anon key hardcoded in it** | `frontend/.env.production` (git-tracked) |

Row 2 is my favorite. Every time the planner produced a plan, it printed a hardcoded line telling the user "I don't do YouTube" — while the very same system was downloading YouTube videos. **The system was contradicting itself out loud, and I never noticed.**

## The root cause isn't laziness — it's an architecture disease

The AI's diagnosis went one level deeper than I expected. These five weren't five isolated typos; they were **five symptoms of one pattern**:

> Capabilities and boundaries get declared as static data (plans, registries, comments) while actual execution runs through a separate hardcoded path. The two are held together by nothing but string conventions — so they evolve independently, and doc drift is just a matter of time.

In other words: **lying docs are the symptom; the missing single source of truth between declaration and execution is the disease.** Your project probably has it too. Every comment that says "X is disabled" or "Y is unsupported" deserves suspicion.

## The fix: make the AI clean up its own crime scene

I turned the findings into an autonomous backlog with iron rules and handed it back:

- **Evidence first**: read the code before touching it; label Confirmed vs. Unknown
- **Smallest safe increment**: one independently verifiable change at a time
- **Never break the build**: full tests + build after every change
- **Gates**: anything that expands product scope must stop and ask me

It worked through everything: aligned every claim, deleted 2,000+ lines of dead code, scrubbed the leaked key from the working tree, turned frame analysis into an explicit `visual_mode` option, and landed CI. 48 tests green, 120 planner golden cases green.

## And then the fix lied to me too

Here's the twist. During the fix, the ASR model id was unified — per my own spoken instruction — to `fun-asr-flash`. Tests green. CI green. Docs consistent. Perfect.

Then I uploaded a **real video** to verify. Transcription failed instantly:

```
HTTP 400 - Model not exist.
```

`fun-asr-flash` **does not exist**. No static check could have caught it, because the lie was internally consistent at every layer — only the real world disagreed. The AI then probed the ASR provider's live API, confirmed which model ids actually exist, fixed the id, and re-ran end-to-end on a real video: 69 transcript segments, one structured note with timestamped citations.

That produced the most important rule of this whole exercise:

> **A claim only counts after it survives a real-sample run.** Green tests ≠ actually works.

## Where it landed: a public report card

Two things became permanent and public:

1. The README now carries a **live badge**: on every push, CI re-runs all 120 planner golden cases and publishes the pass rate. I can afford to show it because CI computes the number — not me.
2. The entire repair process — including the AI's own faceplant — is in a public [build log](https://github.com/PCcoding666/Vidsnap/blob/vidsnap_slim/docs/build-log.md).

That's the project's identity now: **glass-box AI** — transparent (execution traces you can watch), auditable (artifacts anchored to timestamped citations), reproducible (a public report card). For the tool, and for the process that builds it.

## Steal these

1. **The due-diligence prompt skeleton** above — it works on any project that ships faster than its docs
2. **Three disciplines**: evidence first / confidence labels / real-sample acceptance
3. **One paranoia**: grep your repo for "disabled", "unsupported", "out of scope" — then verify each one. At least one of them is lying to you.

---

*Project: [github.com/PCcoding666/Vidsnap](https://github.com/PCcoding666/Vidsnap) · Due diligence and repairs executed by Claude Code; gates and acceptance were mine.*
