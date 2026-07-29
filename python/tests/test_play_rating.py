"""Tests for play-rating map (Phase 4)."""

from __future__ import annotations

import json
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import MagicMock, patch

import chess
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "elo_calibration"))

from conftest import LOW_OPPONENT, MID_OPPONENT  # noqa: E402
from calibration.ratings import CalibrationLadder, GameRecord, RatingUpdate  # noqa: E402
from chess_harness.game_quality import SideQuality, analyse_game  # noqa: E402
from chess_harness.play_rating import (  # noqa: E402
    MIN_GAMES_FOR_SAMPLE,
    MIN_MAP_SAMPLES,
    Q_ALPHA,
    Q_BETA,
    append_play_rating_sample,
    composite_q,
    fit_map_knots,
    fit_play_rating_map,
    interpolate_map,
    is_sample_eligible,
    play_rating_for_side,
    play_rating_from_q,
    process_calibration_game_quality,
    schedule_map_refit,
)


class ScriptedEval:
    def __init__(self, cp_by_index: dict[int, int]):
        self.cp_by_index = cp_by_index

    def __call__(self, board: chess.Board) -> int:
        return self.cp_by_index.get(len(board.move_stack), 0)


def _side(accuracy=90.0, acpl=20.0, blunder_rate=0.05) -> SideQuality:
    return SideQuality(
        accuracy=accuracy,
        acpl=acpl,
        normalized_acpl=acpl / 100.0,
        blunder_rate=blunder_rate,
        move_count=20,
    )


def test_composite_q_formula():
    side = _side(accuracy=80.0, acpl=50.0, blunder_rate=0.1)
    expected = 80.0 - Q_ALPHA * 0.5 - Q_BETA * 0.1
    assert composite_q(side) == pytest.approx(expected)


def test_composite_q_missing_metrics():
    assert composite_q(SideQuality(None, None, None, None, 0)) is None


def test_is_sample_eligibility():
    assert not is_sample_eligible(games_played=100, anchor=False)
    assert is_sample_eligible(games_played=101, anchor=False)
    assert not is_sample_eligible(games_played=500, anchor=True)


def test_fit_map_knots_monotone():
    samples = [
        {"q": 10.0, "calibration_elo_before": 900.0},
        {"q": 20.0, "calibration_elo_before": 850.0},
        {"q": 30.0, "calibration_elo_before": 1100.0},
        {"q": 40.0, "calibration_elo_before": 1050.0},
    ]
    knots = fit_map_knots(samples)
    ratings = [k["play_rating"] for k in knots]
    assert ratings == sorted(ratings)
    assert len(knots) >= 2


def test_interpolate_map_linear():
    knots = [
        {"q": 0.0, "play_rating": 500.0},
        {"q": 100.0, "play_rating": 1500.0},
    ]
    assert interpolate_map(knots, 50.0) == pytest.approx(1000.0)
    assert interpolate_map(knots, -10.0) == pytest.approx(500.0)
    assert interpolate_map(knots, 200.0) == pytest.approx(1500.0)


def test_play_rating_cold_start(tmp_path: Path):
    root = tmp_path / "results"
    side = _side()
    assert play_rating_for_side(side, root=root) is None

    for i in range(MIN_MAP_SAMPLES - 1):
        append_play_rating_sample(
            {"q": 50.0 + i, "calibration_elo_before": 800.0 + i},
            root=root,
        )
    fit_play_rating_map(root=root)
    assert play_rating_for_side(side, root=root) is None


def test_play_rating_warm_map(tmp_path: Path):
    root = tmp_path / "results"
    for i in range(MIN_MAP_SAMPLES):
        append_play_rating_sample(
            {"q": float(i), "calibration_elo_before": 500.0 + i * 10.0},
            root=root,
        )
    fit_play_rating_map(root=root)
    rating = play_rating_from_q(15.0, root=root)
    assert rating is not None
    assert 600.0 <= rating <= 700.0


