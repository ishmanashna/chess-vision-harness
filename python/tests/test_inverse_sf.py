"""Tests for inverse Stockfish opponent move selection."""

import os
import sys
from unittest.mock import MagicMock, patch

import chess
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from chess_harness.inverse_sf import pick_inverse_move, rank_legal_moves


def test_pick_worst_is_lowest_ranked():
    moves = [chess.Move.from_uci(u) for u in ("e2e4", "d2d4", "a2a3")]
    ranked = [(m, float(i)) for i, m in enumerate(reversed(moves))]
    assert pick_inverse_move(ranked, "worst") == moves[0]


def test_pick_exclude_top1_not_best():
    e4 = chess.Move.from_uci("e2e4")
    d4 = chess.Move.from_uci("d2d4")
    a3 = chess.Move.from_uci("a2a3")
    ranked = [(e4, 300.0), (d4, 100.0), (a3, 50.0)]
    for _ in range(20):
        pick = pick_inverse_move(ranked, "exclude_top1")
        assert pick != e4


def test_pick_second_worst():
    e4 = chess.Move.from_uci("e2e4")
    d4 = chess.Move.from_uci("d2d4")
    a3 = chess.Move.from_uci("a2a3")
    ranked = [(e4, 300.0), (d4, 100.0), (a3, 50.0)]
    assert pick_inverse_move(ranked, "second_worst") == d4


def test_pick_abyss_from_blunder_cluster():
    e4 = chess.Move.from_uci("e2e4")
    d4 = chess.Move.from_uci("d2d4")
    a3 = chess.Move.from_uci("a2a3")
    ranked = [(e4, 300.0), (d4, 50.0), (a3, -400.0)]
    pick = pick_inverse_move(ranked, "abyss")
    assert pick == a3


def test_catalog_has_inverse_sf_entries():
    from chess_harness.opponents import get_catalog

    catalog = get_catalog()
    inv = catalog.get("inverse-sf:abyss")
    assert inv.type == "inverse_sf"
    assert inv.inverse["mode"] == "abyss"
    assert inv.inverse["depth"] == 20
    assert inv.enabled is True


def test_catalog_has_noise_harnesses():
    from chess_harness.opponents import get_catalog

    catalog = get_catalog()
    n7 = catalog.get("stockfish-handicap:noise7")
    assert n7.harness["random_move_pct"] == 0.07
    assert n7.harness["movetime_ms"] == 50
    n10 = catalog.get("stockfish-handicap:noise10")
    assert n10.harness["random_move_pct"] == 0.1


def test_removed_opponents_not_in_catalog():
    from chess_harness.opponents import get_catalog

    catalog = get_catalog()
    assert catalog.get("stockfish-handicap:noise10").enabled is True
    assert catalog.get("inverse-sf:exclude-top1").enabled is True
    with pytest.raises(ValueError):
        catalog.get("stockfish-handicap:blitz800")
    with pytest.raises(ValueError):
        catalog.get("stockfish-handicap:noise3")


def test_disabled_opponent_not_in_calibration_pick(tmp_path, monkeypatch):
    from chess_harness.continuous_calibration import pick_opponent
    from chess_harness.opponents import OpponentCatalog, get_catalog, reload_catalog

    dest = tmp_path / "opponents.json"
    dest.write_text(get_catalog().path.read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setenv("OPPONENTS_FILE", str(dest))
    reload_catalog()
    catalog = get_catalog()
    catalog.set_enabled("stockfish-handicap:noise12", False)
    try:
        for _ in range(40):
            oid = pick_opponent("stockfish-handicap:noise10", pairing_mode="random")
            assert oid != "stockfish-handicap:noise12"
            assert catalog.get(oid).enabled
    finally:
        reload_catalog()


def test_manager_release_quits_all_pooled_adapters():
    from chess_harness.engine import OpponentEngineManager
    from chess_harness.opponents import get_catalog

    with patch("chess_harness.engine.chess.engine.SimpleEngine.popen_uci") as popen:
        engines = [MagicMock(), MagicMock()]
        popen.side_effect = engines
        catalog = get_catalog()
        mgr = OpponentEngineManager()
        mgr.get_adapter(catalog.get("stockfish-handicap:noise10"))
        mgr.get_adapter(catalog.get("inverse-sf:worst-d10"))
        assert popen.call_count == 2
        mgr.release()
        for eng in engines:
            eng.quit.assert_called()


def test_stockfish_pool_reuses_subprocess():
    from chess_harness.engine import OpponentEngineManager
    from chess_harness.opponents import get_catalog

    catalog = get_catalog()
    a = catalog.get("stockfish-handicap:noise10")
    b = catalog.get("stockfish-handicap:noise12")
    with patch("chess_harness.engine.chess.engine.SimpleEngine.popen_uci") as popen:
        engine = MagicMock()
        popen.return_value = engine
        mgr = OpponentEngineManager()
        adapter_a = mgr.get_adapter(a)
        adapter_b = mgr.get_adapter(b)
        assert adapter_a is adapter_b
        assert popen.call_count == 1
        mgr.release()
