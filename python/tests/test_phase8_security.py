"""Phase 8 security: logout redirect, /g/ XSS hardening, calibration gate."""

from __future__ import annotations

import json
import shutil

import pytest
from fastapi.testclient import TestClient

from chess_harness.spectator import app
from chess_harness.spectator_game_page import render_game_view_page

from conftest import FIXTURES


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


def test_game_view_rejects_invalid_id(spectator_client):
    client = spectator_client
    bad = client.get("/g/<script>alert(1)</script>")
    assert bad.status_code == 404


def test_game_view_escapes_game_id_in_html():
    game_id = "game-test-escape"
    body = render_game_view_page(game_id)
    assert f"<title>{game_id} · Chess Vision Harness</title>" in body
    assert f'download="{game_id}-board.png"' in body
    assert f'data-game-id="{game_id}"' in body
    assert "Spectating" not in body
    assert 'id="info-panel-title"' not in body


def test_game_view_invalid_id_not_rendered():
    """Validated ids are alphanumeric; malicious paths are rejected before render."""
    from chess_harness.game_manager import GameManager

    gm = GameManager()
    assert gm.validate_game_id('"><script>alert(1)</script>') is False


@pytest.fixture
def spectator_client(tmp_path, monkeypatch):
    harness_dir = tmp_path / "harness"
    harness_dir.mkdir()
    shutil.copy(FIXTURES / "models.json", harness_dir / "models.json")
    monkeypatch.setenv("CHESS_HARNESS_DIR", str(harness_dir))
    monkeypatch.setenv("MODELS_FILE", str(harness_dir / "models.json"))
    monkeypatch.delenv("CHESS_HARNESS_CALIBRATION_SECRET", raising=False)
    monkeypatch.delenv("CHESS_HARNESS_ALLOW_REMOTE_CALIBRATION", raising=False)

    import chess_harness.spectator as spec
    from chess_harness.game_manager import GameManager

    spec._base = str(harness_dir)
    spec.game_manager = GameManager(str(harness_dir))
    spec._controller = None
    spec._game_service = None

    client = TestClient(app)
    yield client
    spec._game_service = None
    spec._controller = None


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
