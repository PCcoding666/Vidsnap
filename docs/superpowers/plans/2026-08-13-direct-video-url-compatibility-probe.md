# Direct Video URL Compatibility Probe Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Safely test one registered Video-MME case through Alibaba Cloud Model Studio private temporary storage and one `qwen3.8-max` URL-video request without producing benchmark conclusions or retaining sensitive transport data.

**Architecture:** Add a diagnostic-only client under `vidsnap.benchmark` and a separate script that validates the fixed registered case, performs one policy request, one private upload, and one model request, then writes only a sanitized report outside the repository. The existing smoke/formal runner remains unchanged; a successful probe merely establishes transport compatibility.

**Tech Stack:** Python 3.10, Pydantic v2, httpx, pytest/pytest-asyncio, existing Hermes child-process launcher, Alibaba Cloud Model Studio temporary upload API and OpenAI-compatible Token Plan endpoint.

## Global Constraints

- Use only model `qwen3.8-max`, explicit `fps=2`, case `videomme:395-2`, SHA-256 `f22889faeedd58563e5349723d10a6d81d8e0c5d167f0962d3cc221e08d3e9d2`, and local source size `15,543,000` bytes.
- Read the Token Plan credential and endpoint only through `scripts/run_with_hermes_qwen.py`; never print or persist either value.
- Permit exactly one temporary upload and at most one model request; do not retry or switch credentials, models, endpoints, public hosts, or cases.
- Keep upload credentials, upload host, object key, `oss://` reference, Authorization header, raw request, raw response, and answer text out of files, terminal output, exceptions, reports, and git.
- Write the diagnostic report only outside the repository and record no accuracy, efficiency, noninferiority, or superiority conclusion.
- Do not modify the smoke/formal execution path, run the 54-case formal benchmark, merge PR #8, or modify PR #7.

---

## File map

- `src/vidsnap/benchmark/url_probe.py`: fixed probe contract, local preflight, temporary-upload flow, one URL-video request, sanitized result types, and safe failure categories.
- `scripts/run_direct_url_probe.py`: external-only CLI, registered-manifest binding, validate-only mode, sanitized report writing, and safe terminal summary.
- `tests/benchmark/test_url_probe.py`: request-shape, one-call, validation, accounting, and redaction tests using `httpx.MockTransport`.
- `tests/test_direct_url_probe_script.py`: command boundary, report schema, external-path, manifest-binding, and terminal-redaction tests.

### Task 1: Add the fixed diagnostic client and contracts

**Files:**
- Create: `src/vidsnap/benchmark/url_probe.py`
- Create: `tests/benchmark/test_url_probe.py`

**Interfaces:**
- Consumes: `BenchmarkProviderConfig`, `FormalCase`, `QWEN_MODEL`, `httpx.AsyncBaseTransport`.
- Produces: `DirectUrlProbeClient.run(case: FormalCase) -> DirectUrlProbeResult`, `validate_probe_case(case: FormalCase) -> None`, `ProbeFailureCategory`, and sanitized `DirectUrlProbeResult` fields.

- [ ] **Step 1: Write failing tests for the immutable case and local-file preflight**

Add tests that construct the registered case and prove that changing any of the case ID, SHA-256, source size, model, or fps is rejected before a transport call. The positive case must pass only with:

```python
REGISTERED_PROBE_CASE_ID = "videomme:395-2"
REGISTERED_PROBE_SHA256 = "f22889faeedd58563e5349723d10a6d81d8e0c5d167f0962d3cc221e08d3e9d2"
REGISTERED_PROBE_SOURCE_BYTES = 15_543_000
DIRECT_URL_PROBE_FPS = 2
```

Use a sparse local file of exactly `15_543_000` bytes and monkeypatch the hashing helper to the registered digest so tests do not commit benchmark media.

- [ ] **Step 2: Run the preflight tests and verify RED**

Run: `.venv/bin/python -m pytest tests/benchmark/test_url_probe.py -q`

Expected: FAIL because `vidsnap.benchmark.url_probe` does not exist.

- [ ] **Step 3: Write failing tests for the exact three-request flow and redaction**

Use one `httpx.MockTransport` handler. It returns a policy containing private fake fields, HTTP 200 with an empty body for upload, and this model response:

