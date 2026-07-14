"""Parity: calibration uses same configure_opponent_strength as harness."""

from unittest.mock import MagicMock

from chess_harness.engine import configure_opponent_strength
from chess_harness.opponents import Opponent


def test_calibration_parity_stockfish_harness():
    opp = Opponent(
        id="stockfish-handicap:noise10",
        display_name="Stockfish 17.1 (10% noise)",
        type="stockfish_harness",
        elo=820,
        uci_elo=1320,
        skill_level=0,
        rating_source="stockfish_harness",
        harness={"movetime_ms": 50, "random_move_pct": 0.1},
    )
    engine = MagicMock()
    cfg = configure_opponent_strength(engine, opp)
    assert cfg["UCI_LimitStrength"] is True
    assert cfg["UCI_Elo"] == 1320
    assert cfg["harness"]["random_move_pct"] == 0.1
