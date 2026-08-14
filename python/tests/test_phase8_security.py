"""Phase 8 security: logout redirect, /g/ XSS hardening, calibration gate."""

from __future__ import annotations

import pytest

from chess_harness.spectator_game_page import load_game_view_shell


@pytest.fixture(autouse=True)
def clear_calibration_env(monkeypatch):
    monkeypatch.delenv("CHESS_HARNESS_CALIBRATION_SECRET", raising=False)
    monkeypatch.delenv("CHESS_HARNESS_ALLOW_REMOTE_CALIBRATION", raising=False)


def safe_logout_path(next_path: str | None) -> str:
    """Mirror public-site/functions/auth/_redirect.js safeLogoutPath."""
    if not isinstance(next_path, str) or not next_path:
        return "/"
    if not next_path.startswith("/") or next_path.startswith("//"):
        return "/"
    if "\\" in next_path or "\0" in next_path:
        return "/"
    return next_path


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("/spectator/", "/spectator/"),
        ("/", "/"),
        ("//evil.com", "/"),
        ("https://evil.com", "/"),
        ("/\\evil", "/"),
        (None, "/"),
        ("", "/"),
    ],
)
def test_safe_logout_path(raw, expected):
    assert safe_logout_path(raw) == expected


def test_game_view_static_shell_has_no_embedded_id(spectator_client):
    client = spectator_client
    # Path segment must not contain '/' (would become a sub-route).
    bad = client.get("/g/%22%3E%3Cscript%3Ealert(1)")
    assert bad.status_code == 200
    assert "<script>alert(1)" not in bad.text


def test_game_view_shell_is_static_html():
    body = load_game_view_shell()
    assert "<title>Game · Chess Vision Harness</title>" in body
    assert "data-board-download" in body
    assert "Spectating" not in body
    assert 'id="info-panel-title"' not in body


def test_game_view_invalid_id_not_rendered():
    """Validated ids are alphanumeric; malicious paths are rejected before render."""
    from chess_harness.game_manager import GameManager

    gm = GameManager()
    assert gm.validate_game_id('"><script>alert(1)</script>') is False


def test_calibration_post_denied_without_secret(spectator_client):
    client = spectator_client
    denied = client.post("/api/calibration/stop-all")
    assert denied.status_code == 403


def test_calibration_post_allowed_on_loopback_host(spectator_client):
    client = spectator_client
    ok = client.post(
        "/api/calibration/stop-all",
        headers={"Host": "127.0.0.1:8765"},
    )
    assert ok.status_code == 200


def test_calibration_post_allowed_with_secret(spectator_client, monkeypatch):
    monkeypatch.setenv("CHESS_HARNESS_CALIBRATION_SECRET", "test-secret")
    client = spectator_client
    ok = client.post(
        "/api/calibration/stop-all",
        headers={"CHESS_HARNESS_CALIBRATION_SECRET": "test-secret"},
    )
    assert ok.status_code == 200


def test_calibration_post_allowed_with_remote_override(spectator_client, monkeypatch):
    monkeypatch.setenv("CHESS_HARNESS_ALLOW_REMOTE_CALIBRATION", "1")
    client = spectator_client
    ok = client.post("/api/calibration/stop-all")
    assert ok.status_code == 200
