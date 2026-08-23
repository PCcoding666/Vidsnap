# Security Policy

## Reporting a Vulnerability

Report suspected vulnerabilities through GitHub private vulnerability reporting (the "Report a vulnerability" button on the repository's Security tab). This keeps the report private between the reporter and the maintainers.

Do not open public issues, pull requests, or discussions for security reports. If GitHub private vulnerability reporting is unavailable, you may open a minimal public issue titled "Private security contact requested" to ask maintainers for a private channel; that issue must not include any vulnerability details.

Please include a description of the issue, steps to reproduce, and the potential impact. Maintainers acknowledge and investigate reports as time permits.

## Prohibited Artifacts

The following artifacts must never be committed to this repository or attached to reports, issues, or pull requests:

- credentials of any kind (API keys, tokens, passwords)
- media and video files
- datasets
- RunBundles
- benchmark results
- cookies
- `.env` files
- raw provider requests
- raw provider responses

If sensitive material is needed to reproduce an issue, describe it instead of attaching the artifact.

## Scope

This repository is a local-first harness. Model keys come only from local environment variables and are never logged, persisted, or committed by repository tooling.
