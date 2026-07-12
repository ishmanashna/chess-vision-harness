#!/usr/bin/env python3
"""Operator script: hard-reset harness runtime data. See README (Operator commands)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import chess_harness.bootstrap  # noqa: F401

from chess_harness.harness_reset import harness_reset

if __name__ == "__main__":
    if "--yes" not in sys.argv:
        sys.exit(harness_reset(confirm=False))
    sys.exit(harness_reset(confirm=True))
