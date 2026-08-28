# MAINTAINERS.md

Working agreements for VidSnap maintainers. This document is public; nothing here overrides repository policy in AGENTS.md.

## AI-assisted development

- AI-assisted contributions are welcome, but they must be disclosed in the pull request description: which tools were used and what they produced.
- Disclosure is never approval. An AI-assisted change does not self-certify; it goes through the same review and gates as any other change. CI results are never rewritten or bypassed.

## Review and merge authority

- Human maintainers own review and merge decisions. No bot, automation, or AI agent may review-approve or merge on its own.
- A change merges only after review approval and passing gates. Merge authority rests with human maintainers; only they decide whether and when to merge.

## Release checklist

A release requires reproducible evidence from a clean checkout, recorded as commands and exit codes rather than pasted artifacts:

1. `ruff format --check src tests scripts` passes.
2. `ruff check .` passes.
3. `mypy src` passes.
4. `python -m pytest -q` passes.
5. `python -m build` passes.
6. `vidsnap conformance` passes.
7. `python scripts/secret_scan.py` passes.
8. `git diff --check` passes.

Do not commit RunBundles, datasets, benchmark results, media, or credentials as release evidence.

## Compatibility and deprecation

- Public contracts are typed; treat changes to them as breaking unless proven otherwise.
- To deprecate: announce in the changelog, keep the old behavior working for at least one minor release, and remove it only in a major release. Document every compatibility break in the release notes.

## Benchmark claims

- Any benchmark claim requires reproducible evidence: exact commands, environment, configuration, and a stated scope of limitations.
- A claim without a reproduction path is not publishable. Never commit raw datasets or result files; describe them and provide the commands.

## Secret and credential handling

- A secret — API key, token, cookie, or credential — must never enter the repository, including tests, fixtures, and logs. Keys come only from local environment variables.
- If a secret is found in history or a diff, stop, rotate the credential, and remove it from the change before merging.

## Security incidents

- Security issues are handled privately: report them privately to the maintainers, not in public issues, pull requests, or discussions.
- Coordinate a fix privately, release it, and publish disclosure only after a fixed version is available.
