# Security Policy

## Supported Versions

The latest released minor version line receives security fixes. Older versions are best-effort: they may receive fixes as time permits, but no guaranteed support. Please upgrade to the latest release before reporting a vulnerability.

## Reporting a Vulnerability

Report suspected vulnerabilities through GitHub private vulnerability reporting (the "Report a vulnerability" button on the repository's Security tab). This keeps the report private between the reporter and the maintainers.

Do not open public issues, pull requests, or discussions for security reports. If GitHub private vulnerability reporting is unavailable, you may open a minimal public issue titled "Private security contact requested" to ask maintainers for a private channel; that issue must not include any vulnerability details.

Please include a description of the issue, steps to reproduce, and the potential impact. Maintainers acknowledge and investigate reports as time permits. Practice responsible disclosure: give maintainers a reasonable window to investigate and ship a fix before any public discussion of vulnerability details.

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

## Trust Boundaries

This repository is a local-first harness: provider adapters and plugin code execute locally, in your own process and with your own permissions. They should be treated as trusted code. Allow-lists, bounded ports, and typed contracts constrain what the harness does with data; they do not make untrusted code safe to run. Only install provider adapters and plugins whose source you have reviewed and trust.

## Key Handling

Model keys are read from local environment variables and are never logged, persisted, or committed by repository tooling. Supply keys only through your local environment; do not place them in files, shell history, CI configuration, or issues. Keys entering the process through the environment are yours to manage and rotate.
