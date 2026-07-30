"""Resign must persist finished state before scheduling quality analysis."""

from __future__ import annotations

from unittest.mock import patch

from chess_harness.board_controller import BoardController
from chess_harness.game_manager import GameManager
from chess_harness.game_types import GAME_TYPE_HUMAN_VS_AGENT
from chess_harness.human_vs_agent import HumanVsAgentPlay


def test_human_agent_resign_schedules_quality_after_save(tmp_path, monkeypatch):
    harness = tmp_path / "harness"
    harness.mkdir()
    monkeypatch.setenv("CHESS_HARNESS_DIR", str(harness))
    gm = GameManager(str(harness))
    ctrl = BoardController(gm)
    play = HumanVsAgentPlay(ctrl)

    game_id = "resign-q"
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

    seen = {}

    def capture_schedule(gid, state=None, **kwargs):
        disk = gm.load_state(gid)
        seen["status"] = disk.get("status") if disk else None
        seen["result"] = disk.get("result") if disk else None

    with patch.object(ctrl, "_schedule_quality_if_scored", side_effect=capture_schedule):
        out = play.resign(game_id)

    assert out["ok"] is True
    assert seen["status"] == "finished"
    assert seen["result"] == "0-1"
