"""Phase 2: finished-db import-live from harness games dirs."""

from __future__ import annotations

import json

from chess_harness.finished_games_db import (
    get_finished_game,
    import_live_finished_games,
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


def test_import_live_two_fixtures_idempotent(tmp_path, monkeypatch):
    db_path = tmp_path / "finished_games.sqlite"
    monkeypatch.setenv("CHESS_HARNESS_FINISHED_DB", str(db_path))
    harness = tmp_path / "harness"
    harness.mkdir()
    monkeypatch.setenv("CHESS_HARNESS_DIR", str(harness))

    gm = GameManager(str(harness))
    rm = ResultsManager(base_dir=str(harness))

    for gid, result in (("import-a", "1-0"), ("import-b", "0-1")):
        state = _scored_state(gid, result=result)
        gm.get_game_dir(gid).mkdir(parents=True, exist_ok=True)
        gm.save_state(gid, state)
        gm.get_pgn_path(gid).write_text(
            f'[Result "{result}"]\n\n1. e4 e5 {result}\n', encoding="utf-8"
        )
        rm.append_result(
            {
                "ts": "2026-07-31T12:00:00",
                "game_id": gid,
                "model_name": "agent-a",
                "result": result,
                "agent_color": "WHITE",
            }
        )

    # Unscored finished game must be skipped.
    star_id = "import-star"
    star = _scored_state(star_id, result="*")
    star["end_reason"] = "inactivity"
    gm.get_game_dir(star_id).mkdir(parents=True, exist_ok=True)
    gm.save_state(star_id, star)

    first = import_live_finished_games(
        db_path=db_path, game_manager=gm, results_manager=rm
    )
    assert first["imported"] == 2
    assert first["skipped"] == 1
    assert set(first["game_ids"]) == {"import-a", "import-b"}

    row_a = get_finished_game("import-a", db_path=db_path)
    row_b = get_finished_game("import-b", db_path=db_path)
    assert row_a is not None and row_a["result"] == "1-0"
    assert row_b is not None and row_b["result"] == "0-1"
    assert json.loads(row_a["results_json"])[0]["game_id"] == "import-a"
    assert get_finished_game(star_id, db_path=db_path) is None

    second = import_live_finished_games(
        db_path=db_path, game_manager=gm, results_manager=rm
    )
    assert second["imported"] == 2
    assert set(second["game_ids"]) == {"import-a", "import-b"}
    # Still exactly two scored rows (idempotent upsert).
    import sqlite3

    with sqlite3.connect(str(db_path)) as conn:
        count = conn.execute("SELECT COUNT(*) FROM finished_games").fetchone()[0]
    assert count == 2
