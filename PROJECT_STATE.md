# VidSnap Project State

This page is the single source of truth for project state: the current main objective, task cards, state transitions, and repository settings awaiting user authorization. Pull-request facts below combine the read-only 2026-08-23 snapshot recorded in the approved implementation plan (`docs/superpowers/plans/2026-08-23-ai-native-development-protocol.md`) with later 2026-08-23 facts: the PR #7/#8/#9 facts were verified by the main agent on 2026-08-23 through read-only GitHub queries, the PR #10 facts (real URL, base/head branches, both GitHub Actions runs, and mergeState) were reported from live GitHub state on 2026-08-23, and the later 2026-08-23 STACK-001 verification facts for PR #10 (head `13a49b3b`, push run `32645998762` and `pull_request` run `32645998504` both success, and the combined `vidsnap_slim` + #10 merge-tree local gate with 333 passed) were also recorded from live state. The Active Stacked Pull Requests table now records the integration-progress facts of the user-authorized STACK-001 sequence: PRs #7, #8, and #9 are merged and PR #10 remains open, Ready, and eligible for the already user-authorized normal merge. PRs #7, #8, and #9 were not modified during GOV-001; the branch push and the Draft PR #10 creation were GOV-001-authorized release actions. No provider query was performed and none is required for this task.

## Current Main Objective

STACK-001 — execute the user-authorized sequential integration of PRs #7, #8, #9, and #10 into `vidsnap_slim`. At most one main objective may be active at a time; STACK-001 is that objective, currently `VERIFIED`. GOV-001 is preserved below as a historical `VERIFIED` task and its recorded facts are not rewritten. All other work remains `PROPOSED`, `BLOCKED`, or already `VERIFIED` or `RELEASED`.

## Task Contract: GOV-001

- Objective: Make the approved repo-native development protocol (`docs/superpowers/specs/2026-08-23-ai-native-development-protocol-design.md`) durable and testable: this canonical state page, protocol instructions in `AGENTS.md` and `CONTRIBUTING.md`, Task Contract issue and pull-request templates, base-agnostic pull-request CI triggering, and minimal security-maintenance files (`SECURITY.md`, `.github/dependabot.yml`).
- Non-goals: Do not modify or merge PRs #7, #8, or #9. No live benchmark and no new evaluation conclusions. No committing credentials, media, datasets, RunBundles, benchmark results, cookies, `.env` files, or raw provider requests/responses. No presenting infrastructure verification (CI, secret scan, build gates) as Harness performance conclusions. No users, authentication, databases, queues, frontend, or SaaS state. No GitHub ruleset, security-scan switch, or default-branch changes without separate user authorization. No action pinning, Python version matrix, or release workflow.
- Acceptance evidence: `PROJECT_STATE.md` exists with the main objective, all six task-contract fields, the seven allowed states, and a last-transition reason; `AGENTS.md` and `CONTRIBUTING.md` protocol additions are consistent with the design spec and preserve every existing rule; the issue form requires all six Task Contract fields and the PR template carries Task ID plus acceptance evidence; `ci.yml` triggers CI for pull requests against any base while existing push behavior is unchanged; `SECURITY.md` lists every forbidden artifact and `.github/dependabot.yml` covers pip and GitHub Actions weekly; the single stacked Draft PR passes the full existing CI; PRs #7, #8, and #9 remain unchanged and unmerged. The earlier bootstrap limitation — that the new `pull_request` event behavior could only be verified after integration — was refuted on 2026-08-23: the `pull_request` event actually fired on Draft PR #10 and its run completed success at SHA `ce53a8ee73646520985d960e987565cf3840e4bf` (see GOV-001 Progress Evidence).
- Authority / data / secret boundaries: Only the user authorizes repository settings and decides merge. Qoder CLI writes tests and repository files only in this worktree on `codex/ai-native-development-loop`. Codex reviews diffs and independently reruns gates. Model keys only come from local environment variables, are read only by the authorized local provider runtime, and are never printed, logged, persisted, or committed. Forbidden artifacts: credentials, media/video, datasets, RunBundles, benchmark results, cookies, `.env` files, raw provider requests, raw provider responses.
- Owner / executor / reviewer: Owner and final merge authority: the user. Executor: Qoder CLI (Qwen3.8-Max or Kimi-K3). Reviewer: Codex. Independent verifier: CI. The executor never self-certifies completion; completion is decided by Codex review plus independent CI results and confirmed by the user's merge decision.
- Next human gate: the user reviews GOV-001 and decides whether to merge Draft PR #10. No role merges automatically; this task never merges #10.

Status: `VERIFIED`

