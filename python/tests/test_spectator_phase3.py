"""Phase 3: mid-game spectator quality + meta-grid wrapping."""

from __future__ import annotations

import time
from unittest.mock import patch

from chess_harness.agent_surface import agent_safe_status, agent_safe_spectator_state
from chess_harness.game_manager import GameManager
from chess_harness.game_quality import GameQuality, SideQuality
from chess_harness.quality_finish import (
    run_provisional_game_quality,
    schedule_provisional_game_quality,
)
from chess_harness.spectator_game_page import render_game_view_page


def _stub_quality(white_acc: float = 88.5, black_acc: float = 91.2) -> GameQuality:
    side = lambda acc: SideQuality(
        accuracy=acc,
        acpl=10.0,
        normalized_acpl=0.1,
        blunder_rate=0.0,
        move_count=6,
    )
    return GameQuality(
        quality_depth=8,
        quality_thin=False,
        white=side(white_acc),
        black=side(black_acc),
    )


def _write_pgn(gm: GameManager, game_id: str) -> None:
    gm.get_game_dir(game_id).mkdir(parents=True, exist_ok=True)
    pgn = (
        '[Event "Test"]\n[White "A"]\n[Black "B"]\n[Result "*"]\n\n'
        "1. e4 e5 2. Nf3 Nc6 3. Bc4 Bc5"
    )
    gm.get_pgn_path(game_id).write_text(pgn, encoding="utf-8")


def test_meta_grid_dd_wraps_words_not_chars():
    from pathlib import Path

    html = render_game_view_page("wrap-test")
    assert "minmax(5.5rem,42%)" in html
    assert "minmax(5rem,1fr)" in html
    assert "overflow-wrap:break-word" in html
    assert "word-break:normal" in html
    assert "min-width:0" in html
    assert "No ELO change recorded yet." not in html
    js = (Path(__file__).resolve().parents[2] / "public-site" / "js" / "spectator-game.js").read_text(
        encoding="utf-8"
    )
    assert "s.elo_change ||" in js


def test_spectator_quality_visible_before_game_over():
    from pathlib import Path

    html = render_game_view_page("mid-quality")
    assert "Performance" in html
    assert "Estimated Elo" not in html
    assert "Est. Elo (play)" not in html
    js = (Path(__file__).resolve().parents[2] / "public-site" / "js" / "spectator-game.js").read_text(
        encoding="utf-8"
    )
    assert "hasQualityMetrics" in js
    assert "isQualityPending" in js
    assert "hasQualityMetrics(s) || pending" in js


@patch("chess_harness.quality_finish.analyse_game")
def test_run_provisional_game_quality_patches_in_progress_state(mock_analyse, tmp_path):
    mock_analyse.return_value = _stub_quality(84.0, 79.0)
    base = tmp_path / "harness"
    gm = GameManager(base_dir=str(base))
    game_id = "live-q1"
    state = {
        "game_id": game_id,
        "status": "in_progress",
        "result": "*",
        "model_name": "agent-a",
        "agent_color": "WHITE",
        "moves": ["e2e4", "e7e5", "g1f3", "b8c6", "f1c4", "f8c5"],
        "pgn_headers": {"Result": "*"},
        "board_fen": "start",
    }
    gm.save_state(game_id, state)
    _write_pgn(gm, game_id)

    assert run_provisional_game_quality(
        game_id, move_count=6, base_dir=str(base)
    ) is True

    saved = gm.load_state(game_id)
    assert saved["quality_provisional"] is True
    assert saved["quality_move_count"] == 6
    assert saved["white_accuracy"] == 84.0
    assert saved["black_accuracy"] == 79.0
    assert saved["quality_at"]
    mock_analyse.assert_called_once()


@patch("chess_harness.quality_finish.analyse_game")
def test_run_provisional_skips_unchanged_move_count(mock_analyse, tmp_path):
    mock_analyse.return_value = _stub_quality()
    base = tmp_path / "harness"
    gm = GameManager(base_dir=str(base))
    game_id = "live-q2"
    state = {
        "game_id": game_id,
        "status": "in_progress",
        "result": "*",
        "model_name": "agent-a",
        "agent_color": "WHITE",
        "moves": ["e2e4", "e7e5"],
        "pgn_headers": {"Result": "*"},
        "board_fen": "start",
        "quality_provisional": True,
        "quality_move_count": 2,
        "quality_at": "2026-01-01T00:00:00+00:00",
        "white_accuracy": 70.0,
    }
    gm.save_state(game_id, state)
    _write_pgn(gm, game_id)

    assert run_provisional_game_quality(
        game_id, move_count=2, base_dir=str(base)
    ) is False
    mock_analyse.assert_not_called()


@patch("chess_harness.quality_finish.analyse_game")
def test_schedule_provisional_runs_in_background(mock_analyse, tmp_path):
    mock_analyse.return_value = _stub_quality()
    base = tmp_path / "harness"
    gm = GameManager(base_dir=str(base))
    game_id = "live-bg"
    state = {
        "game_id": game_id,
        "status": "in_progress",
        "result": "*",
        "model_name": "agent-a",
        "agent_color": "WHITE",
        "moves": ["e2e4", "e7e5"],
        "pgn_headers": {"Result": "*"},
        "board_fen": "start",
    }
    gm.save_state(game_id, state)
    _write_pgn(gm, game_id)

    schedule_provisional_game_quality(
        game_id, move_count=2, base_dir=str(base)
    )

    deadline = time.time() + 5.0
    while time.time() < deadline:
        if gm.load_state(game_id).get("quality_provisional"):
            break
        time.sleep(0.05)

    assert gm.load_state(game_id).get("white_accuracy") == 88.5


def test_agent_api_omits_provisional_quality():
    state = {
        "game_id": "g-prov",
        "status": "in_progress",
        "result": "*",
        "agent_color": "WHITE",
        "moves": ["e2e4"],
        "quality_provisional": True,
        "quality_at": "2026-01-01T00:00:00+00:00",
        "white_accuracy": 88.0,
        "white_play_rating": 1100.0,
    }
    payload = agent_safe_status(
        state,
        "/tmp/board.png",
        {"your_turn": True, "game_over": False},
    )
    assert "white_accuracy" not in payload
    assert "white_play_rating" not in payload


def test_spectator_api_includes_provisional_quality():
    state = {
        "game_id": "g-prov",
        "status": "in_progress",
        "result": "*",
        "quality_provisional": True,
        "quality_at": "2026-01-01T00:00:00+00:00",
        "white_accuracy": 88.0,
        "white_play_rating": 1100.0,
    }
    payload = agent_safe_spectator_state(
        state,
        revision="r1",
        summary="live",
        elo_change="—",
        end_reason_label=None,
        engine_label="Engine",
        agent_outcome=None,
        eval_ui=None,
        agent_elo=1200,
        engine_elo=1500,
        game_over=False,
        board_path="/tmp/board.png",
    )
    assert payload["white_accuracy"] == 88.0
    assert payload["white_play_rating"] == 1100.0
