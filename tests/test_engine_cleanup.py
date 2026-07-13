"""Tests for engine subprocess cleanup."""

import os
import sys
from unittest.mock import MagicMock, patch

import chess

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "elo_calibration"))

from calibration.engine_player import EnginePlayer, release_all_engines
from calibration.play_config import MatchConfig, PlayConfig
from calibration.resilient_game import play_game_resilient


def test_release_all_engines_idempotent():
    with patch("chess_harness.engine.chess.engine.SimpleEngine.popen_uci") as popen:
        popen.return_value = MagicMock()
        from chess_harness.opponents import get_catalog

        opp = get_catalog().get("stockfish-handicap:noise10")
        board = chess.Board()
        player = EnginePlayer(opp.id, PlayConfig())
        player.play(board)
        release_all_engines()
        release_all_engines()


def test_resilient_game_calls_release_all_engines():
    with patch("calibration.resilient_game.release_all_engines") as release:
        with patch("calibration.resilient_game._play_move_resilient", return_value=(None, MagicMock())):
            play_game_resilient(
                MatchConfig(white_id="random", black_id="random", max_plies=4)
            )
        release.assert_called()
