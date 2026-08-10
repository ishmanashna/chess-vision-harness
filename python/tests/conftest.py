"""Shared test constants and fixtures."""

import os
import sys
from pathlib import Path

import pytest

PYTHON_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = PYTHON_ROOT.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"

sys.path.insert(0, str(PYTHON_ROOT / "src"))

STOCKFISH_BIN = REPO_ROOT / "bin" / "stockfish-windows-x86-64.exe"

os.environ.setdefault("STOCKFISH_PATH", str(STOCKFISH_BIN))
os.environ.setdefault("MODELS_FILE", str(FIXTURES / "models.json"))
os.environ.setdefault("OPPONENTS_FILE", str(REPO_ROOT / "config" / "opponents.json"))

DEFAULT_MODEL = "composer-2.5"

# Opponents in the committed catalog (updated when ladder is pruned)
LOW_OPPONENT = "stockfish-handicap:noise10"
MID_OPPONENT = "stockfish-handicap:noise22"
UNCALIBRATED_OPPONENT = "stockfish-handicap:noise7"


@pytest.fixture(autouse=True)
def restore_models_fixture():
    path = FIXTURES / "models.json"
    original = path.read_bytes()
    yield
    path.write_bytes(original)


@pytest.fixture(autouse=True)
def isolate_shipped_data(tmp_path, monkeypatch):
    """Redirect snapshot and calibration writes into tmp_path.

    Prevents the test suite from ever touching ``public-site/data/`` or
    ``elo_calibration/results/`` — the two directories that ship to production.
    """
    snap_out = tmp_path / "leaderboard.json"
    puzzle_out = tmp_path / "puzzles_leaderboard.json"
    monkeypatch.setattr(
        "chess_harness.snapshot_leaderboard.default_output_path",
        lambda: snap_out,
    )
    monkeypatch.setattr(
        "chess_harness.snapshot_leaderboard.default_puzzle_leaderboard_path",
        lambda: puzzle_out,
    )
    cal_results = tmp_path / "elo_calibration" / "results"
    cal_results.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(
        "chess_harness.calibration_view._results_root",
        lambda: cal_results,
    )
    monkeypatch.setattr(
        "chess_harness.snapshot_leaderboard.request_public_snapshots_refresh",
        lambda: None,
    )
    monkeypatch.setattr(
        "chess_harness.snapshot_leaderboard._inject_inline_snapshot",
        lambda _json: None,
    )