```python
{"choices": [{"message": {"content": "A"}}],
 "usage": {"prompt_tokens": 1234, "completion_tokens": 1}}
```

Assert that the policy request is one GET to `https://dashscope.aliyuncs.com/api/v1/uploads` with `action=getPolicy&model=qwen3.8-max`; multipart upload occurs exactly once with private ACL and one file; and the model request occurs exactly once at the configured Token Plan endpoint with `model=qwen3.8-max`, `type=video_url`, `fps=2`, and `X-DashScope-OssResourceResolve: enable`.

Assert that `repr(result)`, `model_dump_json()`, and every raised failure exclude all fake credentials, host, key, `oss://`, answer, and raw response strings. The result may contain only status, case/hash/source bytes, model/fps, call count, tokens, latency, expiry window, request byte count, upload/request statuses, and bounded failure category.

- [ ] **Step 4: Implement the minimal client**

Create these bounded values:

```python
ProbeStatus = Literal["PROBE_SUCCEEDED", "PROBE_FAILED"]
ProbeFailureCategory = Literal[
    "local_validation",
    "upload_policy_compatibility",
    "upload_transfer",
    "provider_url_resolution",
    "model_request",
    "response_schema",
    "usage_missing",
]
```

Implement a private upload-policy dataclass with every sensitive field marked `repr=False`. Use the approved policy URL, validate field types, maximum size, private ACL, and overwrite protection, upload with Alibaba Cloud's required multipart fields, construct the `oss://` reference only in memory, make one model request, parse only token usage, and discard answer content. Convert transport/status/schema errors into `DirectUrlProbeFailure(category)` from `None`; its string and repr expose only the category. Do not retry.

- [ ] **Step 5: Verify GREEN and nearby regressions**

Run:

```bash
.venv/bin/python -m pytest tests/benchmark/test_url_probe.py tests/benchmark/test_live.py -q
.venv/bin/ruff check src/vidsnap/benchmark/url_probe.py tests/benchmark/test_url_probe.py
.venv/bin/mypy src
```

Expected: all selected tests pass, Ruff reports no errors, and mypy reports no issues.

- [ ] **Step 6: Commit the diagnostic client**

```bash
git add src/vidsnap/benchmark/url_probe.py tests/benchmark/test_url_probe.py
git commit -m "feat: add private direct URL compatibility probe"
```

### Task 2: Add the external-only diagnostic command

**Files:**
- Create: `scripts/run_direct_url_probe.py`
- Create: `tests/test_direct_url_probe_script.py`

**Interfaces:**
- Consumes: `DirectUrlProbeClient`, `BenchmarkProviderConfig.from_env()`, `FormalCase`, `REGISTERED_MANIFEST_SHA256["smoke"]`.
- Produces: `--validate-only` safe summary and external `report.json` with no temporary reference, raw content, answer, credentials, or research conclusion.

- [ ] **Step 1: Write failing command-boundary tests**

Cover these behaviors with helper-level and subprocess tests:

- repository-contained output is rejected before manifest access;
- a manifest outside the committed smoke preregistration is rejected;
- exactly one `videomme:395-2` row must pass local source SHA/size checks;
- `--validate-only` makes no provider call and prints only `VALIDATED`, fixed case/model/fps, source SHA/bytes, and manifest SHA;
- success writes only `report.json` under a new external output directory;
- failure writes `PROBE_FAILED` with one bounded category and exits nonzero;
- terminal output and report expose no response text, temporary URL, upload fields, credential-like strings, answer, correctness, accuracy, conclusion, Authorization, raw request, or raw response.

- [ ] **Step 2: Run command tests and verify RED**

Run: `.venv/bin/python -m pytest tests/test_direct_url_probe_script.py -q`

Expected: FAIL because `scripts/run_direct_url_probe.py` does not exist.

- [ ] **Step 3: Implement the minimal command**

Add `--manifest ABSOLUTE_PATH`, `--output-dir ABSOLUTE_PATH`, and `--validate-only`. Require the committed smoke manifest hash, find the one registered case, validate its source before creating output, and reject output under either checkout. In live mode, create a new output directory, run the client, atomically write the result to `report.json`, and print only:

```json
{"status":"PROBE_SUCCEEDED|PROBE_FAILED","report_path":"/external/path/report.json"}
```

