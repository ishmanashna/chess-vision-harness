"""Watch/play shell HTML injection (Phase 0)."""

from __future__ import annotations

from chess_harness.public_site_shell import (
    inject_shell_entity_id,
    watch_shell_response,
)


def test_watch_shell_injects_attempt_id_for_puzzle():
    resp = watch_shell_response("p", "pz-test123")
    body = resp.body.decode("utf-8")
    assert 'data-attempt-id="pz-test123"' in body


def test_watch_shell_injects_attempt_id_for_identify():
    resp = watch_shell_response("i", "id-attempt-456")
    body = resp.body.decode("utf-8")
    assert 'data-attempt-id="id-attempt-456"' in body


def test_watch_shell_injects_game_id_for_game_watch():
    resp = watch_shell_response("g", "game-abc")
    body = resp.body.decode("utf-8")
    assert 'data-game-id="game-abc"' in body


def test_inject_shell_entity_id_escapes_quotes():
    html = "<body class=\"x\"></body>"
    out = inject_shell_entity_id(html, "p", 'pz-"bad"')
    assert 'data-attempt-id="pz-&quot;bad&quot;"' in out
