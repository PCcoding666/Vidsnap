# VidSnap Development And Claude Code Archive

Last reviewed: 2026-07-30

This document is a public-safe archive of the VidSnap development history and local Claude Code conversations. It summarizes decisions, delivery, unresolved debt, and source locations without copying raw chat logs, secrets, cookies, private server details, or local credentials.

## Privacy Boundary

The raw Claude Code archive includes real development commands, local paths, deployment notes, and sensitive credential-like material. Do not publish raw JSONL, pasted cookies, `.env` files, terminal transcripts, or unredacted server notes.

Safe to publish here:

- Product and architecture decisions.
- Redacted session inventory.
- Commit-level development history.
- Non-secret lessons, failures, and next-step themes.

Not safe to publish:

- API keys, cookies, GitHub tokens, SSH material, server IPs, personal emails, `.env` contents, and exact operational access paths.
- Raw Claude tool outputs that may contain environment variables or command output.
- Any material copied directly from private browser sessions.

## Source Inventory

Repository evidence:

- `README.md` defines the current public positioning: VidSnap is a glass-box AI video workbench.
- `docs/build-log.md` records Cycle 0 through Cycle 5 as the public build-in-public trail.
- `docs/architecture.md` describes the current FastAPI + React/Vite + local PostgreSQL/Redis architecture and query-first data flow.
- `docs/vidsnap-slim-product-boundary.md` records the earlier Slim boundary.
- `docs/vidsnap-p0-query-first-todo.md` records P0 acceptance criteria.
- Git history records the product shift from a broad video summarizer/SaaS direction to a query-first, transcript-grounded, open-source-oriented workbench.

Claude Code evidence:

| Source | Time Range | Size / Shape | Archive Role |
| --- | --- | ---: | --- |
| `2e3ad164-78cc-4836-871f-56f9c4cd1531.jsonl` | 2026-06-22 to 2026-07-27 | 4,917 lines, about 252k extracted text chars | Main long-running development thread. Covered image rendering, token gateway, local run/debug, PRs, deployment, UI, YouTube, P0 hardening, cycles, and later continuation. |
| `d93c4427-4175-4379-8dde-dc5d4c7f60b7.jsonl` | 2026-07-06 | 277 lines, about 54k extracted text chars | Open-source review, security hardening, CI/CLI discussion, autonomous loop decisions. |
| `b72f2196-563a-471c-8cda-f1b8df454510.jsonl` | 2026-07-24 | 450 lines, about 23k extracted text chars | Re-entry after feeling lost, project state scan, cycle rationale, note-quality critique, Cycle 5 timestamp fix, Cycle 6 direction. |
| `fc094c9e-1bea-4699-ada2-6d535593ffe8.jsonl` | 2026-07-03 | 6 lines | Tiny continuation stub; no substantive archive content. |
| `d93c.../subagents/agent-a90b4ec5efc32ef37.jsonl` | 2026-07-06 | 42 lines, about 13k extracted text chars | Backend coupling review for possible CLI/headless operation. |
| `d93c.../subagents/agent-a3309bc344110348b.jsonl` | 2026-07-06 | 63 lines, about 10k extracted text chars | Pre-open-source security and privacy audit. |
| `memory/*.md` | 2026-06 to 2026-07 | 7 memory files | Compressed project memory: production topology, token leak risk, YouTube skill, P0 hardening, influence charter, notes quality cycle. |

## Current Project Identity

VidSnap is now best understood as:

```text
Local Video + User Query -> Skill Plan -> Transcript Index -> Reusable Artifact
```

Its differentiator is not merely "video summary." The stronger identity is glass-box AI tooling:

- Transparent: planner, skill plan, trace, status, cost, and execution path are visible.
- Auditable: transcript timestamps and citations anchor generated artifacts.
- Reproducible: planner behavior is covered by a 120-case golden set and public badge.
- Build-in-public ready: the development process itself is being turned into evidence through build logs, screenshots, metrics, and bilingual content.

## Chronological Archive

### 2025-04 to 2025-12: Original Video Summarizer And SaaS Drift

The repository started as a video summarizer with backend/frontend integration, then accumulated Alibaba Cloud services, Gradio, Qwen/VL experiments, YouTube support, chat with video, Supabase/OAuth, production scripts, and multiple frontend reorganizations.

This phase produced useful raw capability, but also created product drift: too many entry points, too many deployment assumptions, and a cloudy boundary between local tool, SaaS app, YouTube downloader, and multimodal video platform.

### 2026-06-10 to 2026-06-16: Slim Boundary And Query-First Reframe

The project was deliberately narrowed:

- Local video upload became the core input.
- Transcript became the default source of truth.
- Query-first workspace replaced mode-first processing menus.
- Planner, skill registry, workspace jobs, transcript index, and artifact outputs became the new product spine.