def test_process_calibration_skips_ineligible(tmp_path: Path, monkeypatch):
    root = tmp_path / "results"
    moves = ["e2e4", "e7e5", "g1f3", "b8c6", "f1c4", "g8f6"]
    record = GameRecord(
        game_index=1,
        white_id=LOW_OPPONENT,
        black_id=MID_OPPONENT,
        result="1/2-1/2",
        white_elo_before=600.0,
        black_elo_before=620.0,
        updates=[
            RatingUpdate(LOW_OPPONENT, 600.0, 601.0, 1.0, games_played=50),
            RatingUpdate(MID_OPPONENT, 620.0, 619.0, -1.0, games_played=101),
        ],
    )
    n = process_calibration_game_quality(
        record,
        LOW_OPPONENT,
        MID_OPPONENT,
        moves,
        eval_fn=ScriptedEval({}),
        root=root,
    )
    assert n == 1
    rows = (root / "continuous" / "play_rating_samples.jsonl").read_text().strip().splitlines()
    assert len(rows) == 1
    row = json.loads(rows[0])
    assert row["engine_id"] == MID_OPPONENT
    assert row["calibration_elo_before"] == 620.0
    assert "q" in row


def test_process_calibration_skips_anchors(tmp_path: Path):
    root = tmp_path / "results"
    moves = ["e2e4", "e7e5"]
    record = GameRecord(
        game_index=2,
        white_id="stockfish:0",
        black_id=MID_OPPONENT,
        result="0-1",
        white_elo_before=1320.0,
        black_elo_before=700.0,
        updates=[
            RatingUpdate(MID_OPPONENT, 700.0, 720.0, 20.0, games_played=150),
        ],
    )
    n = process_calibration_game_quality(
        record,
        "stockfish:0",
        MID_OPPONENT,
        moves,
        eval_fn=ScriptedEval({}),
        root=root,
    )
    assert n == 1
    row = json.loads(
        (root / "continuous" / "play_rating_samples.jsonl").read_text().strip()
    )
    assert row["engine_id"] == MID_OPPONENT


def test_quality_path_does_not_mutate_ratings_json(tmp_path: Path):
    root = tmp_path / "results"
    cont = root / "continuous"
    cont.mkdir(parents=True)
    ratings_path = cont / "ratings.json"
    ladder = CalibrationLadder()
    ladder.ratings[LOW_OPPONENT] = 610.0
    ladder.ratings[MID_OPPONENT] = 630.0
    ladder.games_played[LOW_OPPONENT] = 120
    ladder.games_played[MID_OPPONENT] = 120
    ladder.save(ratings_path)
    before = ratings_path.read_bytes()

    record = GameRecord(
        game_index=3,
        white_id=LOW_OPPONENT,
        black_id=MID_OPPONENT,
        result="1-0",
        white_elo_before=610.0,
        black_elo_before=630.0,
        updates=[
            RatingUpdate(LOW_OPPONENT, 610.0, 615.0, 5.0, games_played=121),
            RatingUpdate(MID_OPPONENT, 630.0, 625.0, -5.0, games_played=121),
        ],
    )
    moves = ["e2e4", "e7e5", "g1f3", "b8c6"]
    process_calibration_game_quality(
        record,
        LOW_OPPONENT,
        MID_OPPONENT,
        moves,
        eval_fn=ScriptedEval({}),
        root=root,
    )

    assert ratings_path.read_bytes() == before


def test_parallel_map_refit_no_corruption(tmp_path: Path):
    root = tmp_path / "results"
    for i in range(MIN_MAP_SAMPLES):
        append_play_rating_sample(
            {"q": float(i % 20), "calibration_elo_before": 700.0 + (i % 20) * 5.0},
            root=root,
        )

    errors: list[Exception] = []

    def worker() -> None:
        try:
            fit_play_rating_map(root=root)
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    data = json.loads((root / "continuous" / "play_rating_map.json").read_text())
    assert data["sample_count"] == MIN_MAP_SAMPLES
    assert data.get("fitted_at")
    assert isinstance(data.get("knots"), list)


def test_debounced_refit_writes_map(tmp_path: Path):
    root = tmp_path / "results"
    for i in range(MIN_MAP_SAMPLES):
        append_play_rating_sample(
            {"q": float(i), "calibration_elo_before": 600.0 + i},
            root=root,
        )

    def immediate(_delay: float, fn):
        fn()
        return MagicMock()

    with patch("chess_harness.play_rating.threading.Timer", side_effect=immediate):
        schedule_map_refit(root=root)
    assert (root / "continuous" / "play_rating_map.json").exists()
