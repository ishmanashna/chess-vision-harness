"""Guard test: pytest never mutates shipped public-site/data/ or tracked calibration snapshots.

The ``isolate_shipped_data`` autouse fixture in conftest.py redirects all
snapshot/calibration writes into ``tmp_path``. This test double-checks that
after running the full snapshot-export path, committed data files remain
byte-identical.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from chess_harness.snapshot_leaderboard import export_public_snapshots

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "public-site" / "data"
CAL_RESULTS = ROOT / "elo_calibration" / "results"

GUARDED_PATHS = (
    DATA / "leaderboard.json",
    DATA / "puzzles_leaderboard.json",
    DATA / "identify_leaderboard.json",
    CAL_RESULTS / "merged_ratings.json",
    CAL_RESULTS / "accuracy_elo_map.json",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_snapshot_export_does_not_touch_data_files():
    """export_public_snapshots runs without corrupting shipped data files."""
    originals = {
        path: _sha256(path) for path in GUARDED_PATHS if path.is_file()
    }
    assert originals, "expected at least one guarded data file in the repo"

    export_public_snapshots()

    for path, digest in originals.items():
        assert _sha256(path) == digest, f"{path.relative_to(ROOT)} was mutated by export_public_snapshots"
