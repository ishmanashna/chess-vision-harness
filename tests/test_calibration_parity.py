"""Parity: calibration uses same configure_opponent_strength as harness."""

from unittest.mock import MagicMock

from chess_harness.engine import configure_opponent_strength
from chess_harness.opponents import Opponent


def test_calibration_parity_patricia():
    opp = Opponent(
        id="patricia:500",
        display_name="Patricia 5",
        type="uci_elo",
        elo=500,
        binary="bin/opponents/patricia_v2.exe",
        uci_elo=500,
        skill_level=1,
        rating_source="patricia_uci",
    )
    engine = MagicMock()
    cfg = configure_opponent_strength(engine, opp)
    assert cfg == {"UCI_LimitStrength": True, "UCI_Elo": 500, "Skill_Level": 1}
