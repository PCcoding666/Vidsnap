<!--
Thank you for contributing to VidSnap. Keep this pull request focused on one
change, verify it locally, and complete every checklist before requesting
review.
-->

# Summary

<!-- What changed and why, in two or three sentences. -->

- [ ] This pull request is focused: one cohesive change, no drive-by refactors or unrelated fixes.
- [ ] It links to the related issue or discussion: <!-- issue number -->
- [ ] It stays within project scope: a local, single-user harness for bounded video analysis runs.

## Tests

<!-- Paste the exact commands you ran and what you observed. Claim only results you actually saw. -->

- [ ] `python -m pytest -q` passes (tests are offline and deterministic: no network, no model calls, no real media).
- [ ] `ruff format --check .` and `ruff check .` pass.
- [ ] `mypy src` passes.
- [ ] `python -m build` succeeds.
- [ ] `vidsnap --help` and `vidsnap conformance` pass on the built wheel.
- [ ] `python scripts/secret_scan.py` reports no forbidden artifacts and `git diff --check` is clean.
- [ ] Every behavior change is covered by tests added or updated in this pull request.

Evidence:

```
<!-- commands and observed output -->
```

## Security

- [ ] This pull request contains no credentials, API keys, cookies, `.env` files, media/video files, datasets, RunBundles, benchmark results, or raw provider requests/responses.
- [ ] Model keys, if any were used, came only from local environment variables and were never logged, embedded in fixtures or traces, or committed.
- [ ] No gate, conformance check, or security tooling was weakened, bypassed, or rewritten to make this change pass.
- [ ] User data and recorded fixtures were not modified, moved, or deleted as a side effect of this change.

## Compatibility

- [ ] Public contracts, recipe and RunBundle formats, CLI behavior, and conformance checks are unchanged; any change to them is an explicit, versioned, tested update.
- [ ] Any contract or format change documents its migration path and includes tests.
- [ ] The change does not add out-of-scope components (no SaaS, accounts, databases, queues, frontend code, or job/history state).
