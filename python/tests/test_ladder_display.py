"""Tests for shared ladder display."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from chess_harness.ladder_display import format_opponent_ladder_cli
from chess_harness.opponents import get_catalog

from conftest import LOW_OPPONENT


def test_opponent_ladder_cli_lists_catalog_ids():
    text = format_opponent_ladder_cli(get_catalog())
    assert LOW_OPPONENT in text
    assert "random" in text
    assert "inverse-sf:abyss" in text
    assert "Stockfish handicaps" in text
    assert "stockfish:0" in text
    assert "patricia" not in text.lower()
    assert "stockfish-handicap:blitz50" not in text
    assert "Skill -5" not in text
