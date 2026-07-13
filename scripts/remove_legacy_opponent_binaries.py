#!/usr/bin/env python3
"""Remove legacy Patricia/Toledo binaries (MinimalChess is kept)."""

from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OPP_DIR = ROOT / "bin" / "opponents"

LEGACY_PATHS = (
    OPP_DIR / "patricia_v2.exe",
    OPP_DIR / "toledo-uci.js",
)


def main() -> int:
    removed = 0
    for path in LEGACY_PATHS:
        if not path.exists():
            continue
        path.unlink()
        print(f"Removed {path.relative_to(ROOT)}")
        removed += 1
    if not removed:
        print("No legacy Patricia/Toledo binaries found.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
