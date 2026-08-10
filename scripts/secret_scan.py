"""Fail CI when tracked text contains a high-confidence credential literal."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9._-]{16,}\b"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"(?i)(?:api[_-]?key|token|secret)\s*[:=]\s*['\"][A-Za-z0-9._-]{16,}"),
)
_SKIP_SUFFIXES = {".ico", ".jpg", ".jpeg", ".png", ".whl", ".gz"}


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    tracked = subprocess.run(
        ["git", "ls-files"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    findings: list[str] = []
    for relative_name in tracked:
        path = root / relative_name
        if path.suffix.lower() in _SKIP_SUFFIXES or not path.is_file():
            continue
        content = path.read_text(encoding="utf-8", errors="ignore")
        if any(pattern.search(content) for pattern in _PATTERNS):
            findings.append(relative_name)
    if findings:
        print("potential secrets found in tracked files:", file=sys.stderr)
        print("\n".join(findings), file=sys.stderr)
        return 1
    print("secret scan passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
