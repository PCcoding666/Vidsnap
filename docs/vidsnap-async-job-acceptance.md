# VidSnap Slim Async Job Acceptance Criteria

## Product Boundary

VidSnap Slim turns a local video into reusable text knowledge assets. The system must not require YouTube download, must not fabricate transcript-backed content, and must keep long-running video work recoverable when an external provider fails.

## P0 Acceptance Criteria

1. `POST /api/v1/workspace/jobs` creates a job and returns within 2 seconds after the upload is persisted locally.
2. The create response contains `job_id`, `status`, `stage`, `progress`, `plan`, `validation`, and a safe user-facing `message`.
3. Video processing runs in a background worker, not inside the request/response lifecycle.
4. `GET /api/v1/workspace/jobs/{job_id}` returns the current state for every job until process restart, including `created_at`, `updated_at`, `attempts`, `max_attempts`, `stage`, `progress`, `error`, `retryable`, `plan`, `skill_trace`, and `cost_estimate`.
5. `GET /api/v1/workspace/jobs/{job_id}/artifact` returns `404` until an artifact exists, then returns the latest artifact, transcript index, video asset, plan, validation, and artifact version history.
6. Audio extraction must not default to large PCM WAV for long videos. The default intermediate audio format is compressed mono 16kHz FLAC.
7. Transcription failures are stored on the job and do not erase uploaded file path, plan, trace, partial transcript index, or existing artifact versions.
8. Retryable provider/network failures mark the job as `failed` with `retryable=true`, `failed_stage`, and the original error message.
9. The frontend starts a job, polls job status, shows stage progress, and never blocks on one long synchronous processing request.

## P1 Acceptance Criteria

1. `GET /api/v1/workspace/jobs/{job_id}/events` exposes Server-Sent Events with current job snapshots.
2. Transcript index entries include `chunk_id` and `provider` metadata when available.
3. `POST /api/v1/workspace/jobs/{job_id}/retry` resumes a failed retryable job from the saved input path without requiring another upload.
4. Transcription is behind a provider adapter boundary with provider name, retry policy, and provider error classification.
5. Job status includes cost and duration estimates: source file size, estimated audio size, estimated transcript minutes, provider, and whether chunking is expected.

## P2 Acceptance Criteria

1. Local ASR fallback is represented as a provider adapter and can be selected in the plan/job request, even if unavailable in the current environment.
2. Artifact versions are append-only; regenerating an artifact creates a new version without overwriting prior versions.
3. `POST /api/v1/workspace/jobs/{job_id}/artifacts` creates a new artifact version from a custom query or custom skill plan.
4. Long videos can be split into chunk metadata for transcription, and chunk results can be merged back into a single transcript index with stable offsets.
5. `POST /api/v1/workspace/jobs/{job_id}/qa` answers against the currently available transcript index and explicitly reports when the answer is partial because processing is still running.

## Non-Acceptable States

- A long video request keeps one HTTP request open for the full processing duration.
- A transient ASR network failure loses the job or forces the user to upload the file again.
- A failed provider call is returned only as a generic `500` without stage, retryability, and recoverability information.
- The frontend only shows a spinner without stage, progress, or failure context.
- Generated notes or answers claim details not backed by transcript text or explicitly available frames.
