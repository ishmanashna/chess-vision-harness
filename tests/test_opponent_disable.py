"""Tests for opponent enable/disable and eligibility filters."""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from conftest import LOW_OPPONENT, UNCALIBRATED_OPPONENT  # noqa: E402

from chess_harness.opponents import OpponentCatalog, get_catalog, reload_catalog


@pytest.fixture
def temp_catalog(tmp_path):
    src = get_catalog().path
    dest = tmp_path / "opponents.json"
    dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    catalog = OpponentCatalog(dest)
    yield catalog
    reload_catalog()


def test_set_enabled_persists(temp_catalog):
    opp = temp_catalog.set_enabled("random", False)
    assert not opp.enabled
    reloaded = OpponentCatalog(temp_catalog.path)
    assert not reloaded.get("random").enabled
    reloaded.set_enabled("random", True)
    assert reloaded.get("random").enabled


def test_disabled_excluded_from_selection(temp_catalog):
    temp_catalog.set_enabled(LOW_OPPONENT, False)
    picks = [temp_catalog.select_by_elo(500).id for _ in range(40)]
    assert LOW_OPPONENT not in picks


def test_resolve_disabled_raises(temp_catalog):
    temp_catalog.set_enabled(LOW_OPPONENT, False)
    with pytest.raises(ValueError, match="disabled"):
        temp_catalog.resolve_opponent_id(opponent_id=LOW_OPPONENT)


def test_resolve_disabled_skill_raises(temp_catalog):
    temp_catalog.set_enabled("stockfish:5", False)
    with pytest.raises(ValueError, match="disabled"):
        temp_catalog.resolve_opponent_id(skill=5)


def test_is_eligible_requires_enabled_and_playable(temp_catalog):
    opp = temp_catalog.get("random")
    assert temp_catalog.is_eligible(opp)
    temp_catalog.set_enabled("random", False)
    assert not temp_catalog.is_eligible(temp_catalog.get("random"))
