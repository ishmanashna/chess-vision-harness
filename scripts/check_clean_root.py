#!/usr/bin/env python3
"""Fail if repo root contains any file that is not Markdown."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

ALLOWED_MD = {
    "AGENTS.md",
    "ARCHITECTURE.md",
    "NOTICE.md",
    "ORCHESTRATOR.md",
    "PRODUCT.md",
    "README.md",
}


def main() -> int:
    violations: list[str] = []
    for path in sorted(ROOT.iterdir()):
        if path.is_dir():
            continue
        if path.suffix.lower() != ".md" or path.name not in ALLOWED_MD:
            violations.append(path.name)

    if not violations:
        print(f"Root layout OK ({len(ALLOWED_MD)} markdown files, directories only otherwise).")
        return 0

    print("Root layout FAILED — non-markdown or unexpected files at repo root:\n")
    for name in violations:
        print(f"  {name}")
    print("\nSee ARCHITECTURE.md and docs/plan.md.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
