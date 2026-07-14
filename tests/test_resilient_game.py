"""Tests for timeout-resilient calibration games."""

import os
import sys
from unittest.mock import MagicMock, patch

import chess
import pytest

ROOT = os.path.join(os.path.dirname(__file__), "..", "elo_calibration")
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from calibration.play_config import MatchConfig, PlayConfig  # noqa: E402
from calibration.resilient_game import play_game_resilient  # noqa: E402


def test_play_game_resilient_skips_on_persistent_timeout():
    match = MatchConfig(
        white_id="stockfish-handicap:noise10",
        black_id="stockfish-handicap:noise22",
        white=PlayConfig(),
        black=PlayConfig(),
    )
    board = chess.Board()

    class FakePlayer:
        def __init__(self, opponent_id, config=None, **kwargs):
            self.opponent_id = opponent_id
            self.config = config

        def play(self, _board):
            raise TimeoutError("engine hung")

        def release(self):
            pass

    with patch("calibration.resilient_game.EnginePlayer", FakePlayer):
        result = play_game_resilient(match, max_move_retries=2)
    assert result is None