Last transition: 2026-08-23 — `READY_FOR_REVIEW` → `VERIFIED`, because Codex review passed and both classes of CI on the latest implementation/review SHA `bc0bab5f4a569fede752963c2f36e9d7f8b44bf3` completed success: the push run (https://github.com/PCcoding666/Vidsnap/actions/runs/32636035016) and the `pull_request` run (https://github.com/PCcoding666/Vidsnap/actions/runs/32636037253). Draft PR #10 remains OPEN Draft with mergeState CLEAN; PRs #7, #8, and #9 remain OPEN with unchanged base/head/draft status. The user still decides whether to merge; this task never merges #10.

## GOV-001 Progress Evidence

Recorded 2026-08-23. The facts below justify the `READY_FOR_REVIEW` → `VERIFIED` transition recorded above.

- Batch A — commit `9dbf524e` (`docs: establish repository development protocol`): canonical state page and protocol instructions; committed after Codex focused review.
- Batch B — commit `d875cd2e` (`docs: add task and pull request contracts`): Task Contract issue form and pull-request template; committed after Codex focused review.
- Batch C — commit `18becd97` (`ci: add repository governance safeguards`): base-agnostic pull-request CI triggering plus `SECURITY.md` and `.github/dependabot.yml`; committed after Codex focused review.
- Full local gate, run 2026-08-23 in this worktree, all green: `ruff format --check src tests scripts`, `ruff check .`, `mypy src` (60 source files), `python -m pytest -q` (328 passed), sdist/wheel build, `vidsnap conformance`, secret scan, and git diff check.
- Draft PR #10 (https://github.com/PCcoding666/Vidsnap/pull/10) is really open: state OPEN Draft, base `codex/plugin-video-harness-implementation`, head `codex/ai-native-development-loop`.
- Push CI on SHA `ce53a8ee73646520985d960e987565cf3840e4bf` succeeded: run https://github.com/PCcoding666/Vidsnap/actions/runs/32635349354.
- The `pull_request` event actually fired on the same SHA and its run completed success: run https://github.com/PCcoding666/Vidsnap/actions/runs/32635385487 (conclusion success, updated 2026-08-23T11:02:40Z). This refutes the earlier bootstrap limitation that the new `pull_request` behavior could only be verified after integration; the old "not observable before integration" claim is removed.
- Latest implementation/review SHA `bc0bab5f4a569fede752963c2f36e9d7f8b44bf3` on Draft PR #10 is independently verified: the push run https://github.com/PCcoding666/Vidsnap/actions/runs/32636035016 completed success and the `pull_request` run https://github.com/PCcoding666/Vidsnap/actions/runs/32636037253 completed success (both recorded 2026-08-23); PR #10 mergeState is CLEAN.
- This metadata-only `VERIFIED` state commit changes no production code or tests; it must still keep GitHub checks green, and the latest check details are tracked on PR #10 itself rather than by committing further run-ID updates here.
- Still true: PRs #7, #8, and #9 remain unchanged and unmerged, and this task does not merge #10.

## Task Contract: STACK-001

- Objective: Execute the sequential integration of PRs #7, #8, #9, and #10 into `vidsnap_slim`, in that order, using normal merge commits to preserve stacked ancestry. Retarget #8, #9, and #10 to `vidsnap_slim` only after their predecessor merges; mark Draft PRs ready for review only when their turn arrives; require latest-head CI success before each merge.
- Non-goals: No squash, no rebase, no force-push, no branch deletion; source branches and worktrees are kept. No live benchmark, no provider call, no credential access. No default-branch rename, no ruleset change, no security-setting change, and no unrelated code change. No claiming any PR has merged before it actually has.
- Acceptance evidence: On 2026-08-23 the user explicitly approved the sequential integration of PRs #7, #8, #9, and #10 into `vidsnap_slim`. Each step is a normal merge commit performed only after that PR's latest-head CI succeeds; retargeting of #8, #9, and #10 and draft-ready changes happen only in sequence as each turn arrives; when the sequence completes, `vidsnap_slim` history shows the four merge commits in order and this page's Active Stacked Pull Requests snapshot is updated with the merged facts.
- Authority / data / secret boundaries: Codex may perform GitHub metadata operations (retargeting base branches, marking Draft PRs ready) and the merge operations under this authorization. Qoder is the only code/file implementation worker if a conflict or fix is needed. CI is the independent verifier and its results are never rewritten or bypassed. No credential access and no provider API calls at any point. Forbidden artifacts remain forbidden: credentials, media/video, datasets, RunBundles, benchmark results, cookies, `.env` files, raw provider requests, raw provider responses.
- Owner / executor / reviewer: Owner and final authority: the user. GitHub metadata and merge operations: Codex, under the 2026-08-23 user authorization. Code/file implementation worker (only if a conflict or fix is needed): Qoder CLI. Independent verifier: CI. Only the user decides anything outside this authorized sequence.
- Next human gate: none for the already authorized normal sequence. Stop and request direction on unexpected conflict, failing CI that requires scope expansion, or any unexpected diff.

STACK-001 Progress Evidence (recorded 2026-08-23 from verified live GitHub facts):

- PR #7 merged into `vidsnap_slim` as a normal merge commit `d4ac1e96`.
- PR #8 merged into `vidsnap_slim` as a normal merge commit `887c25aa` after review fixes, with latest-head CI success before the merge.
- PR #9 merged into `vidsnap_slim` as a normal merge commit `04546ad9` after four reviewed fixes, with latest-head CI success before the merge.
- All three source branches and their worktrees remain; no squash, rebase, force-push, or branch deletion occurred.
- PR #10 is OPEN and Ready (no longer Draft), retargeted to base `vidsnap_slim` with head `codex/ai-native-development-loop` at `13a49b3b`, mergeState CLEAN, not yet merged. On head `13a49b3b` the GitHub push CI run https://github.com/PCcoding666/Vidsnap/actions/runs/32645998762 completed success and the `pull_request` CI run https://github.com/PCcoding666/Vidsnap/actions/runs/32645998504 completed success (both recorded 2026-08-23).
- Combined local gate, run 2026-08-23 on the actual `vidsnap_slim` + PR #10 merge tree, all green: `python -m pytest -q` (333 passed) plus `ruff format --check`, `ruff check`, `mypy src`, sdist/wheel build, `vidsnap conformance`, secret scan, and git diff check.
- Copilot could not review PR #10 due to quota; that absence is recorded for truthfulness and does not constitute any approval from Copilot. Codex independently reviewed the actual PR #10 diff and found no blocking issue.
- PR #10 is therefore eligible for the already user-authorized normal merge into `vidsnap_slim`; the merge itself is not part of this state update and has not happened. `RELEASED` is not claimed.

Status: `VERIFIED`

Last transition: 2026-08-23 — `READY_FOR_REVIEW` → `VERIFIED`, because PR #10 at head `13a49b3b` passed both classes of GitHub CI (push run `32645998762` and `pull_request` run `32645998504`, both success), the combined `vidsnap_slim` + #10 merge-tree local gate passed with 333 tests plus format/lint/mypy/build/conformance/secret-scan/diff checks, and Codex independently reviewed the actual diff with no blocking issue; Copilot could not review due to quota, which is recorded and does not constitute any approval from Copilot. PR #10 remains OPEN and Ready with mergeState CLEAN and is eligible for the already user-authorized normal merge; this transition does not merge #10 and does not claim `RELEASED`.

## Allowed States

Seven states only; no other values are permitted:

- `PROPOSED`: task card drafted, awaiting user approval of direction.
- `APPROVED`: user approved; executor assigned.
- `IN_PROGRESS`: executor implementing in TDD batches in an isolated worktree; ordinary review rework also returns here.
- `READY_FOR_REVIEW`: all batches complete, full local gate green, single Draft PR open, awaiting CI.
- `VERIFIED`: Codex batch reviews passed and Draft PR CI is green; awaiting the user's merge decision.
- `BLOCKED`: a real external dependency, permission, or user decision is required; the reason and unblock condition must be recorded. Ordinary review failure does not enter this state.
- `RELEASED`: the task card's predeclared final integration goal was reached with user approval and long-term facts are archived on GitHub.

Every transition is written back to this page with its reason.

## Active Stacked Pull Requests

Integration-progress snapshot recorded 2026-08-23 from verified live GitHub facts. The historical GOV-001-era instruction "Do not merge #7, #8, or #9" (and the note that merging #10 remained the user's undecided decision) is superseded for STACK-001: on 2026-08-23 the user explicitly authorized the sequential integration of #7, #8, #9, and #10 into `vidsnap_slim`, as recorded in Task Contract: STACK-001. PRs #7, #8, and #9 have now merged; only #10 remains open.

| PR | State | Base ← Head | Latest recorded CI |
| --- | --- | --- | --- |
| #7 | MERGED | `vidsnap_slim` ← `codex/video-harness-core` | merged via normal merge commit `d4ac1e96` (recorded 2026-08-23) |
| #8 | MERGED | `vidsnap_slim` ← `codex/agentic-benchmark` | merged via normal merge commit `887c25aa` after review fixes and latest-head CI success (recorded 2026-08-23) |
| #9 | MERGED | `vidsnap_slim` ← `codex/plugin-video-harness-implementation` | merged via normal merge commit `04546ad9` after four reviewed fixes and latest-head CI success (recorded 2026-08-23) |
| #10 | OPEN (Ready, not Draft) | `vidsnap_slim` ← `codex/ai-native-development-loop` at `13a49b3b` | push run `32645998762` and `pull_request` run `32645998504` both success on head `13a49b3b`; mergeState CLEAN; eligible for the already user-authorized normal merge, source branch and worktree kept (recorded 2026-08-23) |

Integration order: #7 → #8 → #9 → #10, each as a normal merge commit into `vidsnap_slim`, performed only after that PR's latest-head CI succeeds. #7, #8, and #9 are integrated in order; #10 is the remaining step: latest-head CI on `13a49b3b` succeeded and Codex review found no blocking issue, so it is eligible for the already user-authorized normal merge and stays OPEN until that merge happens. Source branches and worktrees are kept; no squash, rebase, force-push, or branch deletion.

## Repository Settings Requiring User Authorization

The following settings are registered here as not authorized. No role may configure them until the user authorizes each item explicitly; authorized outcomes are then recorded back on this page.

- GitHub rulesets (branch protection and merge rules): not authorized.
- Security scanning switches (secret scanning, code scanning): not authorized.
- Default-branch change: not authorized.