The key architectural decision was to make user intent explicit first, then derive a deterministic skill plan.

### 2026-06-21 to 2026-06-22: Visual Notes, Frame Selection, Mermaid, And Image Portability

Development moved into illustrated notes:

- `ExtractFrames` and frame analysis were wired into the note pipeline.
- OCR and zoomed frame crops improved screen-heavy videos.
- LLM-composed illustrated notes placed screenshots near related transcript sections.
- Mermaid fallback diagrams were added when no suitable frame existed.

A practical failure appeared immediately: generated Markdown used local backend image URLs, so images broke in Claude Code or standalone Markdown previews. The chosen fix was base64/data-URI embedding for note images so exported notes could be viewed independently.

### 2026-06-22 to 2026-06-23: Token Gateway, Real Video Testing, And OSS Blocking

A middle-layer LLM gateway was added to centralize DashScope calls and track token usage globally and per job. Real video testing showed:

- Multimodal frame analysis was the token-heavy part.
- ASR cost was outside LLM token accounting.
- Large video handling exposed synchronous OSS upload blocking the API event loop.

This period also clarified a useful engineering principle for the project: tests and code structure matter, but real videos expose the system-level failures that unit tests miss.

### 2026-06-23 to 2026-06-24: PR Hygiene And Token Accounting Correction

The token gateway became a separate PR to avoid mixing it with OSS event-loop work. Review found that `image_tokens` were likely double-counted if treated as independent from input tokens. The accounting and tests were corrected before merge.

This phase established a repeatable contribution rhythm: isolate PR scope, review before merge, and let tests guard regressions.

### 2026-06-25 to 2026-06-30: Production Deployment And Product Surface Simplification

The project moved to an independent Docker Compose deployment with backend, frontend, Postgres, and Redis. The frontend login wall and old landing-page path were removed so the root route opened directly into the upload/workspace experience.

Operationally, the project gained production deployment assets. Product-wise, it moved away from "SaaS shell first" and toward "usable tool first."

### 2026-07-02 to 2026-07-03: Dark Toolchain Workspace And Debuggability

The main UI moved toward a darker toolchain/workbench style. Runtime debugging exposed:

- Frontend/backend proxy and nginx path details mattered for `/workspace/jobs`.
- POST redirects could drop upload bodies if nginx route matching was wrong.
- Logs needed to be easy to follow locally and on the deployed environment.
- Data-URI image rendering remained important for portable artifacts.

The front-end direction became "developer workbench," but later sessions still judged the design and visualization quality as not yet benchmark-worthy.

### 2026-07-06: Open-Source Review, Security Hardening, CI, And CLI Feasibility

The first explicit open-source readiness review concluded:

- CLI/headless operation was feasible because the core services were already mostly decoupled from FastAPI/WebSocket/Redis.
- But CLI was not the top priority until open-source safety and project hygiene improved.
- Real secrets existed in private/local history and required revocation or careful handling.
- Current tracked files were safer after hardening, but raw local archives must remain private.
- License, unsafe JWT defaults, CORS defaults, ignored local-note directories, and CI were addressed.

The CLI idea remained valid, but as a later packaging/distribution move rather than the immediate identity-fixing move.

### 2026-07-06: YouTube Returns As A Skill, Not The Core Product

`FetchYouTube` was introduced through an AI-native slash command:

```text
/youtube <url> <goal>
```

This is an important pivot. Earlier Slim docs excluded remote URL input. The later direction allowed YouTube as an optional skill with explicit environmental requirements, while keeping local video and transcript-backed artifacts as the core path.

The agreed boundary: do not hide YouTube anti-bot complexity. Users bring their own Deno/bgutil/cookie setup if they want it.

### 2026-07-09 to 2026-07-10: P0 Hardening And Glass-Box Positioning

A full project review produced a P0 hardening backlog:

- P0-1: align declarations and remove stale/dead claims.
- P0-2: remove Supabase from the active product path and rename the remaining local store proxy correctly.
- P0-3: make frame extraction plan-driven through `visual_mode=auto/on/off`.
- P0-4: add CI and keep planner evals green.

Real video testing caught a bad ASR model claim: `fun-asr-flash` did not exist in the tested provider path, so the project corrected back to `fun-asr`.

After P0, the public positioning became:

- VidSnap: a glass-box AI video workbench.
- Three pillars: trace, citations, evals.
- Public build log as part of the project identity.
- 120-case planner golden set as a public quality signal.

### 2026-07-10: Influence Charter And Build Cycles

The project adopted an influence-driven operating model:

- North star: reputation events, inbound interest, citations, stars, real outside usage.
- Brand line: "I build AI tools that show their work."
- Ring 0: autonomous code/demo/docs cycles with machine gates.
- Ring 1: public posts and anything under the author's name stay human-gated.
- Ring 2: secrets, host machine, history rewriting, and personal appearance stay protected.

