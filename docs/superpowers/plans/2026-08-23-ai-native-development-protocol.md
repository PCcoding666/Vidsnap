# VidSnap AI-native Development Protocol Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task, and follow test-driven development for every behavior change. Qoder CLI writes all implementation changes; Codex reviews each batch and independently verifies results.

**Goal:** Make the approved repo-native development protocol the durable, testable collaboration loop for VidSnap.

**Architecture:** Repository Markdown is the human-readable source of truth, GitHub templates collect the same Task Contract fields, and an offline pytest contract guards the required structure. The existing CI remains the independent verifier; this change broadens PR coverage and adds only minimal security-maintenance files.

**Tech Stack:** Markdown, GitHub Issue Forms YAML, GitHub Actions YAML, Dependabot YAML, Python 3.10 standard library, pytest.

**Spec:** `docs/superpowers/specs/2026-08-23-ai-native-development-protocol-design.md`

## Global Constraints

- Work only in `/Users/chengpeng/MyProject/Vidsnap-ai-native-development-loop` on `codex/ai-native-development-loop`.
- Qoder CLI must use `Qwen3.8-Max` or `Kimi-K3` for implementation changes.
- Qoder writes tests and repository files; Codex only orchestrates, reviews diffs, and runs independent verification.
- Use one branch and one final Draft PR, stacked on `codex/plugin-video-harness-implementation` and explicitly dependent on PR #9.
- Keep PRs #7, #8, and #9 unchanged and unmerged.
- One main objective may be `IN_PROGRESS`; Qoder may not self-certify completion.
- Each batch follows RED, GREEN, focused local gate, Codex review, and one batch commit before the next batch starts.
- Do not configure GitHub rulesets, security feature switches, or the default branch without separate user authorization.
- Do not add action pinning, a Python version matrix, a release workflow, live providers, or live benchmarks.
- Do not commit credentials, media, datasets, RunBundles, benchmark outputs, cookies, `.env` files, or raw provider requests/responses.
- Infrastructure verification must never be described as evidence that Harness outperforms Direct.
- The bootstrap Draft PR may receive `offline-quality` from its branch push because its base branch still has the old `pull_request` filter. Record this limitation; do not claim that the new PR event behavior was remotely demonstrated before integration.

---

### Task 1: Batch A — Canonical state and repository protocol

**Files:**
- Create: `tests/test_repository_governance.py`
- Create: `PROJECT_STATE.md`
- Modify: `AGENTS.md`
- Modify: `CONTRIBUTING.md`

**Interfaces:**
- Consumes: the approved design spec and the read-only 2026-08-23 snapshot of PRs #7, #8, and #9.
- Produces: the canonical `GOV-001` Task Contract and repository instructions consumed by all later batches.

- [ ] **Step 1: Have Qoder write the failing state-contract test**

Add this focused contract to `tests/test_repository_governance.py` before creating `PROJECT_STATE.md`:

```python
from pathlib import Path


ROOT = Path(__file__).parents[1]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_project_state_defines_the_approved_task_contract() -> None:
    state = _read("PROJECT_STATE.md")

    for heading in (
        "# VidSnap Project State",
        "## Current Main Objective",
        "## Task Contract: GOV-001",
        "## Allowed States",
        "## Active Stacked Pull Requests",
        "## Repository Settings Requiring User Authorization",
    ):
        assert heading in state
    for field in (
        "Objective:",
        "Non-goals:",
        "Acceptance evidence:",
        "Authority / data / secret boundaries:",
        "Owner / executor / reviewer:",
        "Next human gate:",
    ):
        assert field in state
    for status in (
        "PROPOSED",
        "APPROVED",
        "IN_PROGRESS",
        "READY_FOR_REVIEW",
        "VERIFIED",
        "BLOCKED",
        "RELEASED",
    ):
        assert f"`{status}`" in state
    assert state.count("Status: `IN_PROGRESS`") == 1
    for pull_request in ("#7", "#8", "#9"):
        assert pull_request in state
    assert "Do not merge" in state
```

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```bash
env -u PYTHONPATH .venv/bin/python -m pytest tests/test_repository_governance.py -q
```

Expected: FAIL with `FileNotFoundError` for `PROJECT_STATE.md`. A syntax error or an unrelated import failure is not an acceptable RED result.

- [ ] **Step 3: Have Qoder create the minimal canonical state page**

Create `PROJECT_STATE.md` with the exact headings and field labels tested above. Record:

