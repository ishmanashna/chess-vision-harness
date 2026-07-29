"""Tests for agent brief template."""

from __future__ import annotations

import os

from chess_harness.agent_brief import (
    public_base_url,
    render_agent_brief,
    render_agent_brief_avaa,
    render_agent_brief_human,
)


def test_public_base_url_default():
    os.environ.pop("CHESS_HARNESS_PUBLIC_URL", None)
    assert public_base_url() == "http://127.0.0.1:8765"


def test_public_base_url_env_override(monkeypatch):
    monkeypatch.setenv("CHESS_HARNESS_PUBLIC_URL", "https://chess.example.com/")
    assert public_base_url() == "https://chess.example.com"


def test_render_agent_brief_contains_play_loop():
    brief = render_agent_brief("http://127.0.0.1:8765", "game-1-2345", "secret-key-abc")
    assert "game-1-2345" in brief
    assert "Authorization: Bearer secret-key-abc" in brief
    assert "http://127.0.0.1:8765/api/v1/games/game-1-2345/board" in brief
    assert "http://127.0.0.1:8765/api/v1/games/game-1-2345/status" in brief
    assert "You are playing chess" in brief
    assert "image/png" in brief.lower()
    assert "Never use FEN" in brief
    assert "Play loop" in brief
    assert "/move/e2e4" in brief
    assert "No request body" in brief or "no JSON" in brief.lower()
    assert "--data-raw" not in brief
    assert "curl.exe" in brief
    assert "Optional status" in brief


def test_render_agent_brief_ave_still_says_rare_wait():
    brief = render_agent_brief("http://127.0.0.1:8765", "game-1-2345", "secret-key-abc")
    assert "rare" in brief.lower()


def test_render_agent_brief_avaa_contains_poll_loop():
    brief = render_agent_brief_avaa(
        "http://127.0.0.1:8765",
        "game-avaa-1",
        "key-white",
        "white",
        "Opponent Model",
    )
    assert "game-avaa-1" in brief
    assert "Authorization: Bearer key-white" in brief
    assert "You play: white" in brief
    assert "Opponent: Opponent Model" in brief
    assert "agent vs agent" in brief.lower()
    assert "http://127.0.0.1:8765/api/v1/games/game-avaa-1/status" in brief
    assert "http://127.0.0.1:8765/api/v1/games/game-avaa-1/board" in brief
    assert "your_turn" in brief
    assert "poll" in brief.lower() or "Poll" in brief
    assert "backoff" in brief.lower() or "sleep" in brief.lower()
    assert "403" not in brief
    assert "while waiting" in brief.lower() or "look at the position" in brief.lower()
    assert "rare" not in brief.lower()
    assert "Never use FEN" in brief
    assert "/move/e2e4" in brief


def test_render_agent_brief_human_contains_poll_loop():
    brief = render_agent_brief_human(
        "http://127.0.0.1:8765",
        "game-human-1",
        "key-agent",
        "black",
        "Alice",
    )
    assert "game-human-1" in brief
    assert "Authorization: Bearer key-agent" in brief
    assert "You play: black" in brief
    assert "Human opponent: Alice" in brief
    assert "agent vs human" in brief.lower()
    assert "unranked" in brief.lower()
    assert "http://127.0.0.1:8765/api/v1/games/game-human-1/status" in brief
    assert "your_turn" in brief
    assert "poll" in brief.lower() or "Poll" in brief
    assert "Never use FEN" in brief
    assert "/moves" in brief
    assert "memory" in brief.lower() or "recall" in brief.lower()
