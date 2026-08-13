# Direct Video URL Compatibility Probe Design

## Decision

Run one diagnostic request to determine whether the Qwen Token Plan endpoint can
consume the same Direct baseline video through Alibaba Cloud Model Studio's
private temporary-file transport. This is a transport compatibility probe, not
a fourth benchmark variant and not evidence for accuracy, efficiency,
noninferiority, or superiority.

The probe is permitted to upload one public benchmark video to private temporary
storage for internal, non-commercial research. The object may exist for no more
than 48 hours and must not be made public, committed, or copied into a benchmark
report.

## Why this probe is next

The latest six-case smoke produced successful Fixed and Agentic outcomes for all
six cases, but the Direct 2 fps frame-sequence fallback failed on three longer
cases before provider token processing. Lowering the frame dimensions did not
change that result. Alibaba Cloud documents URL-based video input and requires a
URL rather than Base64 for larger video payloads. The smallest test that
distinguishes a transport limitation from a model limitation is therefore one
remote-video request with all model and sampling variables held fixed.

The selected case is `videomme:395-2`:

- source SHA-256:
  `f22889faeedd58563e5349723d10a6d81d8e0c5d167f0962d3cc221e08d3e9d2`;
- local source size: `15,543,000` bytes;
- the case previously failed in Direct `frames_2fps` mode;
- the original video is small enough for a low-budget upload while exceeding the
  documented threshold where inline video transport is unsuitable.

## Considered approaches

1. **Model Studio private temporary upload — selected.** Upload the original
   video for the target model, use the returned model/account-bound `oss://`
   reference once, and rely on automatic expiry within 48 hours. This directly
   tests the provider's documented large-video path with minimal setup.
2. **User-managed private OSS signed URL — deferred.** This provides stronger
   lifecycle control but requires separate storage configuration and signed-URL
   handling. It adds no evidence unless the Model Studio temporary upload API is
   incompatible with the Token Plan credential.
3. **Keep tuning frame lists — rejected.** Reducing fps, dropping timeline
   frames, splitting Direct into multiple calls, or excluding long cases changes
   the registered Direct baseline or repeats an already falsified transport
   hypothesis.

If the selected upload API is incompatible with the Token Plan credential, the
probe stops. It does not silently use another API key, model, public host, or
transport.

## Components and data flow

The implementation will add a narrow diagnostic command, separate from the
benchmark runner:

1. The existing Hermes launcher reads the already configured Token Plan endpoint
   and credential and injects them only into the diagnostic child process.
2. The child validates the selected local file's path, size, and SHA-256 before
   any network operation.
3. The child requests a temporary upload policy for exactly `qwen3.8-max`, uploads
   the original MP4 to the returned private destination, and retains the
   resulting `oss://` reference only in memory.
4. The child sends one OpenAI-compatible `chat/completions` request to the same
   Token Plan endpoint with `type=video_url`, the in-memory `oss://` reference,
   explicit `fps=2`, and the provider's OSS-resource-resolution header.
5. The child parses only terminal status and provider usage. It discards the
   answer text and the temporary reference before exit.
6. The child writes a sanitized external diagnostic report containing only the
   case ID, source SHA-256, local source bytes, fixed model ID, fixed fps,
   model-call count, the serialized JSON request byte count as a number, provider
   input/output tokens, latency, upload status, request status, and a bounded
   failure category. The serialized request itself and its temporary reference
   are never written.

The diagnostic command will never be called by a smoke or formal run. A probe
success only authorizes a separately tested Direct URL transport adapter; it
does not mark the smoke successful by itself.

## Security and data-lifecycle boundary

- Use only the Hermes-injected Token Plan credential and approved endpoint.
- Keep the credential, Authorization header, upload policy, signed fields,
  temporary upload destination, `oss://` reference, raw request, raw response,
  and answer text out of stdout, stderr, exceptions, files, reports, and git.
- Use a repository-external output directory. Reject output paths inside the
  worktree or main checkout.
- Do not print the uploaded object's URL or identifier, including on HTTP errors.
- Do not add retries: at most one upload and one model request are allowed.
- Treat provider-managed automatic deletion within 48 hours as the maximum
  retention. The diagnostic report records the expected expiry window but no
  retrievable object identifier.
- Run the repository secret scanner against the external sanitized report and
  verify that no credential-like or URL-bearing field exists.

## Accounting validity

The probe is not used in any efficiency calculation. Its serialized request byte
count is diagnostic only.

If URL transport is later added to Direct, the URL string length must not be
treated as the video's evidence-input cost. Before rerunning smoke, tests must
require separate accounting for the local video bytes made available to the
provider and for the serialized JSON request bytes. The pre-registered formal
efficiency gate may use only a byte metric whose media accounting is comparable
across Direct, Fixed, and Agentic, or provider-reported input tokens. No positive
conclusion may depend on counting a remote URL as near-zero input.

## Error handling and stop conditions

Every failure maps to one sanitized category: local validation, upload-policy
compatibility, upload transfer, provider URL resolution, model request, response
schema, or usage missing. Detailed provider bodies and URLs are not persisted.

The probe succeeds only when all of the following are true:

- preflight SHA-256 and local size match the registered case;
- the temporary upload and the one model request both complete;
- the request remains fixed to `qwen3.8-max` and the provider reports nonzero
  input-token usage;
- no credential, signed upload field, temporary URL, raw request, raw response,
  or answer text appears in terminal output or the external report;
- the report records one model call, `fps=2`, source SHA-256, source bytes,
  latency, and provider token usage.

If any condition fails, stop and report the failure category and the smallest
next diagnostic step. Do not run another six-case smoke and do not run the
54-case formal benchmark.

## Testing and execution order

Implementation follows TDD:

1. Add failing tests for fixed model/fps/case binding, one-call limits, in-memory
   URL handling, sanitized failures, external-only output, and report schema.
2. Add the minimal diagnostic client and command needed to pass those tests.
3. Run the complete offline repository gate and secret scan.
4. Run a no-network validation mode against the selected external case.
5. Through the Hermes launcher, perform exactly one live upload and one live
   model request.
6. Audit the sanitized report and terminal capture. Only a successful audit may
   lead to a separate TDD plan for the Direct URL adapter and a new six-case
   smoke.

The existing Draft PR remains stacked on `codex/video-harness-core`; this work
does not merge it, modify PR #7, or authorize the formal benchmark.

## Provider references

- [Alibaba Cloud Model Studio temporary file upload](https://help.aliyun.com/en/model-studio/get-temporary-file-url)
- [Qwen OpenAI-compatible video input](https://help.aliyun.com/en/model-studio/qwen-api-via-openai-chat-completions)
- [Alibaba Cloud Model Studio input-size error guidance](https://help.aliyun.com/en/model-studio/error-code)
