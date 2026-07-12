"""Stockfish harness opponents in catalog."""

import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from chess_harness.engine import configure_opponent_strength, play_opponent_move
from chess_harness.opponents import Opponent, get_catalog


def test_catalog_has_handicap_stockfish():
    catalog = get_catalog()
    blitz = catalog.get("stockfish-handicap:blitz50")
    depth = catalog.get("stockfish-handicap:depth6")
    depth10 = catalog.get("stockfish-handicap:depth10")
    assert blitz.type == "stockfish_harness"
    assert blitz.harness == {"movetime_ms": 50}
    assert depth.harness["depth"] == 6
    assert depth10.harness["depth"] == 10


def test_configure_includes_harness_snapshot():
    opp = get_catalog().get("stockfish-handicap:depth6")
    engine = MagicMock()
    cfg = configure_opponent_strength(engine, opp)
    assert cfg["UCI_Elo"] == 1320
    assert cfg["harness"]["depth"] == 6


def test_play_opponent_move_uses_depth_limit():
    opp = Opponent(
        id="test-harness",
        display_name="Test",
        type="stockfish_harness",
        elo=900,
        uci_elo=1320,
        skill_level=0,
        harness={"depth": 4},
    )
    adapter = MagicMock()
    board = MagicMock()
    board.legal_moves = []
    play_opponent_move(adapter, opp, board)
    adapter.play.assert_called_once()
    assert adapter.play.call_args.kwargs["depth"] == 4