Cycle 0 to Cycle 4 delivered:

- Build log and charter.
- README glass-box rewrite.
- Planner eval badge.
- Bilingual content draft about AI due diligence discovering false project claims.
- Real Playwright-captured trace screenshot.
- Influence metrics snapshot collector.

### 2026-07-17 to 2026-07-22: Domain Migration And Content Packaging

The public domain migrated to the current project domain, and the first content package gained channel order, titles, hooks, and publication discipline.

The project was increasingly treated not just as software, but as a public artifact: code, proof, screenshots, metrics, and writing all had to reinforce the same thesis.

### 2026-07-24: Re-Entry, Note Quality, And Cycle 5

After a pause, the project state was rescanned because the maintainer felt lost. The key emotional/product blocker was not "there is no project," but "the output quality is not yet something I am proud to publish."

Real video testing with a Figma Make demo exposed a specific notes-quality defect:

- The user asked for timeline notes with timestamps.
- Pure text notes lost timestamps because transcript segments had been flattened before note composition.
- Timestamps were only reintroduced via frames, so no frames meant no timestamped sections.

Cycle 5 fixed this by feeding transcript segments as `[mm:ss] text` and requiring major note sections to anchor to real timestamps. Tests and a real video run verified that pure text notes could carry timestamps without depending on frame extraction.

Cycle 6 direction was selected: make screenshot/frame use transparent and proactive. The product should detect screen-heavy/high-visual videos cheaply, explain the reason, and offer a one-click `visual_mode=on` suggestion instead of silently relying on query keywords.

## Major Decisions And Pivots

1. From broad SaaS/video platform to local-first query-first workbench.
2. From hidden model behavior to visible plan, trace, citations, and evals.
3. From mandatory/implicit visual processing to plan-driven optional `visual_mode`.
4. From "YouTube out of scope" to optional `/youtube` skill with honest anti-bot requirements.
5. From cloud database assumptions to local PostgreSQL plus open-source-friendly operation.
6. From feature count as progress to influence cycles: one proof-bearing improvement per cycle.
7. From "tests passed" to "tests plus real video proof" as the quality bar.

## Completed Assets

Product and backend:

- Query-first workspace API.
- Deterministic planner and skill registry.
- Workspace jobs, artifacts, artifact versions, QA, and SSE surface.
- Transcript index and timestamp/citation-backed artifacts.
- Optional frame extraction via `visual_mode`.
- YouTube slash command path.
- LLM token gateway and accounting endpoints.
- Paraformer/Fun-ASR provider handling, OSS signed URL flow, retries, and error classification.

Frontend:

- React/Vite workspace.
- Upload plus natural language goal flow.
- Plan/trace/artifact/transcript display.
- Dark toolchain direction.
- Basic job polling and status display.

Open-source and operations:

- MIT license.
- CI.
- Public README positioning.
- Docs hub, architecture, configuration, deployment, troubleshooting, contribution docs.
- Docker production assets.
- Public build log.
- Planner eval badge.
- Real screenshot capture script.
- Influence metric collector.
- Bilingual content draft and publication kit.

## Known Open Threads

These are archive findings, not yet a final roadmap:

- Job persistence is still process-memory-bound. Restarting the API loses job state.
- Trace step state was observed not to update live enough during long runs.
- Frontend design and visualization quality are not yet at personal-homepage benchmark quality.
- Frontend automated tests are still thin or absent compared with backend tests.
- Visual-mode auto currently relies too much on query wording; Cycle 6 proposes cheap visual pre-scan plus explicit suggestion.
- Product boundary docs and README need a single updated truth around local core, optional visual, and optional YouTube skill.
- YouTube support remains operationally fragile by nature; it should stay optional and honest.
- Historical secret exposure requires owner-side revocation/rotation confirmation before any public push that might draw attention.
- CLI remains feasible, but it should follow after the public experience and core trust story are clearer.

## Future Planning Frame

When planning the next phase, use this sequence:

1. Trust first: verify secrets are rotated, docs do not overclaim, and real demo paths still run.
2. Output quality second: make generated artifacts good enough to show without apology.
3. Visual transparency third: show why frames are or are not used, and let the user override.
4. Developer confidence fourth: add frontend visual regression/e2e tests and improve reports.
5. Public polish fifth: once the tool produces a proud artifact, improve homepage/readme/demo flow.
6. Distribution last: revisit CLI after the product story and proof loop are stable.

## How To Use This Archive

Use this document as the shared memory before future planning sessions. It is intentionally not a full raw transcript. If a future decision needs exact details, inspect the raw local Claude Code JSONL files directly, then quote only redacted, minimal excerpts.
