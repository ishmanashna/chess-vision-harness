"""Phase 1: finished-games SQLite dual-write + survive live delete."""

from __future__ import annotations

import json
import subprocess

import pytest

from chess_harness.board_controller import BoardController
from chess_harness.finished_games_db import (
    get_finished_game,
    record_scored_finish,
    upsert_finished_game,
)
from chess_harness.game_manager import GameManager
from chess_harness.game_types import DEFAULT_GAME_TYPE, GAME_TYPE_HUMAN_VS_AGENT
from chess_harness.paths import project_root, resolve_finished_games_db
from chess_harness.results import ResultsManager


@pytest.fixture
def finished_db(tmp_path, monkeypatch):
    db_path = tmp_path / "finished_games.sqlite"
    monkeypatch.setenv("CHESS_HARNESS_FINISHED_DB", str(db_path))
    harness = tmp_path / "harness"
    harness.mkdir()
    monkeypatch.setenv("CHESS_HARNESS_DIR", str(harness))
    return db_path, harness


def _ave_state(game_id: str = "ave-1", result: str = "1-0") -> dict:
    return {
        "game_id": game_id,
        "game_type": DEFAULT_GAME_TYPE,
        "status": "finished",
        "result": result,
        "end_reason": "checkmate (White wins)",
        "agent_color": "WHITE",
        "model_name": "agent-a",
        "model_display_name": "Agent A",
        "opponent_id": "stockfish_skill_5",
        "opponent_elo": 1200,
        "moves": ["e2e4", "e7e5", "d1h5", "b8c6", "h5f7"],
        "board_fen": "r1bqkb1r/pppp1Qpp/2n2n2/4p3/2B1P3/8/PPPP1PPP/RNB1K1NR b KQkq - 0 4",
        "pgn_headers": {"Result": result, "Event": "Chess Vision Harness Game"},
        "elo_before": 1500,
        "elo_after": 1516,
        "elo_delta": 16,
    }


def test_upsert_scored_game_and_survive_delete(finished_db):
    db_path, harness = finished_db
    gm = GameManager(str(harness))
    rm = ResultsManager(base_dir=str(harness))
    game_id = "ave-durability"
    state = _ave_state(game_id)
    gm.get_game_dir(game_id).mkdir(parents=True, exist_ok=True)
    gm.save_state(game_id, state)
    pgn = '[Result "1-0"]\n\n1. e4 e5 2. Qh5 Nc6 3. Bc4 Nf6 4. Qxf7# 1-0\n'
    gm.get_pgn_path(game_id).write_text(pgn, encoding="utf-8")
    rm.append_result(
        {
            "ts": "2026-07-31T12:00:00",
            "game_id": game_id,
            "model_name": "agent-a",
            "result": "1-0",
            "agent_color": "WHITE",
        }
    )

    assert record_scored_finish(
        game_id, state, db_path=db_path, game_manager=gm, results_manager=rm
    )
    row = get_finished_game(game_id, db_path=db_path)
    assert row is not None
    assert row["result"] == "1-0"
    assert row["model_id"] == "agent-a"
    assert row["opponent_id"] == "stockfish_skill_5"
    assert row["elo_delta"] == 16
    assert json.loads(row["moves_uci_json"])[0] == "e2e4"
    assert "1-0" in (row["pgn_text"] or "")
    assert json.loads(row["state_json"])["game_id"] == game_id
    results = json.loads(row["results_json"])
    assert len(results) == 1

    assert gm.delete_game(game_id)
    assert not gm.game_exists(game_id)
    still = get_finished_game(game_id, db_path=db_path)
    assert still is not None
    assert still["result"] == "1-0"


def test_skip_no_result_star(finished_db):
    db_path, _ = finished_db
    state = _ave_state("star-1", result="*")
    state["end_reason"] = "inactivity"
    assert record_scored_finish(state["game_id"], state, db_path=db_path) is False
    assert get_finished_game("star-1", db_path=db_path) is None


def test_upsert_idempotent(finished_db):
    db_path, _ = finished_db
    state = _ave_state("idem-1")
    upsert_finished_game("idem-1", state, db_path=db_path, pgn_text="first")
    state["elo_after"] = 1520
    state["elo_delta"] = 20
    upsert_finished_game("idem-1", state, db_path=db_path, pgn_text="second")
    row = get_finished_game("idem-1", db_path=db_path)
    assert row["elo_delta"] == 20
    assert row["pgn_text"] == "second"


def test_schedule_quality_dual_writes(finished_db, monkeypatch):
    db_path, harness = finished_db
    monkeypatch.setattr(
        "chess_harness.board_controller.schedule_game_quality", lambda *a, **k: None
    )
    gm = GameManager(str(harness))
    ctrl = BoardController(gm)
    game_id = "via-schedule"
    state = _ave_state(game_id)
    gm.save_state(game_id, state)
    gm.get_pgn_path(game_id).write_text('[Result "1-0"]\n', encoding="utf-8")
    ctrl.results.append_result(
        {"game_id": game_id, "model_name": "agent-a", "result": "1-0"}
    )

    ctrl._schedule_quality_if_scored(game_id, state)
    row = get_finished_game(game_id, db_path=db_path)
    assert row is not None
    assert row["game_type"] == DEFAULT_GAME_TYPE


def test_avh_resign_dual_writes(finished_db, monkeypatch):
    db_path, harness = finished_db
    monkeypatch.setattr(
        "chess_harness.board_controller.schedule_game_quality", lambda *a, **k: None
    )
    gm = GameManager(str(harness))
    ctrl = BoardController(gm)
    game_id = "avh-resign-db"
    state = {
        "game_id": game_id,
        "game_type": GAME_TYPE_HUMAN_VS_AGENT,
        "status": "in_progress",
        "result": "*",
        "model_name": "agent-a",
        "model_display_name": "Agent A",
        "agent_color": "WHITE",
        "human_color": "BLACK",
        "human_nickname": "Bob",
        "agent_joined": True,
        "moves": ["e2e4", "e7e5"],
        "pgn_headers": {"Result": "*"},
        "board_fen": "rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2",
        "last_activity": "2026-07-30T00:00:00+00:00",
    }
    gm.save_state(game_id, state)
    out = ctrl.human_play.resign(game_id)
    assert out["ok"] is True
    row = get_finished_game(game_id, db_path=db_path)
    assert row is not None
    assert row["result"] == "0-1"
    assert row["human_nickname"] == "Bob"
    assert gm.delete_game(game_id)
    assert get_finished_game(game_id, db_path=db_path) is not None


def test_default_db_path_not_gitignored():
    rel = "data/finished_games.sqlite"
    root = project_root()
    assert resolve_finished_games_db() == (root / rel).resolve()
    proc = subprocess.run(
        ["git", "check-ignore", "-v", rel],
        cwd=str(root),
        capture_output=True,
        text=True,
        check=False,
    )
    # Exit 1 = not ignored; exit 0 would print a matching rule.
    assert proc.returncode == 1, proc.stdout + proc.stderr
    for gi in root.rglob(".gitignore"):
        text = gi.read_text(encoding="utf-8")
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or stripped.startswith("!"):
                continue
            assert "finished_games.sqlite" not in stripped
            if gi.parent == root / "data":
                assert stripped not in ("*.sqlite", "data/", "*")
