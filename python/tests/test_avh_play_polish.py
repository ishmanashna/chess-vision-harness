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
    'id="nav-human"',
    'id="nav-contact"',
)


def _nav_positions(html: str) -> list[int]:
    return [html.index(marker) for marker in NAV_ORDER]


def _read_public(rel: str) -> str:
    return (PUBLIC_SITE / rel).read_text(encoding="utf-8")


def test_nav_order_consistent_across_shells(create_client):
    client, _ = create_client
    for path in ("/human/", "/create", "/spectator/", "/contact/"):
        html = client.get(path).text
        assert _nav_positions(html) == sorted(_nav_positions(html))


def test_human_hub_no_your_games_or_registry_ui(create_client):
    client, _ = create_client
    html = client.get("/human/").text
    assert "Your games" not in html
    assert "data-human-games-list" not in html
    assert "human-games-ui.js" not in html
    assert "Resume saved games in Spectator" in html


def test_spectator_my_games_tab_wired(create_client):
    client, _ = create_client
    html = client.get("/spectator/").text
    assert 'data-spec-tab="mygames"' in html
    assert "My games" in html
    assert "human-games-ui.js" in html
    assert "data-human-games-list" in html


def test_create_human_mode_redirect_unchanged(create_client):
    client, _ = create_client
    resp = client.get("/create?mode=human", follow_redirects=False)
    assert resp.status_code == 301
    assert resp.headers["location"] == "/human/"


def test_create_brief_collapsible_in_js():
    js = _read_public("js/create-result.js")
    assert "brief-collapsible" in js
    assert "<details" in js
    assert "Agent prompt (copy this)" in js


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


def test_spectator_game_page_compact_export_links():
    html = render_game_view_page("game-polish-1")
    assert 'class="export-links"' in html
    assert "Download board PNG" in html
    assert "Copy PGN" in html
    assert "<h2>Export</h2>" not in html
    assert "max-content" in html


def test_spectator_game_page_avh_eval_trusts_api_flag():
    html = render_game_view_page("game-polish-2")
    assert "s.show_eval!==false" in html
    assert "human_vs_agent" in html
    # Eval bar hidden only when API says show_eval is false; Elo row still gated for AvH.
    assert "showElo=showEval&&s.game_type!=='human_vs_agent'" in html


def test_spectator_game_page_quality_metrics():
    html = render_game_view_page("game-quality-ui")
    assert "state-acc-white" in html
    assert "state-pr-black" in html
    assert "quality-row" in html
    assert "formatAccuracy" in html
    assert "renderQualityMetrics" in html
    assert "shouldKeepPolling" in html
    assert "quality_at" in html
    assert "not ladder Elo" in html
    assert "white_accuracy" in html
    assert "play rating" in html


def test_show_eval_for_state_true_for_human_vs_agent():
    state = {"game_type": "human_vs_agent", "status": "in_progress"}
    assert show_eval_for_state(state) is True


@pytest.mark.parametrize("path", ["/human/", "/create"])
def test_create_shells_include_collapsible_inscribe(create_client, path):
    client, _ = create_client
    html = client.get(path).text
    assert "<details" in html
    assert "inscribe-panel" in html
