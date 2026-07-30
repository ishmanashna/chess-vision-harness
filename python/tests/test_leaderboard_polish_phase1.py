"""Phase 1: leaderboard labels, engine columns, home mini-ladder."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest_plugins = ["test_create_game"]

REPO_ROOT = Path(__file__).resolve().parents[2]
PUBLIC_SITE = REPO_ROOT / "public-site"


def _read_public(rel: str) -> str:
    return (PUBLIC_SITE / rel).read_text(encoding="utf-8")


def test_leaderboard_estimated_elo_labels(create_client):
    client, _ = create_client
    html = client.get("/leaderboard/").text
    assert "Estimated Elo" in html
    assert "Est. Elo (play)" not in html
    assert "Rebuild that table on the local Calibration page" not in html
    assert 'script src="/js/engines.js"' not in html
    assert 'title="Estimated strength from move accuracy' in html


def test_home_mini_ladder_full_columns(create_client):
    client, _ = create_client
    html = client.get("/").text
    assert "Estimated Elo" in html
    assert "Est. Elo (play)" not in html
    assert "data-leaderboard-full" in html
    assert "home-ladder-note" not in html
    assert "1500" not in html
    assert "club player" not in html
    assert "chess.com" not in html
    assert "Scale check" not in html
    assert 'title="Results-only ladder Elo' in html
    assert 'colspan="7"' in html


def test_engines_js_renders_six_columns():
    js = _read_public("js/engines.js")
    assert 'colspan="6"' in js
    assert "mean_accuracy" in js
    assert "mean_play_rating" in js
    assert '[data-engines-leaderboard]' not in js


def test_common_js_single_engines_load():
    js = _read_public("js/common.js")
    assert "loadEnginesOnce" in js
    assert "engines.js?v=" in js
    assert 'loadScriptOnce("/js/engines.js")' not in js


def test_calibration_html_estimated_elo_label():
    import os
    import sys

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
    from chess_harness.ladder_display import render_calibration_html

    html = render_calibration_html()
    assert "Estimated Elo" in html
    assert "Est. Elo (play)" not in html
