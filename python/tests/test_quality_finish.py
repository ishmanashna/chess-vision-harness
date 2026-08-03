"""Phase 2 tests: quality finish hooks and results upsert."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from chess_harness.agent_surface import agent_safe_status
from chess_harness.play_rating import map_path, play_rating_for_side
from chess_harness.game_manager import GameManager
from chess_harness.game_quality import GameQuality, SideQuality
from chess_harness.game_types import GAME_TYPE_AGENT_VS_AGENT, GAME_TYPE_HUMAN_VS_AGENT
from chess_harness.quality_finish import run_game_quality, schedule_game_quality
from chess_harness.results import ResultsManager


def _warm_play_rating_map_root(tmp_path):
    """Fixture Q→play-rating map with the documented cold-start threshold."""
    map_root = tmp_path / "cal_results"
    path = map_path(map_root)
    path.parent.mkdir(parents=True)
    payload = {
        "alpha": 8.0,
        "beta": 25.0,
        "min_samples": 30,
        "sample_count": 30,
        "fitted_at": "2026-01-01T00:00:00+00:00",
        "knots": [
            {"q": 0.0, "play_rating": 800.0},
            {"q": 100.0, "play_rating": 1500.0},
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return map_root


def _side(accuracy: float) -> SideQuality:
    return SideQuality(
        accuracy=accuracy,
        acpl=10.0,
        normalized_acpl=0.1,
        blunder_rate=0.0,
        move_count=6,
    )


def _stub_quality(white_acc: float = 88.5, black_acc: float = 91.2) -> GameQuality:
    return GameQuality(
        quality_depth=8,
        quality_thin=False,
        white=_side(white_acc),
        black=_side(black_acc),
    )


def _write_pgn(gm: GameManager, game_id: str, moves: list[str] | None = None) -> None:
    moves = moves or ["e2e4", "e7e5", "g1f3", "b8c6", "f1c4", "f8c5"]
    game_dir = gm.get_game_dir(game_id)
    game_dir.mkdir(parents=True, exist_ok=True)
    pgn = (
        '[Event "Test"]\n[White "A"]\n[Black "B"]\n[Result "1-0"]\n\n'
        + " ".join(f"{i // 2 + 1}. {m}" if i % 2 == 0 else m for i, m in enumerate(moves))
        + " 1-0"
    )
    gm.get_pgn_path(game_id).write_text(pgn, encoding="utf-8")


def test_upsert_quality_fields_patches_matching_row(tmp_path):
    base = tmp_path / "harness"
    base.mkdir()
    rm = ResultsManager(base_dir=str(base))
    rm.append_result({"game_id": "g1", "model_name": "agent-a", "result": "1-0"})
    rm.append_result({"game_id": "g1", "model_name": "agent-b", "result": "1-0"})

    assert rm.upsert_quality_fields(
        "g1",
        "agent-a",
        {"accuracy": 90.0, "play_rating": None, "quality_depth": 8},
    )

    rows = rm.load_results()
    assert rows[0]["accuracy"] == 90.0
    assert rows[0]["quality_depth"] == 8
    assert "accuracy" not in rows[1]


def test_upsert_quality_fields_avaa_dual_rows(tmp_path):
    base = tmp_path / "harness"
    base.mkdir()
    rm = ResultsManager(base_dir=str(base))
    white_id, black_id = "white-bot", "black-bot"
    common = {"game_id": "avaa-1", "game_type": GAME_TYPE_AGENT_VS_AGENT, "result": "1-0"}
    rm.append_result({**common, "model_name": white_id, "agent_color": "WHITE"})
    rm.append_result({**common, "model_name": black_id, "agent_color": "BLACK"})

    fields = {
        "accuracy": 77.7,
        "play_rating": None,
        "quality_depth": 8,
        "quality_thin": True,
        "quality_at": "2026-01-01T00:00:00+00:00",
    }
    assert rm.upsert_quality_fields("avaa-1", white_id, {**fields, "accuracy": 80.0})
    assert rm.upsert_quality_fields("avaa-1", black_id, {**fields, "accuracy": 72.0})

    rows = {r["model_name"]: r for r in rm.load_results()}
    assert rows[white_id]["accuracy"] == 80.0
    assert rows[black_id]["accuracy"] == 72.0
    assert rows[white_id]["quality_thin"] is True
    assert rows[black_id]["quality_at"] == "2026-01-01T00:00:00+00:00"


@patch("chess_harness.quality_finish.analyse_game")
def test_run_game_quality_avaa_state_and_results(mock_analyse, tmp_path):
    mock_analyse.return_value = _stub_quality(85.5, 79.25)
    base = tmp_path / "harness"
    gm = GameManager(base_dir=str(base))
    rm = ResultsManager(base_dir=str(base))
    game_id = "avaa-q1"
    white_id, black_id = "model-w", "model-b"

    state = {
        "game_id": game_id,
        "game_type": GAME_TYPE_AGENT_VS_AGENT,
        "status": "finished",
        "result": "1-0",
        "white_model_id": white_id,
        "black_model_id": black_id,
        "agent_color": "WHITE",
        "moves": ["e2e4", "e7e5"],
        "pgn_headers": {"Result": "1-0"},
        "board_fen": "start",
    }
    gm.save_state(game_id, state)
    _write_pgn(gm, game_id)
    rm.append_result({"game_id": game_id, "model_name": white_id, "result": "1-0"})
    rm.append_result({"game_id": game_id, "model_name": black_id, "result": "1-0"})

    run_game_quality(game_id, base_dir=str(base), map_root=tmp_path / "cold-map")

    saved = gm.load_state(game_id)
    assert saved["quality_depth"] == 8
    assert saved["quality_thin"] is False
    assert saved["quality_at"]
    assert saved["white_accuracy"] == 85.5
    assert saved["black_accuracy"] == 79.25
    assert saved["white_play_rating"] is None
    assert saved["black_play_rating"] is None

    rows = {r["model_name"]: r for r in rm.load_results()}
    assert rows[white_id]["accuracy"] == 85.5
    assert rows[black_id]["accuracy"] == 79.25
    assert rows[white_id]["play_rating"] is None
    mock_analyse.assert_called_once()


@patch("chess_harness.quality_finish.analyse_game")
def test_run_game_quality_agent_vs_human_agent_row(mock_analyse, tmp_path):
    mock_analyse.return_value = _stub_quality(white_acc=93.0, black_acc=50.0)
    base = tmp_path / "harness"
    gm = GameManager(base_dir=str(base))
    rm = ResultsManager(base_dir=str(base))
    game_id = "avh-q1"
    model_id = "test-agent"

    state = {
        "game_id": game_id,
        "game_type": GAME_TYPE_HUMAN_VS_AGENT,
        "status": "finished",
        "result": "1-0",
        "model_name": model_id,
        "agent_color": "WHITE",
        "moves": ["e2e4", "e7e5"],
        "pgn_headers": {"Result": "1-0"},
        "board_fen": "start",
    }
    gm.save_state(game_id, state)
    _write_pgn(gm, game_id)
    rm.append_result({"game_id": game_id, "model_name": model_id, "result": "1-0"})

    run_game_quality(game_id, base_dir=str(base), map_root=tmp_path / "cold-map")

    saved = gm.load_state(game_id)
    assert saved["agent_accuracy"] == 93.0
    assert saved["agent_play_rating"] is None
    assert saved["white_accuracy"] == 93.0
    assert saved["black_accuracy"] == 50.0
    assert saved["white_play_rating"] is None
    assert saved["black_play_rating"] is None
    assert saved["quality_depth"] == 8

    rows = rm.load_results()
    assert len(rows) == 1
    assert rows[0]["accuracy"] == 93.0


def test_run_game_quality_skips_no_result(tmp_path, monkeypatch):
    base = tmp_path / "harness"
    gm = GameManager(base_dir=str(base))
    game_id = "idle-1"
    state = {
        "game_id": game_id,
        "status": "finished",
        "result": "*",
        "model_name": "agent",
        "moves": [],
        "pgn_headers": {"Result": "*"},
        "board_fen": "start",
    }
    gm.save_state(game_id, state)
    _write_pgn(gm, game_id, moves=[])

    called = {"n": 0}

    def _boom(_pgn):
        called["n"] += 1
        raise AssertionError("should not analyse")

    monkeypatch.setattr("chess_harness.quality_finish.analyse_game", _boom)
    run_game_quality(game_id, base_dir=str(base))
    assert called["n"] == 0
    assert gm.load_state(game_id).get("quality_at") is None


@patch("chess_harness.quality_finish.analyse_game")
def test_schedule_game_quality_runs_in_background(mock_analyse, tmp_path):
    mock_analyse.return_value = _stub_quality()
    base = tmp_path / "harness"
    gm = GameManager(base_dir=str(base))
    rm = ResultsManager(base_dir=str(base))
    game_id = "bg-1"
    model_id = "solo-agent"
    state = {
        "game_id": game_id,
        "status": "finished",
        "result": "1-0",
        "model_name": model_id,
        "agent_color": "BLACK",
        "moves": ["e2e4"],
        "pgn_headers": {"Result": "1-0"},
        "board_fen": "start",
    }
    gm.save_state(game_id, state)
    _write_pgn(gm, game_id)
    rm.append_result({"game_id": game_id, "model_name": model_id, "result": "1-0"})

    schedule_game_quality(game_id, base_dir=str(base))

    import time

    deadline = time.time() + 5.0
    while time.time() < deadline:
        if gm.load_state(game_id).get("quality_at"):
            break
        time.sleep(0.05)

    assert gm.load_state(game_id).get("agent_accuracy") == 91.2


@patch("chess_harness.quality_finish.analyse_game")
def test_run_game_quality_writes_play_rating_with_warm_map(mock_analyse, tmp_path):
    """Phase 4: harness finish applies Q→play-rating map when warm."""
    quality = _stub_quality(85.5, 79.25)
    mock_analyse.return_value = quality
    map_root = _warm_play_rating_map_root(tmp_path)
    expected_white = play_rating_for_side(quality.white, root=map_root)
    expected_black = play_rating_for_side(quality.black, root=map_root)
    assert expected_white is not None
    assert expected_black is not None

    base = tmp_path / "harness"
    gm = GameManager(base_dir=str(base))
    rm = ResultsManager(base_dir=str(base))
    game_id = "avaa-pr1"
    white_id, black_id = "model-w", "model-b"

    state = {
        "game_id": game_id,
        "game_type": GAME_TYPE_AGENT_VS_AGENT,
        "status": "finished",
        "result": "1-0",
        "white_model_id": white_id,
        "black_model_id": black_id,
        "agent_color": "WHITE",
        "moves": ["e2e4", "e7e5"],
        "pgn_headers": {"Result": "1-0"},
        "board_fen": "start",
    }
    gm.save_state(game_id, state)
    _write_pgn(gm, game_id)
    rm.append_result({"game_id": game_id, "model_name": white_id, "result": "1-0"})
    rm.append_result({"game_id": game_id, "model_name": black_id, "result": "1-0"})

    run_game_quality(game_id, base_dir=str(base), map_root=map_root)

    saved = gm.load_state(game_id)
    assert saved["white_play_rating"] == expected_white
    assert saved["black_play_rating"] == expected_black
    assert "agent_play_rating" not in saved

    rows = {r["model_name"]: r for r in rm.load_results()}
    assert rows[white_id]["play_rating"] == expected_white
    assert rows[black_id]["play_rating"] == expected_black


@patch("chess_harness.quality_finish.analyse_game")
def test_run_game_quality_avh_both_sides_play_rating(mock_analyse, tmp_path):
    """Phase 4: AvH state gets white/black + agent Play rating (play)."""
    quality = _stub_quality(white_acc=93.0, black_acc=50.0)
    mock_analyse.return_value = quality
    map_root = _warm_play_rating_map_root(tmp_path)
    expected_agent = play_rating_for_side(quality.white, root=map_root)
    expected_human = play_rating_for_side(quality.black, root=map_root)
    assert expected_agent is not None
    assert expected_human is not None

    base = tmp_path / "harness"
    gm = GameManager(base_dir=str(base))
    rm = ResultsManager(base_dir=str(base))
    game_id = "avh-pr1"
    model_id = "test-agent"

    state = {
        "game_id": game_id,
        "game_type": GAME_TYPE_HUMAN_VS_AGENT,
        "status": "finished",
        "result": "1-0",
        "model_name": model_id,
        "agent_color": "WHITE",
        "moves": ["e2e4", "e7e5"],
        "pgn_headers": {"Result": "1-0"},
        "board_fen": "start",
    }
    gm.save_state(game_id, state)
    _write_pgn(gm, game_id)
    rm.append_result({"game_id": game_id, "model_name": model_id, "result": "1-0"})

    run_game_quality(game_id, base_dir=str(base), map_root=map_root)

    saved = gm.load_state(game_id)
    assert saved["white_play_rating"] == expected_agent
    assert saved["black_play_rating"] == expected_human
    assert saved["agent_play_rating"] == expected_agent

    rows = rm.load_results()
    assert len(rows) == 1
    assert rows[0]["play_rating"] == expected_agent


@patch("chess_harness.quality_finish.analyse_game")
def test_run_game_quality_ave_agent_play_rating(mock_analyse, tmp_path):
    """Phase 4: AvE agent row gets Play rating (play) from the Q map."""
    quality = _stub_quality(white_acc=70.0, black_acc=82.0)
    mock_analyse.return_value = quality
    map_root = _warm_play_rating_map_root(tmp_path)
    expected_agent = play_rating_for_side(quality.black, root=map_root)
    assert expected_agent is not None

    base = tmp_path / "harness"
    gm = GameManager(base_dir=str(base))
    rm = ResultsManager(base_dir=str(base))
    game_id = "ave-pr1"
    model_id = "test-agent"

    state = {
        "game_id": game_id,
        "status": "finished",
        "result": "0-1",
        "model_name": model_id,
        "agent_color": "BLACK",
        "moves": ["e2e4", "e7e5"],
        "pgn_headers": {"Result": "0-1"},
        "board_fen": "start",
    }
    gm.save_state(game_id, state)
    _write_pgn(gm, game_id)
    rm.append_result({"game_id": game_id, "model_name": model_id, "result": "0-1"})

    run_game_quality(game_id, base_dir=str(base), map_root=map_root)

    saved = gm.load_state(game_id)
    assert saved["agent_play_rating"] == expected_agent
    assert saved["black_play_rating"] == expected_agent
    assert saved["white_play_rating"] == play_rating_for_side(quality.white, root=map_root)

    rows = rm.load_results()
    assert rows[0]["play_rating"] == expected_agent


def test_agent_safe_status_includes_play_rating_fields():
    state = {
        "game_id": "g-est",
        "status": "finished",
        "result": "1-0",
        "agent_color": "WHITE",
        "moves": ["e2e4", "e7e5"],
        "quality_at": "2026-01-01T00:00:00+00:00",
        "white_accuracy": 88.0,
        "black_accuracy": 72.0,
        "white_play_rating": 1100.5,
        "black_play_rating": 950.2,
        "agent_play_rating": 1100.5,
    }
    payload = agent_safe_status(
        state,
        "/tmp/board.png",
        {"your_turn": False, "game_over": True},
    )
    assert payload["white_play_rating"] == 1100.5
    assert payload["black_play_rating"] == 950.2
    assert payload["agent_play_rating"] == 1100.5
    assert payload["white_accuracy"] == 88.0
    assert "fen" not in payload
    assert "moves" not in payload