Exit 1 on `PROBE_FAILED`; use safe argparse errors for local validation failures.

- [ ] **Step 4: Verify GREEN and security regressions**

Run:

```bash
.venv/bin/python -m pytest tests/test_direct_url_probe_script.py tests/test_hermes_launcher.py -q
.venv/bin/ruff format --check src tests scripts
.venv/bin/ruff check .
.venv/bin/mypy src
.venv/bin/python scripts/secret_scan.py
git diff --check
```

Expected: every command exits zero and the secret scanner reports no findings.

- [ ] **Step 5: Commit the command**

```bash
git add scripts/run_direct_url_probe.py tests/test_direct_url_probe_script.py
git commit -m "feat: add sanitized direct URL probe command"
```

### Task 3: Complete offline verification and publish the Draft PR update

**Files:**
- Modify only Task 1 or Task 2 files if a gate identifies a defect.

**Interfaces:**
- Consumes: completed diagnostic client and command.
- Produces: a clean pushed branch and passing Draft PR checks before live upload.

- [ ] **Step 1: Validate the real external manifest without network access**

Run:

```bash
.venv/bin/python scripts/run_direct_url_probe.py \
  --validate-only \
  --manifest /Users/chengpeng/VidsnapBenchmarks/agentic-video-20260812/manifests/smoke.jsonl \
  --output-dir /Users/chengpeng/VidsnapBenchmarks/agentic-video-20260812/results/direct-url-probe-20260813
```

Expected: `VALIDATED`, the fixed case/model/fps/hash/size, and no created output directory.

- [ ] **Step 2: Run the complete repository gate**

Run:

```bash
.venv/bin/ruff format --check src tests scripts
.venv/bin/ruff check .
.venv/bin/mypy src
.venv/bin/python -m pytest -q
.venv/bin/python -m build
.venv/bin/vidsnap conformance
.venv/bin/python scripts/secret_scan.py
git diff --check
```

Expected: every command exits zero, pytest has zero failures, build succeeds, conformance passes, and secret scan passes.

- [ ] **Step 3: Push and wait for Draft PR #8**

Run:

```bash
git push origin codex/agentic-benchmark
gh pr checks 8 --watch --interval 10
```

Expected: push succeeds and every required check passes. Do not merge or edit PR #7.

### Task 4: Run and audit exactly one live compatibility probe

**Files:**
- Write externally: `/Users/chengpeng/VidsnapBenchmarks/agentic-video-20260812/results/direct-url-probe-20260813/report.json`
- Do not create or modify repository files.

**Interfaces:**
- Consumes: passing local/CI gates, real smoke manifest, Hermes Token Plan configuration.
- Produces: one sanitized compatibility result, never a benchmark conclusion.

- [ ] **Step 1: Confirm the external result directory does not exist**

Run: `test ! -e /Users/chengpeng/VidsnapBenchmarks/agentic-video-20260812/results/direct-url-probe-20260813`

Expected: exit zero. If it exists, stop rather than overwrite it.

- [ ] **Step 2: Perform one upload and one model request through Hermes**

Run:

```bash
.venv/bin/python scripts/run_with_hermes_qwen.py -- \
  .venv/bin/python scripts/run_direct_url_probe.py \
  --manifest /Users/chengpeng/VidsnapBenchmarks/agentic-video-20260812/manifests/smoke.jsonl \
  --output-dir /Users/chengpeng/VidsnapBenchmarks/agentic-video-20260812/results/direct-url-probe-20260813
```

Expected on success: stdout contains only `PROBE_SUCCEEDED` and the external report path. On any bounded failure, write only `PROBE_FAILED` and its category, exit 1, and stop without another call.

- [ ] **Step 3: Audit the report and repository state**

Verify the fixed case/hash/size/model/fps, one model call, nonzero input tokens, measured latency, and successful upload/request statuses. Verify there is no answer, correctness, accuracy, conclusion, URL, object key, host, policy, signature, Authorization, raw request, raw response, or credential pattern. Run:

```bash
.venv/bin/python scripts/secret_scan.py
git status --short
git diff --check
```

If successful, report only that Direct URL transport compatibility is established and propose a separately tested adapter before rerunning the six-case smoke. If failed, report the bounded category and smallest next diagnostic step. Never claim Harness superiority and never run formal.
