<!--
Thank you for contributing to VidSnap. Every pull request, whether written by a
human contributor or an agent, must reference an approved Task Contract from
PROJECT_STATE.md and carry its own evidence. Only the repository owner decides
whether a pull request is merged.
-->

## Task Contract

Task ID: <!-- the approved task card ID from PROJECT_STATE.md, e.g. GOV-001 -->

## Summary

<!-- What changed and why, in two or three sentences. -->

## Acceptance Evidence

<!-- Paste the evidence promised by the task card: the exact commands run, their
results, the exact test count, and any warnings or known limitations. Claim only
what you actually observed. -->

## Authority and Data Boundaries

- [ ] This PR contains no credentials, media/video, datasets, RunBundles, benchmark results, cookies, `.env` files, or raw provider requests/responses.
- [ ] This PR does not change GitHub rulesets, security-scanning switches, or the default branch; those require separate owner authorization recorded in PROJECT_STATE.md.
- [ ] Model keys, if any were used, came only from local environment variables and are not printed, read out, or committed anywhere in this PR.

## Verification

- [ ] `python -m pytest -q` passes locally.
- [ ] `ruff format --check .` and `ruff check .` pass.
- [ ] `mypy src` passes.
- [ ] `python -m build` succeeds and `vidsnap conformance` passes on the built wheel.
- [ ] `python scripts/secret_scan.py` reports no forbidden artifacts and `git diff --check` is clean.
- [ ] Every behavior change is covered by tests written before the implementation.
- [ ] No live benchmark was run, unless explicitly authorized by the task card; even when explicitly authorized, live benchmark results stay outside the repository and are not committed. This PR presents no Harness performance conclusions; infrastructure checks (CI, secret scan, build) are not performance evidence.

## Merge Authority

Opening this pull request, passing review, and green CI all together does not authorize merge. Only the repository owner decides whether and when to merge.
