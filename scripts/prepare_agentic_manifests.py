#!/usr/bin/env python3
"""Build private hash-bound benchmark manifests from fixed public revisions."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from vidsnap.benchmark.manifest import FORMAL_SELECTION, SMOKE_SELECTION, prepare_manifests


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    if not args.root.is_absolute():
        parser.error("benchmark root must be absolute")
    try:
        paths = prepare_manifests(args.root)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(
        json.dumps(
            {
                "status": "PREPARED",
                "smoke_cases": sum(len(items) for items in SMOKE_SELECTION.values()),
                "formal_cases": sum(len(items) for items in FORMAL_SELECTION.values()),
                "smoke_manifest": str(paths["smoke"]),
                "formal_manifest": str(paths["formal"]),
            },
            ensure_ascii=True,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
