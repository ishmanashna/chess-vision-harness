"""Phase 4: shared sortable tables (home, leaderboard, spectator lists)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytest_plugins = ["test_create_game"]

REPO_ROOT = Path(__file__).resolve().parents[2]
PUBLIC_SITE = REPO_ROOT / "public-site"


def _read_public(rel: str) -> str:
    return (PUBLIC_SITE / rel).read_text(encoding="utf-8")


def test_table_sort_helper_api():
    js = _read_public("js/table-sort.js")
    assert "firstNumber" in js
    assert "sortRows" in js
    assert "loadState" in js
    assert "saveState" in js
    assert "paintHeaders" in js
    assert "bindHeaders" in js
    assert "aria-sort" in js
    assert "is-sorted" in js
    # Acc/Performance: first numeric token (white side of "a / b").
    assert r"/-?\d+(?:\.\d+)?/" in js or "-?\\d+(?:\\.\\d+)?" in js


def test_table_sort_first_number_behavior():
    """Mirror the JS firstNumber rule used for Acc/Performance columns."""
    import re as _re

    def first_number(value):
        if value is None or value == "":
            return None
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
        m = _re.search(r"-?\d+(?:\.\d+)?", str(value))
        return float(m.group(0)) if m else None

    assert first_number("91.2% / 88.4%") == 91.2
    assert first_number("1524 / 1498") == 1524.0
    assert first_number("1500*") == 1500.0
    assert first_number("—") is None
    assert first_number(42) == 42.0


def test_home_and_leaderboard_sortable_headers(create_client):
    client, _ = create_client
    home = client.get("/").text
    assert 'script src="/js/table-sort.js"' in home
    assert 'data-sort="name"' in home
    assert 'data-sort="elo"' in home
    assert 'data-sort="mean_accuracy"' in home
    assert 'data-sort="mean_play_rating"' in home
    assert 'data-sort="puzzle_rating"' in home
    assert 'data-sort="identify_mean_accuracy"' in home
    assert 'data-sort="games"' not in home
    # Rank column stays non-sortable.
    assert re.search(r"<th scope=\"col\">#</th>", home)
    assert "data-sort=\"#\"" not in home

    lb = client.get("/leaderboard/").text
    assert 'script src="/js/table-sort.js"' in lb
    assert 'data-sort="name"' in lb
    assert 'data-sort="elo"' in lb
    assert 'data-sort="mean_play_rating"' in lb
    assert 'data-sort="kind"' in lb  # engines

    assert re.search(r"<th scope=\"col\">#</th>", lb)
def test_spectator_loads_table_sort(create_client):
    client, _ = create_client
    html = client.get("/spectator/").text
    assert 'script src="/js/table-sort.js"' in html
    assert html.index("/js/table-sort.js") < html.index("/js/games-list.js")
    assert 'data-sort="performance"' in html
    assert 'data-sort="estimatedElo"' not in html


def test_common_and_engines_use_shared_sorter():
    common = _read_public("js/common.js")
    assert "CVH.tableSort" in common
    assert "cvh-home-ladder-sort" in common
    assert "cvh-leaderboard-agents-sort" in common
    assert 'estimatedElo: "mean_play_rating"' in common
    assert "window.CVH = window.CVH || {}" in common

    engines = _read_public("js/engines.js")
    assert "CVH.tableSort" in engines
    assert "cvh-leaderboard-engines-sort" in engines
    assert "paintHeaders" in engines or "ts.paintHeaders" in engines


def test_sorted_header_css():
    css = _read_public("css/site.css")
    assert ".leaderboard-table th[data-sort]" in css
    assert ".leaderboard-table th[data-sort].is-sorted" in css
    assert ".games-table th[data-sort].is-sorted" in css
