#!/usr/bin/env python3
"""Verify UCI handshake for all playable catalog opponents."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from chess_harness.opponent_verify import verify_all_opponents

if __name__ == "__main__":
    sys.exit(verify_all_opponents())
