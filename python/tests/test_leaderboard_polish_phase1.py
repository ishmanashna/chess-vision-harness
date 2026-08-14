"""Phase 1: leaderboard labels, engine columns, home mini-ladder."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest_plugins = ["test_create_game"]

REPO_ROOT = Path(__file__).resolve().parents[2]
PUBLIC_SITE = REPO_ROOT / "public-site"


def _read_public(rel: str) -> str:
    return (PUBLIC_SITE / rel).read_text(encoding="utf-8")


def test_leaderboard_performance_labels(create_client):
    client, _ = create_client
    html = client.get("/leaderboard/").text
    assert "Performance" in html
    assert "Play rating" not in html
    assert "Estimated Elo" not in html
    assert "Est. Elo (play)" not in html
    assert "Rebuild that table on the local Calibration page" not in html
    assert 'script src="/js/engines.js"' not in html
    assert 'title="Estimated strength from move accuracy' in html
    assert 'class="leaderboard-layout"' in html
    assert 'class="leaderboard-copy"' in html
    assert 'class="leaderboard-tables"' in html
    # Copy (Agents intro + How ratings) precedes tables column.
    assert html.index("leaderboard-copy") < html.index("leaderboard-tables")
    assert html.index("How ratings work") < html.index("data-engines-leaderboard")
    assert html.index('id="ladder-heading"') < html.index("leaderboard-tables")


def test_home_mini_ladder_full_columns(create_client):
    client, _ = create_client
    html = client.get("/").text
    assert "Performance" in html
    assert "Estimated Elo" not in html
    assert "Est. Elo (play)" not in html
    assert "data-leaderboard-full" in html
    assert "home-ladder-note" not in html
    assert "1500" not in html
    assert "club player" not in html
    assert "chess.com" not in html
    assert "Scale check" not in html
    assert 'title="Results-only ladder Elo' in html
    assert "Model id" not in html
    assert "data-show-model-id" not in html
    assert 'colspan="6"' in html
    assert "Finished games with a real result" in html


def test_leaderboard_keeps_scored_games_copy(create_client):
    client, _ = create_client
    html = client.get("/leaderboard/").text
    assert "Model id" not in html
    assert "data-show-model-id" not in html
    assert "Finished games with a real result" in html
    assert "100 rated games" in html
    # Agents + puzzle-content loading rows: 9 columns each after the
    # solve-rate and Themes column removals (P5).
    assert 'colspan="9"' in html
    assert 'colspan="10"' not in html


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


def test_common_js_provisional_ignores_display_games():
    js = _read_public("js/common.js")
    assert "typeof agent.provisional === \"boolean\"" in js
    assert "games < 100" not in js
    assert "data-show-model-id" in js
    assert "leaderboardColCount" in js


def test_calibration_html_performance_label():
    import os
    import sys

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
    from chess_harness.ladder_display import render_calibration_html

    html = render_calibration_html()
    assert "Performance" in html
    assert "Play rating" not in html
    assert "Estimated Elo" not in html
    assert "Est. Elo (play)" not in html


def test_prose_copy_is_plain_and_justified():
    import re

    leaderboard = _read_public("leaderboard/index.html")
    launch = _read_public("launch/index.html")
    css = _read_public("css/site.css")
    allowed_strong = {
        "*",
        "Launcher unavailable",
        "Game server offline",
        "No live games while the server is offline",
    }
    for html in (leaderboard, launch):
        for match in re.finditer(r"<strong>([^<]*)</strong>", html):
            assert match.group(1) in allowed_strong, match.group(1)
    for selector in (
        ".about-copy p",
        ".leaderboard-copy p",
        ".rating-explain p",
        ".info-block p",
        ".engines-section > p",
    ):
        block = css[css.index(selector):]
        assert "text-align: justify" in block.split("}")[0], selector


def test_calibration_lead_and_legend_justified():
    import os
    import sys

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
    from chess_harness.ladder_display import render_calibration_html

    html = render_calibration_html()
    assert "text-align:justify" in html
    assert html.count("cal-lead") == 2
    assert html.count("cal-legend") == 3
    assert html.count("<strong>") == html.count("</strong>")  # balanced markup
