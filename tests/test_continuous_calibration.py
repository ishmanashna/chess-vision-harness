"""Tests for continuous per-engine calibration."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
ROOT = os.path.join(os.path.dirname(__file__), "..", "elo_calibration")
sys.path.insert(0, ROOT)

from chess_harness.continuous_calibration import (  # noqa: E402
    build_random_match,
    can_continuously_calibrate,
    clamp_parallel,
    get_continuous_calibration,
    list_calibratable_engine_ids,
    normalize_pairing_mode,
    pick_opponent,
    pick_similar_opponent,
)

from conftest import LOW_OPPONENT  # noqa: E402

LOW = LOW_OPPONENT
MID = "stockfish-handicap:noise22"


def test_pick_similar_opponent_never_self():
    for _ in range(20):
        opp = pick_similar_opponent(MID)
        assert opp != MID


def test_pick_similar_opponent_excludes_anchors():
    from chess_harness.opponents import get_catalog
    from calibration.ratings import is_anchor

    cat = get_catalog()
    for _ in range(40):
        opp = pick_similar_opponent(LOW)
        assert not is_anchor(cat.get(opp))


def test_pick_opponent_random_includes_anchors():
    from chess_harness.opponents import get_catalog
    from calibration.ratings import is_anchor

    cat = get_catalog()
    seen = set()
    for _ in range(120):
        seen.add(pick_opponent(LOW, pairing_mode="random"))
    anchor_picks = [o for o in seen if is_anchor(cat.get(o))]
    assert anchor_picks, f"expected anchor tiers in pool, got: {sorted(seen)}"


def test_pick_opponent_anchors_only():
    from chess_harness.opponents import get_catalog
    from calibration.ratings import is_anchor

    cat = get_catalog()
    for _ in range(30):
        opp = pick_opponent(LOW, pairing_mode="anchors")
        assert is_anchor(cat.get(opp))


def test_pick_opponent_allows_large_elo_gaps_in_random():
    seen = set()
    for _ in range(80):
        seen.add(pick_opponent(LOW, pairing_mode="random"))
    assert "stockfish-handicap:noise92" in seen or "stockfish:0" in seen


def test_normalize_pairing_mode_rejects_unknown():
    with pytest.raises(ValueError, match="pairing_mode"):
        normalize_pairing_mode("nonsense")


def test_cannot_continuously_calibrate_anchor():
    assert not can_continuously_calibrate("stockfish:0")
    assert can_continuously_calibrate(LOW)
    assert can_continuously_calibrate("random")


def test_list_calibratable_engine_ids_includes_random():
    ids = list_calibratable_engine_ids()
    assert "random" in ids
    assert "stockfish:0" not in ids


def test_pick_opponent_fixed_opponent():
    assert pick_opponent(
        LOW,
        pairing_mode="fixed",
        fixed_opponent_id="stockfish:0",
    ) == "stockfish:0"


def test_pick_opponent_fixed_rejects_self():
    import pytest

    with pytest.raises(RuntimeError, match="itself"):
        pick_opponent(
            LOW,
            pairing_mode="fixed",
            fixed_opponent_id=LOW,
        )


def test_manager_fixed_opponent():
    mgr = get_continuous_calibration()
    assert mgr.set_fixed_opponent("stockfish:0") == "stockfish:0"
    mgr.set_pairing_mode("random")
    mgr.set_pairing_mode("floaters")


def test_manager_pairing_mode_default():
    from chess_harness.continuous_calibration import ContinuousCalibrationManager

    mgr = ContinuousCalibrationManager()
    assert mgr.pairing_mode() == "floaters"


def test_clamp_parallel():
    assert clamp_parallel(0) == 1
    assert clamp_parallel(4) == 4
    assert clamp_parallel(99) == 99
    assert clamp_parallel(150) == 100


def test_build_random_match_uses_both_sides():
    m = build_random_match(LOW, "stockfish:0")
    ids = {m.white_id, m.black_id}
    assert ids == {LOW, "stockfish:0"}
