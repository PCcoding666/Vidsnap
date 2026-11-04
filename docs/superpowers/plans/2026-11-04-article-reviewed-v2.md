# Reviewed article v2 Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans for this approved implementation.

**Goal:** Add opt-in visual review, targeted sampling and one local editorial revision.
**Architecture:** Versioned recipe policy over typed model/media ports and kernel budgets.
**Tech Stack:** Python, Pydantic, pytest, existing synthesis/media ports.
**Spec:** docs/superpowers/specs/2026-11-04-article-reviewed-v2.md

## Global Constraints

Follow AGENTS.md, keep v1 default and public formats compatible, no live calls or
user-media mutations. Tests precede behavior changes. Baseline: 984 passed, one
README navigation placement failure; repair actual docs, never weaken the gate.

## Review Focus

Reject incomplete visual coverage, invalid citations and patches outside flagged
sections. Bound calls and resampling. Preserve drafts on failure. Review artifacts
must be validated output, not raw provider traffic. No vacuous success.

### Task 1: Bounded model steps and dense sampling

- [ ] Add offline failing tests for typed bounded model steps and window sampling.
- [ ] Implement additive kernel model-step interface and v2 sampling plugin.
- [ ] Verify targeted tests pass; commit.

Files: tasks/base.py, runtime/kernel.py, plugins/builtin/sample_evidence.py,
tests/recipes/test_article_reviewed.py. RED: missing interfaces. GREEN: typed
steps account usage and failures, dense windows do not depend on global candidates.

### Task 2: Versioned reviewed article workflow

- [ ] Add failing integration tests for review, patch, failures and retained drafts.
- [ ] Add strict review/patch schemas and v2 recipe adapter/policy.
- [ ] Integrate explicit runner/CLI recipe version while preserving v1.
- [ ] Verify targeted tests and commit.

Files: contracts/article_review.py, recipes/article_review.py, recipes/article.py,
cli.py, tests/recipes/test_article_reviewed.py. RED: missing v2. GREEN: real image
parts in review, reserved frames, one patch, final review, truthful terminal state.

### Task 3: Documentation and verification

- [ ] Document CLI, artifacts, budgets and limitations; fix README navigation.
- [ ] Run all eight exact public gates in isolated venv.
- [ ] Fresh whole-branch review, address substantive findings, rerun gates as needed.
- [ ] Commit and report branch, usage and offline validation limits.

Files: README.md, docs/recipes.md (or existing recipe guide), tests as needed.
