"""Tests for continuous per-engine calibration."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
ROOT = os.path.join(os.path.dirname(__file__), "..", "elo_calibration")
sys.path.insert(0, ROOT)

from chess_harness.continuous_calibration import (  # noqa: E402
    build_random_match,
    can_continuously_calibrate,
    clamp_parallel,
    pick_similar_opponent,
)


def test_pick_similar_opponent_never_self():
    for _ in range(20):
        opp = pick_similar_opponent("patricia:800")
        assert opp != "patricia:800"


def test_pick_similar_opponent_includes_stockfish():
    seen = set()
    for _ in range(50):
        seen.add(pick_similar_opponent("patricia:500"))
    assert any(o.startswith("stockfish") for o in seen)


def test_pick_similar_opponent_allows_large_elo_gaps():
    """Relaxed sigma should sometimes pair distant floaters (not anchors)."""
    seen = set()
    for _ in range(80):
        seen.add(pick_similar_opponent("patricia:500"))
    assert "minimalchess-0.3" in seen or "patricia:1200" in seen


def test_pick_similar_opponent_excludes_anchors():
    from chess_harness.opponents import get_catalog
    from calibration.ratings import is_anchor

    cat = get_catalog()
    for _ in range(40):
        opp = pick_similar_opponent("patricia:500")
        assert not is_anchor(cat.get(opp))


def test_cannot_continuously_calibrate_anchor():
    assert not can_continuously_calibrate("stockfish:0")
    assert can_continuously_calibrate("patricia:500")
    assert can_continuously_calibrate("random")


def test_clamp_parallel():
    assert clamp_parallel(0) == 1
    assert clamp_parallel(4) == 4
    assert clamp_parallel(99) == 99
    assert clamp_parallel(150) == 100


def test_build_random_match_uses_both_sides():
    m = build_random_match("patricia:500", "stockfish:0")
    ids = {m.white_id, m.black_id}
    assert ids == {"patricia:500", "stockfish:0"}
