"""Tests for agent brief template."""

from __future__ import annotations

import os

from chess_harness.agent_brief import public_base_url, render_agent_brief


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
