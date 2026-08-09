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
from chess_harness.game_quality import (
    COMPOSITE_Q_ALPHA,
    COMPOSITE_Q_BETA,
    SideQuality,
    analyse_game,
)  # noqa: E402
from chess_harness.play_rating import (  # noqa: E402
    MIN_GAMES_FOR_SAMPLE,
    MIN_MAP_SAMPLES,
    append_play_rating_sample,
    build_samples_for_calibration_game,
    composite_q,
    fit_map_knots,
    interpolate_map,
    is_sample_eligible,
    play_rating_for_side,
    play_rating_status_summary,
    process_calibration_game_quality,
    rebuild_estimation_samples,
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


def _write_warm_accuracy_map(root: Path) -> Path:
    """Fixture accuracy→Elo map with the documented warm criteria (≥2 engines)."""
    path = root / "accuracy_elo_map.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "engine_count": 2,
                "min_engines": 2,
                "fitted_at": "2026-01-01T00:00:00+00:00",
                "knots": [
                    {"accuracy": 0.0, "elo": 500.0},
                    {"accuracy": 100.0, "elo": 1500.0},
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def test_composite_q_formula():
    side = _side(accuracy=80.0, acpl=50.0, blunder_rate=0.1)
    expected = 80.0 - COMPOSITE_Q_ALPHA * 0.5 - COMPOSITE_Q_BETA * 0.1
    assert composite_q(side) == pytest.approx(expected)


def test_composite_q_missing_metrics():
    assert composite_q(SideQuality(None, None, None, None, 0)) is None


def test_is_sample_eligibility():
    assert not is_sample_eligible(games_played=100, anchor=False)
    assert is_sample_eligible(games_played=101, anchor=False)
    assert not is_sample_eligible(games_played=0, anchor=True)
    assert is_sample_eligible(games_played=1, anchor=True)
    assert is_sample_eligible(games_played=500, anchor=True)


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
            {"engine_id": "engine-a", "q": 50.0 + i, "accuracy": 80.0, "calibration_elo_before": 800.0 + i},
            root=root,
        )
    assert play_rating_for_side(side, root=root) is None


def test_play_rating_warm_map(tmp_path: Path):
    root = tmp_path / "results"
    _write_warm_accuracy_map(root)
    rating = play_rating_for_side(_side(accuracy=90.0), root=root)
    assert rating is not None
    assert 1300.0 <= rating <= 1500.0  # 500 + 0.9 * 1000 = 1400


def test_play_rating_status_summary_aggregates(tmp_path: Path):
    root = tmp_path
    for i in range(MIN_MAP_SAMPLES):
        append_play_rating_sample(
            {
                "engine_id": "stockfish-handicap:noise22",
                "q": 50.0 + i,
                "q_midgame": 48.0 + i,
                "q_trimmed": 51.0 + i,
                "accuracy": 80.0 + (i % 5),
                "acpl": 30.0 + (i % 3),
                "calibration_elo_before": 700.0 + i,
            },
            root=root,
        )
    summary = play_rating_status_summary(
        root=root,
        engine_elos={"stockfish-handicap:noise22": 750},
    )
    assert summary["sample_count"] == MIN_MAP_SAMPLES
    eng = summary["engines"][0]
    assert eng["engine_id"] == "stockfish-handicap:noise22"
    assert eng["sample_count"] == MIN_MAP_SAMPLES
    assert eng["mean_accuracy"] is not None
    assert eng["accuracy_std"] is not None
    assert "elo_estimations" not in eng
    assert "champion" not in summary
    assert "estimators" not in summary
    assert "warm" not in summary


def test_play_rating_status_summary_stddev_and_reliability(tmp_path: Path):
    root = tmp_path
    samples = [
        {
            "engine_id": "engine-a",
            "q": 10.0,
            "accuracy": 80.0,
            "calibration_elo_before": 600.0,
        },
        {
            "engine_id": "engine-a",
            "q": 20.0,
            "accuracy": 90.0,
            "calibration_elo_before": 700.0,
        },
        {
            "engine_id": "engine-b",
            "q": 15.0,
            "accuracy": 85.0,
            "calibration_elo_before": 650.0,
        },
    ]
    for row in samples:
        append_play_rating_sample(row, root=root)
    summary = play_rating_status_summary(root=root)
    eng_a = next(e for e in summary["engines"] if e["engine_id"] == "engine-a")
    assert eng_a["mean_accuracy"] == 85.0
    assert eng_a["accuracy_std"] == 5.0
    eng_b = next(e for e in summary["engines"] if e["engine_id"] == "engine-b")
    assert eng_b["accuracy_std"] is None  # n < 2
    assert "reliability" not in summary

    for i in range(MIN_MAP_SAMPLES - len(samples)):
        append_play_rating_sample(
            {
                "engine_id": "engine-a",
                "q": float(i),
                "accuracy": 75.0 + (i % 3),
                "calibration_elo_before": 500.0 + i * 10.0,
            },
            root=root,
        )
    warm = play_rating_status_summary(root=root)
    warm_a = next(e for e in warm["engines"] if e["engine_id"] == "engine-a")
    assert warm_a["mean_accuracy"] is not None
    assert "reliability" not in warm


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


def test_process_calibration_includes_anchors(tmp_path: Path):
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
    assert n == 2
    rows = [
        json.loads(line)
        for line in (root / "continuous" / "play_rating_samples.jsonl")
        .read_text()
        .strip()
        .splitlines()
    ]
    ids = {row["engine_id"] for row in rows}
    assert ids == {MID_OPPONENT, "stockfish:0"}
    anchor_row = next(r for r in rows if r["engine_id"] == "stockfish:0")
    assert anchor_row["calibration_elo_before"] == 1320.0


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


def test_parallel_sample_append_no_corruption(tmp_path: Path):
    root = tmp_path / "results"
    errors: list[Exception] = []

    def worker() -> None:
        try:
            for _ in range(20):
                append_play_rating_sample(
                    {"engine_id": "engine-a", "q": 1.0, "accuracy": 70.0, "calibration_elo_before": 900.0},
                    root=root,
                )
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    lines = (
        (root / "continuous" / "play_rating_samples.jsonl")
        .read_text()
        .strip()
        .splitlines()
    )
    assert len(lines) == 160
    for line in lines:
        assert json.loads(line)["engine_id"] == "engine-a"
    assert not (root / "accuracy_elo_map.json").exists()


def test_append_game_log_persists_uci_moves(tmp_path: Path):
    ladder = CalibrationLadder()
    record = ladder.record_game(LOW_OPPONENT, MID_OPPONENT, "1-0")
    log_path = tmp_path / "games.jsonl"
    moves = ["e2e4", "e7e5", "g1f3", "b8c6"]
    ladder.append_game_log(log_path, record, uci_moves=moves)
    row = json.loads(log_path.read_text().strip())
    assert row["uci_moves"] == moves
    assert row["game_index"] == record.game_index
    assert row["white"] == LOW_OPPONENT


def test_append_game_log_omits_empty_uci_moves(tmp_path: Path):
    ladder = CalibrationLadder()
    record = ladder.record_game(LOW_OPPONENT, MID_OPPONENT, "1/2-1/2")
    log_path = tmp_path / "games.jsonl"
    ladder.append_game_log(log_path, record)
    row = json.loads(log_path.read_text().strip())
    assert "uci_moves" not in row


def _write_game_log_row(
    path: Path,
    *,
    game_index: int,
    white: str,
    black: str,
    uci_moves: list[str] | None,
    white_games: int,
    black_games: int,
) -> None:
    row = {
        "game_index": game_index,
        "ts": "2026-01-01T00:00:00+00:00",
        "white": white,
        "black": black,
        "result": "1/2-1/2",
        "white_elo_before": 600.0,
        "black_elo_before": 620.0,
        "updates": [
            {
                "opponent_id": white,
                "elo_before": 600.0,
                "elo_after": 601.0,
                "elo_delta": 1.0,
                "games_played": white_games,
            },
            {
                "opponent_id": black,
                "elo_before": 620.0,
                "elo_after": 619.0,
                "elo_delta": -1.0,
                "games_played": black_games,
            },
        ],
    }
    if uci_moves is not None:
        row["uci_moves"] = uci_moves
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


def test_rebuild_estimation_samples_from_games_log(tmp_path: Path):
    root = tmp_path / "results"
    cont = root / "continuous"
    cont.mkdir(parents=True)
    moves = ["e2e4", "e7e5", "g1f3", "b8c6", "f1c4", "g8f6"]
    log_path = cont / "games.jsonl"
    _write_game_log_row(
        log_path,
        game_index=1,
        white=LOW_OPPONENT,
        black=MID_OPPONENT,
        uci_moves=moves,
        white_games=50,
        black_games=101,
    )
    _write_game_log_row(
        log_path,
        game_index=2,
        white=LOW_OPPONENT,
        black=MID_OPPONENT,
        uci_moves=None,
        white_games=51,
        black_games=102,
    )

    result = rebuild_estimation_samples(root=root, eval_fn=ScriptedEval({}))
    assert result == {"games_total": 2, "games_with_moves": 1, "samples": 1}

    samples_path = cont / "play_rating_samples.jsonl"
    rows = [json.loads(line) for line in samples_path.read_text().strip().splitlines()]
    assert len(rows) == 1
    assert rows[0]["engine_id"] == MID_OPPONENT
    assert rows[0]["game_index"] == 1
    assert not (cont / "play_rating_map.json").exists()


def test_rebuild_estimation_samples_idempotent(tmp_path: Path):
    root = tmp_path / "results"
    cont = root / "continuous"
    cont.mkdir(parents=True)
    moves = ["e2e4", "e7e5", "g1f3", "b8c6"]
    log_path = cont / "games.jsonl"
    _write_game_log_row(
        log_path,
        game_index=1,
        white=LOW_OPPONENT,
        black=MID_OPPONENT,
        uci_moves=moves,
        white_games=120,
        black_games=120,
    )

    rebuild_estimation_samples(root=root, eval_fn=ScriptedEval({}))
    first = (cont / "play_rating_samples.jsonl").read_text()
    rebuild_estimation_samples(root=root, eval_fn=ScriptedEval({}))
    second = (cont / "play_rating_samples.jsonl").read_text()
    assert first == second
    assert len(first.strip().splitlines()) == 2


def test_rebuild_does_not_mutate_ratings_json(tmp_path: Path):
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

    moves = ["e2e4", "e7e5", "g1f3", "b8c6"]
    _write_game_log_row(
        cont / "games.jsonl",
        game_index=1,
        white=LOW_OPPONENT,
        black=MID_OPPONENT,
        uci_moves=moves,
        white_games=121,
        black_games=121,
    )
    rebuild_estimation_samples(root=root, eval_fn=ScriptedEval({}))

    assert ratings_path.read_bytes() == before
