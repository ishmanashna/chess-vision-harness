"""Phase 6 serve hot-path performance tests."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import chess
import pytest
from fastapi.testclient import TestClient

from conftest import FIXTURES, LOW_OPPONENT

from chess_harness.board_controller import BoardController
from chess_harness.board_render_cache import board_png_is_fresh, note_board_rendered
from chess_harness.engine import OpponentEngineManager
from chess_harness.game_manager import GameManager
from chess_harness.game_service import GameService
from chess_harness.opponents import get_catalog
from chess_harness.spectator import _build_games_list, app


@pytest.fixture
def hot_path_client(tmp_path, monkeypatch):
    harness_dir = tmp_path / "harness"
    harness_dir.mkdir()
    shutil_copy = __import__("shutil").copy
    shutil_copy(FIXTURES / "models.json", harness_dir / "models.json")
    monkeypatch.setenv("CHESS_HARNESS_DIR", str(harness_dir))
    monkeypatch.setenv("MODELS_FILE", str(harness_dir / "models.json"))
    monkeypatch.setenv("CHESS_HARNESS_MAX_ENGINE_PROCESSES", "4")

    import chess_harness.api_limits as api_limits
    import chess_harness.spectator as spec

    api_limits.get_limit_enforcer().reset_counters()
    spec._base = str(harness_dir)
    spec.game_manager = GameManager(str(harness_dir))
    spec._controller = None
    spec._game_service = None
    spec._eval_cache.clear()
    spec._finished_eval_cache.clear()

    with TestClient(app) as client:
        yield client, harness_dir


def test_opponent_manager_trim_drops_lru():
    catalog = get_catalog()
    stockfish = catalog.get("stockfish-handicap:noise10")
    inverse = catalog.get("inverse-sf:worst-d10")
    with patch("chess_harness.engine.chess.engine.SimpleEngine.popen_uci") as popen:
        engines = [MagicMock(), MagicMock()]
        popen.side_effect = engines
        mgr = OpponentEngineManager()
        mgr.get_adapter(stockfish)
        mgr.get_adapter(inverse)
        assert mgr.live_adapter_count() == 2
        mgr.get_adapter(stockfish)
        mgr.trim(1)
        assert mgr.live_adapter_count() == 1
        assert engines[0].quit.called or engines[1].quit.called
        mgr.release()


def test_board_png_skips_rerender_when_fresh(tmp_path):
    gm = GameManager(str(tmp_path / "harness"))
    ctrl = BoardController(gm)
    game_id = "fresh-board"
    state = {
        "game_id": game_id,
        "board_fen": chess.STARTING_FEN,
        "moves": [],
        "last_move_uci": None,
        "agent_color": "WHITE",
        "model_name": "composer-2.5",
        "status": "in_progress",
        "pgn_headers": {},
    }
    gm.save_state(game_id, state)
    board_path = gm.get_board_path(game_id)
    board_path.parent.mkdir(parents=True, exist_ok=True)
    board_path.write_bytes(b"png")
    note_board_rendered(game_id, state)
    assert board_png_is_fresh(game_id, state, board_path)

    with patch.object(ctrl.renderer, "render_board") as render:
        assert ctrl.refresh_board_image(game_id) is True
        render.assert_not_called()


def test_games_list_does_not_call_live_eval(hot_path_client, monkeypatch):
    client, harness_dir = hot_path_client
    svc = GameService(GameManager(str(harness_dir)))
    created = svc.new_game(
        "list-no-eval",
        "white",
        opponent_id=LOW_OPPONENT,
        model_name="composer-2.5",
    )
    assert created.get("ok") is True, created

    calls = {"n": 0}
    original = __import__("chess_harness.spectator", fromlist=["_eval_position"])._eval_position

    def counting_eval(fen: str):
        calls["n"] += 1
        return original(fen)

    monkeypatch.setattr("chess_harness.spectator._eval_position", counting_eval)

    listed = client.get("/api/games?status=in_progress")
    assert listed.status_code == 200
    row = next(g for g in listed.json()["games"] if g["game_id"] == "list-no-eval")
    assert row["active_card"] is not None
    assert calls["n"] == 0


def test_build_games_list_finished_elo_without_jsonl_replay(hot_path_client):
    _client, harness_dir = hot_path_client
    gm = GameManager(str(harness_dir))
    game_id = "finished-inline-elo"
    gm.save_state(
        game_id,
        {
            "status": "finished",
            "result": "1-0",
            "agent_color": "WHITE",
            "model_name": "composer-2.5",
            "board_fen": chess.STARTING_FEN,
            "moves": ["e2e4"],
            "elo_before": 1500,
            "elo_after": 1510,
            "elo_delta": 10,
            "end_reason": "resignation",
            "pgn_headers": {},
        },
    )

    with patch.object(
        __import__("chess_harness.elo", fromlist=["ELOLadder"]).ELOLadder,
        "elo_change_for_game",
        side_effect=AssertionError("list must not replay JSONL"),
    ):
        rows, total = _build_games_list("finished", None, 0)

    row = next(r for r in rows if r["game_id"] == game_id)
    assert total >= 1
    assert row["agent_elo"] == 1510
    assert "1510" in (row.get("elo_change") or "")


def test_health_stays_fast_under_list_hammer(hot_path_client):
    client, _ = hot_path_client
    import concurrent.futures

    def hit_list():
        return client.get("/api/games").status_code

    def hit_health():
        return client.get("/health").elapsed.total_seconds()

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        list_futs = [pool.submit(hit_list) for _ in range(12)]
        health_ms = hit_health()
        for fut in list_futs:
            assert fut.result() == 200
    assert health_ms < 2.0
