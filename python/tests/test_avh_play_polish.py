"""Phase 8 regression: AvH play polish (hub, play chrome, draw, chat, spectator eval)."""

from __future__ import annotations

from pathlib import Path

import pytest

from chess_harness.spectator_game_page import render_game_view_page
from chess_harness.spectator_human import show_eval_for_state

pytest_plugins = ["test_create_game", "test_human_vs_agent"]

REPO_ROOT = Path(__file__).resolve().parents[2]
PUBLIC_SITE = REPO_ROOT / "public-site"

NAV_ORDER = (
    'id="nav-home"',
    'id="nav-create"',
    'id="nav-spectator"',
    'id="nav-leaderboard"',
    'id="nav-contact"',
)


def _nav_positions(html: str) -> list[int]:
    return [html.index(marker) for marker in NAV_ORDER]


def _read_public(rel: str) -> str:
    return (PUBLIC_SITE / rel).read_text(encoding="utf-8")


def test_nav_order_consistent_across_shells(create_client):
    client, _ = create_client
    for path in ("/launch/", "/spectator/", "/contact/"):
        html = client.get(path).text
        assert _nav_positions(html) == sorted(_nav_positions(html))


def test_human_hub_no_your_games_or_registry_ui(create_client):
    client, _ = create_client
    resp = client.get("/human/", follow_redirects=False)
    assert resp.status_code == 301
    assert resp.headers["location"] == "/launch/?flow=playground"


def test_spectator_my_games_tab_wired(create_client):
    client, _ = create_client
    html = client.get("/spectator/").text
    assert 'data-spec-tab="mygames"' in html
    assert "My games" in html
    assert "human-games-ui.js" in html
    assert "data-human-games-list" in html


def test_human_games_ui_compact_when_format():
    js = _read_public("js/human-games-ui.js")
    assert "HH:mm D/MM/YY" in js
    assert "dateStyle" not in js


def test_create_human_mode_redirects_to_launch(create_client):
    client, _ = create_client
    resp = client.get("/create?mode=human", follow_redirects=False)
    assert resp.status_code == 301
    assert resp.headers["location"] == "/launch/?flow=engine"


def test_create_brief_collapsible_in_js():
    js = _read_public("js/create-result.js")
    assert "brief-collapsible" in js
    assert "<details" in js
    assert "Show agent prompt" in js
    assert "brief-toolbar" in js
    assert "data-copy-brief" in js
    # Copy toolbar must sit outside <details> so it works while collapsed.
    assert js.index("brief-toolbar") < js.index('<details class="brief-collapsible">')


def test_play_chat_enter_sends_without_shift():
    js = _read_public("js/play-chat.js")
    assert 'event.key !== "Enter"' in js or "event.key!=='Enter'" in js
    assert "shiftKey" in js


def test_play_page_single_header_chat_markup(human_client, monkeypatch):
    from test_human_vs_agent import _create_human_game, _register_agent

    client, _ = human_client
    api_key, _ = _register_agent(client)
    data = _create_human_game(client, api_key, monkeypatch=monkeypatch)
    game_id = data["game_id"]

    html = client.get(f"/play/{game_id}").text
    assert html.count('class="play-header"') == 1
    assert "data-play-header-line" in html
    assert ">Play board<" not in html
    assert "30 minutes without a move" not in html
    assert "data-chat-form" in html
    assert 'spellcheck="false"' in html
    assert "data-chat-log" in html
    assert 'class="play-chat-log"' in html
    assert "data-clear-premove" in html
    assert "data-download-slot" in html
    # Cancel premoves sits under the board, not in the resign/draw row.
    actions_start = html.index('class="play-actions"')
    assert "data-clear-premove" not in html[actions_start : actions_start + 600]
    assert html.index("data-clear-premove") < actions_start


def test_spectator_game_page_compact_export_links():
    html = render_game_view_page("game-polish-1")
    assert 'class="export-links"' in html
    assert "Download board PNG" in html
    assert "Copy PGN" in html
    assert "<h2>Export</h2>" not in html
    assert "max-content" in html


def test_spectator_game_page_avh_eval_trusts_api_flag():
    js = (PUBLIC_SITE / "js" / "spectator-game.js").read_text(encoding="utf-8")
    assert "human_vs_agent" in js
    assert "s.show_eval !== false" in js
    # Eval bar hidden only when API says show_eval is false; Elo row still gated for AvH.
    assert 's.game_type !== "human_vs_agent"' in js
    assert "showElo" in js


def test_spectator_game_page_quality_metrics():
    html = render_game_view_page("game-quality-ui")
    js = (PUBLIC_SITE / "js" / "spectator-game.js").read_text(encoding="utf-8")
    assert "state-acc-white" in html
    assert "state-pr-black" in html
    assert "quality-row" in html
    assert "formatAccuracy" in js
    assert "renderQualityMetrics" in js
    assert "shouldKeepPolling" in js
    assert "quality_at" in js
    assert "not ladder Elo" in html
    assert "white_accuracy" in js
    assert "Performance" in html
    assert "Estimated Elo" not in html
    assert "Est. Elo (play)" not in html
    assert "const wAccLbl =" in js or "const wAccLbl=" in js
    assert "let wAcc =" in js or "let wAcc=" in js
    # Duplicate const/let wAcc in one function breaks the entire /g/ poll loop.
    assert "const wAcc =" not in js and "const wAcc=" not in js
    # Per-player grouping: white accuracy+elo, then black accuracy+elo.
    assert html.index("state-acc-white-label") < html.index("state-pr-white-label")
    assert html.index("state-pr-white-label") < html.index("state-acc-black-label")
    assert html.index("state-acc-black-label") < html.index("state-pr-black-label")


def test_spectator_game_page_quality_analysing_pending():
    html = render_game_view_page("game-quality-pending")
    js = (PUBLIC_SITE / "js" / "spectator-game.js").read_text(encoding="utf-8")
    assert "isQualityPending" in js
    assert "Analysing…" in js
    assert "quality-pending" in html
    assert 's.result !== "*"' in js
    html = render_game_view_page("game-chat-toggle")
    assert 'id="info-panel-toggle"' in html
    assert 'id="spec-chat-panel"' in html
    assert 'id="spec-chat-log"' in html
    assert "/chat?since=" in js
    assert "Show chat" in html
    assert "setInfoPanelMode" in js
    assert "Spectating" not in html
    assert 'id="info-panel-title"' not in html
    assert "is-covered" in html
    assert "info-panel-slot" in html
    assert "<h2>Game info</h2>" in html
    assert "<h2>Game state</h2>" in html
    assert ">Game</h2>" not in html


def test_spectator_modules_parse():
    import shutil
    import subprocess

    node = shutil.which("node")
    if not node:
        pytest.skip("node not available for JS syntax check")
    for name in ("spectator-game.js", "spectator-board.js"):
        path = PUBLIC_SITE / "js" / name
        result = subprocess.run(
            [node, "--check", str(path)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"{name}: {result.stderr}"


def test_show_eval_for_state_true_for_human_vs_agent():
    state = {"game_type": "human_vs_agent", "status": "in_progress"}
    assert show_eval_for_state(state) is True


@pytest.mark.parametrize("path", ["/launch/"])
def test_launcher_includes_collapsible_inscribe(create_client, path):
    client, _ = create_client
    html = client.get(path).text
    assert "<details" in html
    assert "inscribe-panel" in html
