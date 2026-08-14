"""Stockfish harness opponents in catalog."""

import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from chess_harness.engine import configure_opponent_strength, play_opponent_move
from chess_harness.opponents import Opponent, get_catalog


def test_catalog_has_handicap_stockfish():
    catalog = get_catalog()
    noise7 = catalog.get("stockfish-handicap:noise7")
    depth = catalog.get("stockfish-handicap:depth4")
    noise10 = catalog.get("stockfish-handicap:noise10")
    assert noise7.type == "stockfish_harness"
    assert noise7.harness == {"movetime_ms": 50, "random_move_pct": 0.07}
    assert depth.harness["depth"] == 2
    assert noise10.harness["random_move_pct"] == 0.1


def test_configure_includes_harness_snapshot():
    opp = get_catalog().get("stockfish-handicap:depth4")
    engine = MagicMock()
    cfg = configure_opponent_strength(engine, opp)
    assert cfg["UCI_Elo"] == 1320
    assert cfg["harness"]["depth"] == 2


def test_configure_handicap_noise_snapshot():
    opp = get_catalog().get("stockfish-handicap:noise10")
    engine = MagicMock()
    cfg = configure_opponent_strength(engine, opp)
    assert cfg["UCI_LimitStrength"] is True
    assert cfg["harness"]["random_move_pct"] == 0.1


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
