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
    assert ">Performance</th>" in html
    assert ">% pieces</th>" in html or ">% pieces<" in html or '>% pieces</th>' in html
    assert ">Strength</th>" not in html
    assert ">Eyesight</th>" not in html
    assert "Play rating" not in html
    assert "Estimated Elo" not in html
    assert "Est. Elo (play)" not in html
    assert "Rebuild that table on the local Calibration page" not in html
    assert 'script src="/js/engines.js"' not in html
    assert 'title="Estimated strength from move accuracy' in html
    assert "leaderboard-layout-stack" in html
    assert 'class="leaderboard-copy"' in html
    assert 'class="leaderboard-tables"' in html
    # Single column: giant table first, explanatory copy below.
    assert html.index("leaderboard-tables") < html.index("leaderboard-copy")
    assert html.index("data-engines-leaderboard") < html.index("How ratings work")
    assert "Leaderboards" in html
    assert 'id="agents-table-heading"' in html


def test_home_mini_ladder_full_columns(create_client):
    client, _ = create_client
    html = client.get("/").text
    # Flavor Benchmark labels only on Home — not a fork of Leaderboards naming.
    assert ">Strength</th>" in html
    assert ">Eyesight</th>" in html
    assert ">% pieces</th>" not in html
    assert ">Performance</th>" not in html
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
    assert 'colspan="7"' in html
    assert 'data-sort="puzzle_rating"' in html
    assert 'data-sort="identify_mean_accuracy"' in html
    assert "data-show-home-benchmark" in html
    assert 'data-sort="games"' not in html
    assert ">Benchmark</h2>" in html
    assert "flavor snapshot" in html


def test_leaderboard_keeps_scored_games_copy(create_client):
    client, _ = create_client
    html = client.get("/leaderboard/").text
    assert "Model id" not in html
    assert "data-show-model-id" not in html
    assert "Finished games with a real result" in html
    assert "100 rated games" in html
    # Agents table: 11 columns (6 ladder + 5 unified puzzle/identify stats).
    assert 'colspan="11"' in html
    assert "Pz att" not in html
    assert "Pz sol" not in html
    assert 'data-sort="identify_full_ratio"' in html
    assert '>Id</th>' in html
    assert 'data-sort="puzzle_solve_ratio"' in html


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

    home = _read_public("index.html")
    leaderboard = _read_public("leaderboard/index.html")
    launch = _read_public("launch/index.html")
    css = _read_public("css/site.css")
    # Status/callout chrome may use strong; body copy paragraphs must not.
    about = home[home.index('class="about-copy"') : home.index("</section>", home.index('class="about-copy"'))]
    assert "<strong>" not in about
    rating = leaderboard[
        leaderboard.index('class="rating-explain"') : leaderboard.index(
            "</section>", leaderboard.index('class="rating-explain"')
        )
    ]
    assert "<strong>" not in rating
    allowed_strong = {
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
        block = css[css.index(selector) :]
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
