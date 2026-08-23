# VidSnap Project State

This page is the single source of truth for project state: the current main objective, task cards, state transitions, and repository settings awaiting user authorization. Pull-request facts below are the read-only 2026-08-23 snapshot recorded in the approved implementation plan (`docs/superpowers/plans/2026-08-23-ai-native-development-protocol.md`); the PR #7/#8/#9 facts were verified by the main agent on 2026-08-23 through read-only GitHub queries, and no GitHub state was modified. No provider query was performed and none is required for this task.

## Current Main Objective

GOV-001 — establish the AI-native development protocol as the durable, testable collaboration loop for VidSnap. Exactly one main objective may be `IN_PROGRESS` at a time; GOV-001 is that objective. All other work remains `PROPOSED`, `BLOCKED`, or already `VERIFIED` or `RELEASED`.

## Task Contract: GOV-001

- Objective: Make the approved repo-native development protocol (`docs/superpowers/specs/2026-08-23-ai-native-development-protocol-design.md`) durable and testable: this canonical state page, protocol instructions in `AGENTS.md` and `CONTRIBUTING.md`, Task Contract issue and pull-request templates, base-agnostic pull-request CI triggering, and minimal security-maintenance files (`SECURITY.md`, `.github/dependabot.yml`).
- Non-goals: Do not modify or merge PRs #7, #8, or #9. No live benchmark and no new evaluation conclusions. No committing credentials, media, datasets, RunBundles, benchmark results, cookies, `.env` files, or raw provider requests/responses. No presenting infrastructure verification (CI, secret scan, build gates) as Harness performance conclusions. No users, authentication, databases, queues, frontend, or SaaS state. No GitHub ruleset, security-scan switch, or default-branch changes without separate user authorization. No action pinning, Python version matrix, or release workflow.
- Acceptance evidence: `PROJECT_STATE.md` exists with the main objective, all six task-contract fields, the seven allowed states, and a last-transition reason; `AGENTS.md` and `CONTRIBUTING.md` protocol additions are consistent with the design spec and preserve every existing rule; the issue form requires all six Task Contract fields and the PR template carries Task ID plus acceptance evidence; `ci.yml` triggers CI for pull requests against any base while existing push behavior is unchanged; `SECURITY.md` lists every forbidden artifact and `.github/dependabot.yml` covers pip and GitHub Actions weekly; the single stacked Draft PR passes the full existing CI; PRs #7, #8, and #9 remain unchanged and unmerged. Limitation: remote demonstration of the new pull_request event behavior cannot be claimed before integration — the bootstrap Draft PR may receive `offline-quality` only from its branch push because its base branch still has the old `pull_request` filter, and this limitation must be recorded rather than hidden.
- Authority / data / secret boundaries: Only the user authorizes repository settings and decides merge. Qoder CLI writes tests and repository files only in this worktree on `codex/ai-native-development-loop`. Codex reviews diffs and independently reruns gates. Model keys come only from local environment variables and are never read, printed, or committed. Forbidden artifacts: credentials, media/video, datasets, RunBundles, benchmark results, cookies, `.env` files, raw provider requests, raw provider responses.
- Owner / executor / reviewer: Owner and final merge authority: the user. Executor: Qoder CLI (Qwen3.8-Max or Kimi-K3). Reviewer: Codex. Independent verifier: CI. The executor never self-certifies completion; completion is decided by Codex review plus independent CI results and confirmed by the user's merge decision.
- Next human gate: Codex review of the current implementation batch (Batch A: canonical state and repository protocol).

Status: `IN_PROGRESS`

Last transition: 2026-08-23 — `APPROVED` → `IN_PROGRESS`, because the user approved the design spec and implementation plan and dispatched Batch A implementation to Qoder CLI.

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

Read-only 2026-08-23 snapshot. Do not merge, modify, or close any of these PRs in this task; they remain exactly as recorded until the user files a separate task card.

| PR | State | Base ← Head | Latest recorded CI |
| --- | --- | --- | --- |
| #7 | OPEN (not Draft) | `vidsnap_slim` ← `codex/video-harness-core` | success (recorded 2026-08-23) |
| #8 | OPEN Draft | `codex/video-harness-core` ← `codex/agentic-benchmark` | success (recorded 2026-08-23) |
| #9 | OPEN Draft | `codex/agentic-benchmark` ← `codex/plugin-video-harness-implementation` | success (recorded 2026-08-23) |

Do not merge #7, #8, or #9.

## Repository Settings Requiring User Authorization

The following settings are registered here as not authorized. No role may configure them until the user authorizes each item explicitly; authorized outcomes are then recorded back on this page.

- GitHub rulesets (branch protection and merge rules): not authorized.
- Security scanning switches (secret scanning, code scanning): not authorized.
- Default-branch change: not authorized.
