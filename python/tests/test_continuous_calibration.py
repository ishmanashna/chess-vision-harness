"""Tests for continuous per-engine calibration."""

import random
import sys
from pathlib import Path

import pytest

PYTHON_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = PYTHON_ROOT.parent
sys.path.insert(0, str(PYTHON_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "elo_calibration"))

from chess_harness.calibration_view import merge_calibration_ratings  # noqa: E402
from chess_harness.continuous_calibration import (  # noqa: E402
    build_random_match,
    can_continuously_calibrate,
    clamp_parallel,
    display_elo,
    get_continuous_calibration,
    list_calibratable_engine_ids,
    normalize_pairing_mode,
    pick_opponent,
    pick_similar_opponent,
)
from chess_harness.opponents import get_catalog  # noqa: E402

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


def test_pick_opponent_random_reaches_far_elo_opponents():
    """Random mode is unweighted — opponents far from focus ELO remain in the pool."""
    cat = get_catalog()
    cal = merge_calibration_ratings()
    focus_elo = display_elo(cat.get(LOW), cal)
    far_ids = [
        o.id
        for o in cat.list_opponents()
        if o.id != LOW
        and o.enabled
        and cat._is_playable(o)
        and abs(display_elo(o, cal) - focus_elo) >= 400
    ]
    assert far_ids, "catalog needs opponents ≥400 ELO from LOW for this check"

    rng = random.Random(0)
    seen = set()
    for _ in range(600):
        seen.add(pick_opponent(LOW, pairing_mode="random", rng=rng))
    assert any(fid in seen for fid in far_ids), (
        f"random mode never picked a far opponent in 600 seeded draws; "
        f"far pool sample: {sorted(far_ids)[:5]}"
    )


def test_normalize_pairing_mode_rejects_unknown():
    with pytest.raises(ValueError, match="pairing_mode"):
        normalize_pairing_mode("nonsense")


def test_normalize_pairing_mode_accepts_anchors_self():
    assert normalize_pairing_mode("anchors-self") == "anchors-self"


def test_pick_opponent_anchors_self_only_anchors():
    from chess_harness.opponents import get_catalog
    from calibration.ratings import is_anchor

    cat = get_catalog()
    for _ in range(30):
        opp = pick_opponent("stockfish:0", pairing_mode="anchors-self")
        assert is_anchor(cat.get(opp)), opp
        assert opp != "stockfish:0"


def test_cannot_continuously_calibrate_anchor():
    assert not can_continuously_calibrate("stockfish:0")
    assert can_continuously_calibrate(LOW)
    assert can_continuously_calibrate("random")


def test_can_continuously_calibrate_anchor_under_anchors_self():
    from calibration.ratings import is_anchor

    cat = get_catalog()
    for o in cat.list_opponents():
        if is_anchor(o):
            assert can_continuously_calibrate(o.id, pairing_mode="anchors-self")
            assert not can_continuously_calibrate(o.id, pairing_mode="floaters")
            assert not can_continuously_calibrate(o.id)
            continue
        assert can_continuously_calibrate(o.id, pairing_mode="floaters") == (
            o.enabled and cat._is_playable(o)
        )
        assert not can_continuously_calibrate(o.id, pairing_mode="anchors-self")


def test_list_calibratable_engine_ids_anchors_self_only_anchors():
    from calibration.ratings import is_anchor

    cat = get_catalog()
    ids = list_calibratable_engine_ids(pairing_mode="anchors-self")
    assert ids
    for oid in ids:
        assert is_anchor(cat.get(oid)), oid
    anchors = {o.id for o in cat.list_opponents() if is_anchor(o) and o.enabled and cat._is_playable(o)}
    assert set(ids) == anchors
    assert not list_calibratable_engine_ids(pairing_mode="floaters") or all(
        not is_anchor(cat.get(oid)) for oid in list_calibratable_engine_ids(pairing_mode="floaters")
    )


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


def test_start_all_anchors_self_starts_only_anchors(monkeypatch):
    import asyncio

    from chess_harness.continuous_calibration import ContinuousCalibrationManager
    from calibration.ratings import is_anchor
    from chess_harness.opponents import get_catalog

    cat = get_catalog()
    mgr = ContinuousCalibrationManager()
    assert mgr.set_pairing_mode("anchors-self") == "anchors-self"

    started: list = []

    async def fake_start(engine_id, *, parallel=1):
        started.append(engine_id)

    monkeypatch.setattr(mgr, "start", fake_start)

    async def go():
        return await mgr.start_all(parallel=1)

    result = asyncio.run(go())
    assert result == started
    assert started
    for oid in started:
        assert is_anchor(cat.get(oid)), oid


def test_enrich_rating_rows_anchors_get_controls_only_in_anchors_self():
    from chess_harness.continuous_calibration import ContinuousCalibrationManager

    rows = [{"id": "stockfish:0", "elo": 1350, "anchor": True, "catalog_elo": 1350}]
    mgr = ContinuousCalibrationManager()
    assert mgr.pairing_mode() == "floaters"
    out = mgr.enrich_rating_rows(rows)
    assert out[0]["can_calibrate"] is False
    assert out[0]["activity"] == "anchor"
    assert out[0]["continuous"] is False

    mgr.set_pairing_mode("anchors-self")
    out = mgr.enrich_rating_rows(rows)
    assert out[0]["can_calibrate"] is True
    assert out[0]["activity"] == "idle"
    assert out[0]["continuous"] is False
    assert out[0]["playing"] == 0


def test_clamp_parallel():
    assert clamp_parallel(0) == 1
    assert clamp_parallel(4) == 4
    assert clamp_parallel(99) == 99
    assert clamp_parallel(150) == 100


def test_build_random_match_uses_both_sides():
    m = build_random_match(LOW, "stockfish:0")
    ids = {m.white_id, m.black_id}
    assert ids == {LOW, "stockfish:0"}
