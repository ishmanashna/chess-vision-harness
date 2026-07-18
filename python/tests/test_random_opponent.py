"""Tests for random-move builtin opponent."""

import os
import sys

import chess

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from chess_harness.engine import OpponentEngineManager  # noqa: E402
from chess_harness.opponents import get_catalog  # noqa: E402


def test_random_opponent_in_catalog():
    opp = get_catalog().get("random")
    assert opp.type == "random"
    assert get_catalog()._is_playable(opp)


def test_random_opponent_plays_legal_move():
    opp = get_catalog().get("random")
    mgr = OpponentEngineManager()
    board = chess.Board()
    try:
        result = mgr.play(opp, board)
        assert result.move in board.legal_moves
    finally:
        mgr.release()


def test_random_opponent_new_game(tmp_path, monkeypatch):
    monkeypatch.setenv("CHESS_HARNESS_DIR", str(tmp_path / "harness"))
    from chess_harness import commands

    result = commands.cmd_new(
        "random-harness-test",
        "white",
        None,
        model_name="composer-2.5",
        force=True,
        opponent="random",
    )
    assert result["ok"] is True
    assert result["opponent_id"] == "random"
    assert result["your_turn"] is True
