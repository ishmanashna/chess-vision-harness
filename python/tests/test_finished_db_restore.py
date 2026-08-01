"""Phase 3: finished-db list + restore after live delete."""

from __future__ import annotations

from chess_harness.commands import cmd_finished_db_list, cmd_finished_db_restore
from chess_harness.finished_games_db import (
    list_finished_games,
    record_scored_finish,
    restore_finished_game,
)
from chess_harness.game_manager import GameManager
from chess_harness.game_types import DEFAULT_GAME_TYPE
from chess_harness.results import ResultsManager


def _scored_state(game_id: str, result: str = "1-0") -> dict:
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
        "moves": ["e2e4", "e7e5"],
        "board_fen": "rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2",
        "pgn_headers": {"Result": result},
        "elo_before": 1500,
        "elo_after": 1516,
        "elo_delta": 16,
    }


def test_list_and_restore_after_live_delete(tmp_path, monkeypatch):
    db_path = tmp_path / "finished_games.sqlite"
    monkeypatch.setenv("CHESS_HARNESS_FINISHED_DB", str(db_path))
    harness = tmp_path / "harness"
    harness.mkdir()
    monkeypatch.setenv("CHESS_HARNESS_DIR", str(harness))

    gm = GameManager(str(harness))
    rm = ResultsManager(base_dir=str(harness))
    game_id = "restore-me"
    state = _scored_state(game_id)
    gm.get_game_dir(game_id).mkdir(parents=True, exist_ok=True)
    gm.save_state(game_id, state)
    pgn = f'[Result "1-0"]\n\n1. e4 e5 1-0\n'
    gm.get_pgn_path(game_id).write_text(pgn, encoding="utf-8")
    result_row = {
        "ts": "2026-07-31T12:00:00",
        "game_id": game_id,
        "model_name": "agent-a",
        "result": "1-0",
        "agent_color": "WHITE",
    }
    rm.append_result(result_row)

    assert record_scored_finish(
        game_id, state, db_path=db_path, game_manager=gm, results_manager=rm
    )
    assert {r["game_id"] for r in list_finished_games(db_path=db_path)} == {game_id}

    # Accidental live wipe: dir + results row gone; DB keeps the row.
    assert gm.delete_game(game_id)
    rm.remove_game_results(game_id)
    assert not gm.game_exists(game_id)
    assert not any(r.get("game_id") == game_id for r in rm.load_results())

    rebuild_calls: list[bool] = []
    snapshot_calls: list[bool] = []

    def fake_rebuild():
        rebuild_calls.append(True)

    def fake_export():
        snapshot_calls.append(True)
        return harness / "leaderboard.json"

    monkeypatch.setattr("chess_harness.commands.cmd_rebuild_elo", fake_rebuild)
    monkeypatch.setattr(
        "chess_harness.snapshot_leaderboard.export_leaderboard_snapshot",
        fake_export,
    )

    assert cmd_finished_db_list() == 0
    assert cmd_finished_db_restore(game_id, export_snapshot=True) == 0

    assert gm.game_exists(game_id)
    restored = gm.load_state(game_id)
    assert restored is not None
    assert restored["status"] == "finished"
    assert restored["result"] == "1-0"
    assert gm.get_pgn_path(game_id).read_text(encoding="utf-8") == pgn
    assert not gm.get_board_path(game_id).exists()

    finished_ids = {g["game_id"] for g in gm.list_games(status_filter="finished")}
    assert game_id in finished_ids

    results = [r for r in rm.load_results() if r.get("game_id") == game_id]
    assert len(results) == 1
    assert results[0]["result"] == "1-0"
    assert rebuild_calls
    assert snapshot_calls


def test_restore_skips_results_when_already_present(tmp_path, monkeypatch):
    db_path = tmp_path / "finished_games.sqlite"
    monkeypatch.setenv("CHESS_HARNESS_FINISHED_DB", str(db_path))
    harness = tmp_path / "harness"
    harness.mkdir()
    monkeypatch.setenv("CHESS_HARNESS_DIR", str(harness))

    gm = GameManager(str(harness))
    rm = ResultsManager(base_dir=str(harness))
    game_id = "keep-results"
    state = _scored_state(game_id, result="0-1")
    gm.get_game_dir(game_id).mkdir(parents=True, exist_ok=True)
    gm.save_state(game_id, state)
    gm.get_pgn_path(game_id).write_text('[Result "0-1"]\n', encoding="utf-8")
    rm.append_result(
        {
            "ts": "2026-07-31T13:00:00",
            "game_id": game_id,
            "model_name": "agent-a",
            "result": "0-1",
            "agent_color": "WHITE",
        }
    )
    assert record_scored_finish(
        game_id, state, db_path=db_path, game_manager=gm, results_manager=rm
    )

    assert gm.delete_game(game_id)
    # Leave the results row; restore should not duplicate it.
    summary = restore_finished_game(
        game_id, db_path=db_path, game_manager=gm, results_manager=rm
    )
    assert summary["results_merged"] == 0
    assert gm.game_exists(game_id)
    assert len([r for r in rm.load_results() if r.get("game_id") == game_id]) == 1


def test_restore_missing_game_id(tmp_path, monkeypatch, capsys):
    db_path = tmp_path / "finished_games.sqlite"
    monkeypatch.setenv("CHESS_HARNESS_FINISHED_DB", str(db_path))
    harness = tmp_path / "harness"
    harness.mkdir()
    monkeypatch.setenv("CHESS_HARNESS_DIR", str(harness))

    assert cmd_finished_db_restore("no-such-game") == 1
    assert "No finished game in DB" in capsys.readouterr().out
