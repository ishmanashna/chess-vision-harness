"""Tests for opponent catalog and ELO-weighted selection."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from chess_harness.calibration_view import ladder_elo_for_opponent
from chess_harness.opponents import get_catalog, opponent_elo_from_result, stockfish_skill_to_elo

from conftest import LOW_OPPONENT


def test_catalog_loads():
    catalog = get_catalog()
    assert len(catalog.opponents) >= 21
    assert catalog.get("stockfish:5").elo == stockfish_skill_to_elo(5)


def test_select_by_elo_prefers_similar_rating():
    catalog = get_catalog()
    opp = catalog.get(LOW_OPPONENT)
    target = ladder_elo_for_opponent(opp)
    picks = [catalog.select_by_elo(target).id for _ in range(50)]
    assert LOW_OPPONENT in picks


def test_select_by_elo_excludes_far_anchors():
    """Low agents must not draw 3000+ Stockfish via the soft weight floor."""
    catalog = get_catalog()
    picks = [catalog.select_by_elo(292).id for _ in range(80)]
    far = []
    for oid in picks:
        opp = catalog.get(oid)
        elo = ladder_elo_for_opponent(opp)
        if elo >= 2500:
            far.append((oid, elo))
    assert not far, f"unexpected far pairings: {far[:5]}"


def test_negative_skill_rejected():
    catalog = get_catalog()
    try:
        catalog.resolve_opponent_id(skill=-1)
        assert False, "expected ValueError"
    except ValueError as e:
        assert "Negative" in str(e)


def test_skill_alias_maps_to_stockfish():
    catalog = get_catalog()
    assert catalog.resolve_opponent_id(skill=5) == "stockfish:5"


def test_opponent_elo_from_result_uses_calibrated_ladder():
    catalog = get_catalog()
    opp = catalog.get(LOW_OPPONENT)
    calibrated = ladder_elo_for_opponent(opp)
    resolved = opponent_elo_from_result({"opponent_id": LOW_OPPONENT}, catalog)
    assert resolved == calibrated