- `GOV-001` as the only `IN_PROGRESS` objective;
- user as owner and final merge authority, Qoder CLI as executor, Codex as reviewer, and CI as independent verifier;
- the approved non-goals and forbidden-data boundary;
- the seven allowed statuses and a last-transition reason;
- ruleset, secret/code scanning switches, and default-branch change as not authorized;
- PR #7: OPEN, not Draft, `vidsnap_slim` ← `codex/video-harness-core`, latest recorded CI success;
- PR #8: OPEN Draft, `codex/video-harness-core` ← `codex/agentic-benchmark`, latest recorded CI success;
- PR #9: OPEN Draft, `codex/agentic-benchmark` ← `codex/plugin-video-harness-implementation`, latest recorded CI success;
- an explicit `Do not merge` statement for all three existing PRs in this task;
- the next human gate as Codex review of the current implementation batch.

- [ ] **Step 4: Have Qoder append protocol instructions without removing existing rules**

Append `## AI-native Development Protocol` to `AGENTS.md` and `CONTRIBUTING.md`. Both additions must require reading `PROJECT_STATE.md` first, one main objective, the seven-state vocabulary, Qoder implementation, Codex review, CI verification, human merge authority, and the prohibited-artifact boundary. Preserve every existing Harness rule.

- [ ] **Step 5: Run the focused GREEN gate**

Run:

```bash
env -u PYTHONPATH .venv/bin/python -m pytest tests/test_repository_governance.py -q
.venv/bin/ruff format --check tests/test_repository_governance.py
.venv/bin/ruff check tests/test_repository_governance.py
git diff --check
```

Expected: the governance test passes and every command exits 0.

- [ ] **Step 6: Stop for Codex review, then commit Batch A**

Codex reviews the actual diff against Task 1 and reruns the focused gate. Only after review passes:

```bash
git add PROJECT_STATE.md AGENTS.md CONTRIBUTING.md tests/test_repository_governance.py
git commit -m "docs: establish repository development protocol"
```

---

### Task 2: Batch B — Task Contract issue and pull-request templates

**Files:**
- Modify: `tests/test_repository_governance.py`
- Create: `.github/ISSUE_TEMPLATE/task.yml`
- Create: `.github/ISSUE_TEMPLATE/config.yml`
- Create: `.github/PULL_REQUEST_TEMPLATE.md`

**Interfaces:**
- Consumes: the six grouped Task Contract fields defined by `PROJECT_STATE.md`.
- Produces: GitHub intake templates that collect the same fields and preserve human merge authority.

- [ ] **Step 1: Have Qoder add failing template-contract tests**

Add tests that read the three files before they exist. For `task.yml`, assert the field IDs `objective`, `non_goals`, `acceptance_evidence`, `boundaries`, `roles`, and `next_human_gate`; isolate each field block and require `required: true`. For `config.yml`, require `blank_issues_enabled: false`. For the PR template, require these headings and statements:

```python
def test_task_issue_form_requires_every_contract_field() -> None:
    form = _read(".github/ISSUE_TEMPLATE/task.yml")
    field_ids = (
        "objective",
        "non_goals",
        "acceptance_evidence",
        "boundaries",
        "roles",
        "next_human_gate",
    )
    for index, field_id in enumerate(field_ids):
        block = form.split(f"id: {field_id}", 1)[1]
        if index + 1 < len(field_ids):
            block = block.split(f"id: {field_ids[index + 1]}", 1)[0]
        assert "required: true" in block
    assert "blank_issues_enabled: false" in _read(
        ".github/ISSUE_TEMPLATE/config.yml"
    )


def test_pull_request_template_preserves_evidence_and_human_gates() -> None:
    template = _read(".github/PULL_REQUEST_TEMPLATE.md")
    for required in (
        "## Task Contract",
        "Task ID",
        "## Acceptance Evidence",
        "## Authority and Data Boundaries",
        "## Verification",
        "No live benchmark",
        "does not authorize merge",
    ):
        assert required in template
```

- [ ] **Step 2: Run the focused test and verify RED**

Run the governance test. Expected: FAIL with `FileNotFoundError` for `.github/ISSUE_TEMPLATE/task.yml`, not an unrelated failure.

- [ ] **Step 3: Have Qoder create minimal GitHub templates**

Create one Task Contract issue form with all six required fields, disable blank issues in `config.yml`, and create one PR template with Task ID, acceptance evidence, boundaries, verification checklist, no-live-benchmark assertion, and an explicit statement that opening or passing the PR does not authorize merge. Do not add automation or external links that are not already known.

- [ ] **Step 4: Run the focused GREEN gate**

Run the same four focused commands from Task 1 Step 5. Expected: all pass.

- [ ] **Step 5: Stop for Codex review, then commit Batch B**

```bash
git add tests/test_repository_governance.py .github/ISSUE_TEMPLATE .github/PULL_REQUEST_TEMPLATE.md
git commit -m "docs: add task and pull request contracts"
```

---

### Task 3: Batch C — PR CI coverage and security maintenance files

**Files:**
- Modify: `tests/test_repository_governance.py`
- Modify: `.github/workflows/ci.yml`
- Create: `SECURITY.md`
- Create: `.github/dependabot.yml`

