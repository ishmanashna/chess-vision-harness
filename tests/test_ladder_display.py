"""Tests for shared ladder display."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from chess_harness.ladder_display import format_opponent_ladder_cli
from chess_harness.opponents import get_catalog


def test_opponent_ladder_cli_lists_catalog_ids():
    text = format_opponent_ladder_cli(get_catalog())
    assert "patricia:500" in text
    assert "minimalchess-0.2" in text
    assert "stockfish-handicap:blitz50" in text
    assert "stockfish-handicap:depth6" in text
    assert "Stockfish handicaps" in text
    assert "stockfish:0" in text
    assert "Skill -5" not in text
