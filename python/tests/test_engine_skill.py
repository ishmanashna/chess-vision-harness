"""Tests for Stockfish UCI_Elo opponent configuration."""

from unittest.mock import MagicMock

from chess_harness.engine import StockfishOpponentAdapter
from chess_harness.opponents import stockfish_skill_to_elo


def test_stockfish_skill_to_elo_range():
    assert stockfish_skill_to_elo(0) == 1320
    assert stockfish_skill_to_elo(20) == 3190
    assert stockfish_skill_to_elo(5) == 1788


def test_stockfish_opponent_configures_uci_limit_strength():
    from chess_harness.engine import configure_opponent_strength
    from chess_harness.opponents import Opponent

    opp = Opponent(
        id="stockfish:5",
        display_name="Stockfish 17.1",
        type="stockfish",
        elo=1788,
        uci_elo=1788,
        skill_level=5,
        rating_source="stockfish_uci",
    )
    engine = MagicMock()
    configure_opponent_strength(engine, opp)
    engine.configure.assert_called_with(
        {"UCI_LimitStrength": True, "UCI_Elo": 1788, "Skill Level": 5}
    )


def test_patricia_skill_level_configured():
    from unittest.mock import MagicMock

    from chess_harness.engine import RatedUciOpponentAdapter, configure_opponent_strength
    from chess_harness.opponents import Opponent

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
    engine.configure.assert_called_with(
        {"UCI_LimitStrength": True, "UCI_Elo": 500, "Skill_Level": 1}
    )
    assert cfg["Skill_Level"] == 1


def test_rated_uci_adapter_uses_configure():
    from unittest.mock import MagicMock, patch

    from chess_harness.engine import RatedUciOpponentAdapter
    from chess_harness.opponents import Opponent

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
    with patch.object(RatedUciOpponentAdapter, "_initialize_engine"):
        adapter = RatedUciOpponentAdapter.__new__(RatedUciOpponentAdapter)
        adapter.uci_elo = 500
        adapter.skill_level = 1
        adapter._opponent = opp
        adapter.engine = MagicMock()
        adapter.configure_strength()
        adapter.engine.configure.assert_called_with(
            {"UCI_LimitStrength": True, "UCI_Elo": 500, "Skill_Level": 1}
        )