**Interfaces:**
- Consumes: the existing `offline-quality` job and prohibited-artifact boundary.
- Produces: branch-agnostic future PR triggering, a private-reporting policy, and weekly pip/GitHub Actions update checks.

- [ ] **Step 1: Have Qoder add failing CI and security-contract tests**

Add these standard-library text tests:

```python
def test_ci_runs_for_pull_requests_against_any_base() -> None:
    workflow = _read(".github/workflows/ci.yml")
    push = workflow.split("  push:", 1)[1].split("  pull_request:", 1)[0]
    pull_request = workflow.split("  pull_request:", 1)[1].split(
        "\n\npermissions:", 1
    )[0]

    assert "vidsnap_slim" in push
    assert '"codex/**"' in push
    assert "branches:" not in pull_request


def test_security_policy_names_private_reporting_and_forbidden_artifacts() -> None:
    policy = _read("SECURITY.md").lower()
    for required in (
        "credential",
        "video",
        "dataset",
        "runbundle",
        "benchmark result",
        ".env",
        "cookie",
        "raw provider request",
        "raw provider response",
    ):
        assert required in policy
    assert "github" in policy
    assert "private" in policy
    assert "@" not in policy


def test_dependabot_covers_python_and_github_actions_weekly() -> None:
    config = _read(".github/dependabot.yml")

    assert 'package-ecosystem: "pip"' in config
    assert 'package-ecosystem: "github-actions"' in config
    assert config.count('interval: "weekly"') == 2
```

- [ ] **Step 2: Run the focused test and verify RED**

Expected: FAIL first because the current PR trigger contains `branches: [vidsnap_slim]`; after that assertion is implemented, missing security files must also remain capable of failing the test.

- [ ] **Step 3: Have Qoder make the minimal CI and security changes**

Change only the workflow trigger from the base-limited mapping to an unrestricted `pull_request:` trigger. Preserve the push branches and every existing job step. Create `SECURITY.md` using GitHub private vulnerability reporting as the preferred channel and explicitly telling reporters not to disclose details publicly if that interface is unavailable. Create two weekly Dependabot entries for pip and GitHub Actions at directory `/`.

- [ ] **Step 4: Run the focused GREEN gate**

Run the same four focused commands from Task 1 Step 5. Expected: all pass.

- [ ] **Step 5: Stop for Codex review, then commit Batch C**

```bash
git add tests/test_repository_governance.py .github/workflows/ci.yml SECURITY.md .github/dependabot.yml
git commit -m "ci: add repository governance safeguards"
```

---

### Task 4: Full verification and stacked Draft PR

**Files:**
- Modify: `PROJECT_STATE.md`

**Interfaces:**
- Consumes: the three reviewed batch commits and full local gate output.
- Produces: one stacked Draft PR and an accurate state/evidence record; no merge.

- [ ] **Step 1: Run the complete local gate before publishing**

```bash
.venv/bin/ruff format --check src tests scripts
.venv/bin/ruff check .
.venv/bin/mypy src
env -u PYTHONPATH .venv/bin/python -m pytest -q
env -u PYTHONPATH .venv/bin/python -m build
.venv/bin/vidsnap conformance
env -u PYTHONPATH .venv/bin/python scripts/secret_scan.py
git diff --check
```

Expected: every command exits 0. Record exact test count and any warnings without suppressing them.

- [ ] **Step 2: Push and create one stacked Draft PR**

Push `codex/ai-native-development-loop` and create a Draft PR with base `codex/plugin-video-harness-implementation`, title `chore: establish AI-native development loop`, and a description that states it is stacked on and depends on #9. State that it changes only internal/open-source development governance, contains no live benchmark conclusions or prohibited artifacts, and must not be merged without user approval.

- [ ] **Step 3: Update the canonical state with real publication evidence**

After the Draft PR exists, have Qoder update `GOV-001` to `READY_FOR_REVIEW`, add the real PR URL, local gate evidence, and the bootstrap CI-event limitation. Run:

```bash
env -u PYTHONPATH .venv/bin/python -m pytest tests/test_repository_governance.py -q
env -u PYTHONPATH .venv/bin/python scripts/secret_scan.py
git diff --check
```

Commit and push only this state update:

```bash
git add PROJECT_STATE.md
git commit -m "docs: record governance review state"
git push
```

- [ ] **Step 4: Wait for remote CI and report facts only**

Confirm the latest `offline-quality` check applies to the latest branch SHA and report whether it came from `push` or `pull_request`. If it fails, keep `GOV-001` at `READY_FOR_REVIEW`, return the relevant batch to Qoder, and repeat verification. If it passes, update the state to `VERIFIED` only after Codex confirms all acceptance evidence. Do not merge and do not run live benchmark.
