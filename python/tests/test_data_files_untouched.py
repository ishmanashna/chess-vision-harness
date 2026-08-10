"""Guard test: pytest never mutates shipped public-site/data/ files.

The ``isolate_shipped_data`` autouse fixture in conftest.py redirects all
snapshot/calibration writes into ``tmp_path``. This test double-checks that
after running the full snapshot-export path, the committed data files
remain byte-identical.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from chess_harness.snapshot_leaderboard import export_public_snapshots

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "public-site" / "data"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_snapshot_export_does_not_touch_data_files():
    """export_public_snapshots runs without corrupting shipped data files."""
    orig_leaderboard = _sha256(DATA / "leaderboard.json")
    orig_puzzles = _sha256(DATA / "puzzles_leaderboard.json")

    export_public_snapshots()

    assert _sha256(DATA / "leaderboard.json") == orig_leaderboard, (
        "leaderboard.json was mutated by export_public_snapshots"
    )
    assert _sha256(DATA / "puzzles_leaderboard.json") == orig_puzzles, (
        "puzzles_leaderboard.json was mutated by export_public_snapshots"
    )
