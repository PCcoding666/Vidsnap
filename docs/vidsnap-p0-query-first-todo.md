# VidSnap P0 Query-First TODO and Acceptance

Last reviewed: 2026-06-10

## Product Contract

VidSnap P0 is not a video processing menu. It is a query-first workspace:

```
Local Video + User Query -> Skill Plan -> Executed Skills -> Reusable Artifact
```

The system must let the user state the job in natural language. The product then converts that request into a structured, validated skill plan and returns a transcript-backed artifact.

## P0 Scope

### 1. Query-First Product Contract

TODO:

- Reframe VidSnap Slim from "upload/transcribe/summarize/chat" to "local video AI-native knowledge workspace".
- Keep YouTube download, cross-video search, team collaboration, and default multimodal analysis out of P0.

Acceptance:

- Product docs state that local uploaded video is the only input.
- Docs state that transcript text is the default source of truth.
- Docs state that optional frame extraction is triggered only by explicit visual requests.
- Docs define artifact output as the primary user-facing result.

### 2. VideoAsset + Transcript + Index

TODO:

- Create a stable `VideoAsset` before task-specific artifact generation.
- Treat transcription as the default base skill.
- Build a searchable transcript index with time ranges.

Acceptance:

- `VideoAsset` includes `video_id`, `title`, `duration`, `source_type=upload`, `processing_status`, transcript segment count, and summary status.
- Transcript segments include text, start time, end time, and confidence.
- Transcript index entries can be cited by artifact outputs.
- Empty transcript paths produce explicit "no transcript available" text instead of fabricated content.

### 3. Skill Registry

TODO:

- Externalize atomic capabilities as skills.
- Make every skill independently describable and validateable.

Acceptance:

- P0 registry exposes:
  - `IngestVideo`
  - `TranscribeAudio`
  - `BuildTranscriptIndex`
  - `SummarizeContent`
  - `LocateContent`
  - `GenerateNotes`
  - `AnswerWithContext`
  - `ExtractFrames`
- Each skill has `name`, `description`, `inputs_schema`, `outputs_schema`, `cost_estimate`, `failure_modes`, and `idempotency_key`.
- `ExtractFrames` has `default_enabled=false`.

### 4. Planner JSON

TODO:

- Convert user query into structured plan JSON.
- Validate unknown skills, missing dependencies, and cycles before execution.

Acceptance:

- `POST /api/v1/workspace/plan` returns `plan_id`, `artifact_type`, ordered `steps`, dependency lists, assumptions, rejected capabilities, and cost tier.
- Plans with nonexistent skills or cyclic dependencies fail validation.
- Plans that request visual output include `ExtractFrames`; ordinary notes do not.
- Planner output is deterministic for the same query in P0.

### 5. Planner Eval

TODO:

- Build a golden query set for planner evaluation.
- Evaluate required skills, forbidden skills, and artifact type.

Acceptance:

- Eval set has at least 100 query cases.
- Current set has 120 cases across transcript, summary, notes, visual notes, location, and QA.
- `Plan skill selection accuracy >= 85%`.
- `Unnecessary skill rate <= 15%`.
- `Artifact type accuracy >= 85%`.
- `pytest backend/app/tests/test_workspace_planner.py` enforces these thresholds.

### 6. Query-First UI

TODO:

- Change the primary UI from "choose a mode" to "upload video + describe what you want".
- Keep examples as prompts, not as mandatory modes.

Acceptance:

- The first interaction asks for a local video and a natural language goal.
- The UI does not expose summary granularity, frame count, or transcript mode as required controls.
- User can submit examples such as "制作图文并茂的笔记", "视频转录", and "提取或定位特定内容".
- The result page shows the generated plan, skill trace, artifact, and transcript-backed citations.

### 7. Artifact Output

TODO:

- Return reusable artifacts instead of only chat text.

Acceptance:

- Supported artifact types:
  - `transcript`
  - `summary`
  - `notes`
  - `content_locations`
  - `qa_answer`
- Artifact includes `artifact_id`, `artifact_type`, `title`, `content`, `format`, and `citations`.
- Location artifacts include start/end time ranges and matching transcript text.
- Notes artifacts include timestamped notes and source boundary text.
- Visual-note requests do not fabricate screenshots or visual descriptions when frame extraction is disabled.

## P0 API Surface

- `GET /api/v1/workspace/skills`
- `POST /api/v1/workspace/plan`
- `POST /api/v1/workspace/process`
- `GET /api/v1/workspace/evals/planner`

## Current Non-Goals

- YouTube or remote URL downloading.
- Cross-video knowledge base search.
- Team sharing and collaboration.
- Subscription or billing changes.
- Default multimodal frame extraction.
- Persistent artifact library beyond the current video-processing result.
