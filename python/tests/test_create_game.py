"""Tests for Create Game static shell and API-backed create flow."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from conftest import FIXTURES

from chess_harness.game_manager import GameManager
from chess_harness.spectator import app

REPO_ROOT = Path(__file__).resolve().parents[2]
PUBLIC_SITE = REPO_ROOT / "public-site"

@pytest.fixture
def create_client(tmp_path, monkeypatch):
    harness_dir = tmp_path / "harness"
    harness_dir.mkdir()
    shutil.copy(FIXTURES / "models.json", harness_dir / "models.json")
    monkeypatch.setenv("CHESS_HARNESS_DIR", str(harness_dir))
    monkeypatch.setenv("MODELS_FILE", str(harness_dir / "models.json"))

    import chess_harness.spectator as spec

    spec._base = str(harness_dir)
    spec.game_manager = GameManager(str(harness_dir))
    spec._controller = None
    spec._game_service = None

    client = TestClient(app)
    yield client, harness_dir
    spec._game_service = None
    spec._controller = None
    if spec._engine is not None:
        spec._engine.quit()
        spec._engine = None
    if hasattr(spec, "_get_controller"):
        try:
            spec._get_controller().opponent_mgr.release()
        except Exception:
            pass


def test_home_serves_public_shell(create_client):
    client, _ = create_client
    resp = client.get("/")
    assert resp.status_code == 200
    assert "What this is" in resp.text
    assert 'data-leaderboard' in resp.text
    assert "site-header" in resp.text


def test_legacy_tab_active_redirects_to_spectator(create_client):
    client, _ = create_client
    resp = client.get("/?tab=active", follow_redirects=False)
    assert resp.status_code == 307
    assert resp.headers["location"] == "/spectator/"


def test_legacy_tab_done_redirects_to_spectator_completed(create_client):
    client, _ = create_client
    resp = client.get("/?tab=done", follow_redirects=False)
    assert resp.status_code == 307
    assert resp.headers["location"] == "/spectator/?tab=completed"


def test_leaderboard_and_contact_serve_static(create_client):
    client, _ = create_client
    for path in ("/leaderboard/", "/contact/"):
        resp = client.get(path)
        assert resp.status_code == 200
        assert "site-header" in resp.text


def test_public_data_and_favicons_served(create_client):
    client, _ = create_client
    assert client.get("/data/leaderboard.json").status_code == 200
    assert client.get("/favicon.ico").status_code == 200
    assert client.get("/favicon.svg").status_code == 200
    assert client.get("/favicon-alert.svg").status_code == 200


def test_create_game_get_renders_static_shell(create_client):
    client, _ = create_client
    resp = client.get("/create")
    assert resp.status_code == 200
    assert "Create Game" in resp.text
    assert 'data-create-page' in resp.text
    assert "Agent vs Human" not in resp.text
    assert 'data-mode="human"' not in resp.text
    assert 'name="api_key"' not in resp.text
    assert 'name="opponent"' not in resp.text
    assert 'name="agent_color"' not in resp.text
    assert 'data-pairing="find"' in resp.text
    assert 'data-pairing="direct"' in resp.text
    assert 'data-avaa-pairing-tabs hidden' in resp.text
    assert 'id="white-model-select"' in resp.text
    assert 'id="black-model-select"' in resp.text
    assert "create-result.js" in resp.text
    assert "showDualBriefResult" in (client.get("/js/create-result.js").text)


def test_create_pairing_tabs_gated_to_avaa(create_client):
    """Find match / Direct chrome is AvA-only; CSS must honor [hidden]."""
    client, _ = create_client
    html = client.get("/create").text
    assert 'data-avaa-pairing-tabs hidden' in html
    assert 'data-pairing="find"' in html
    assert 'data-pairing="direct"' in html
    assert "Rated game vs engine" in html

    css = (PUBLIC_SITE / "css" / "site.css").read_text(encoding="utf-8")
    assert "[hidden]" in css
    assert "display: none !important" in css

    js = (PUBLIC_SITE / "js" / "create.js").read_text(encoding="utf-8")
    assert "pairingTabs.hidden = !isAvaa" in js
    assert 'mode === "avaa"' in js

def test_create_human_mode_redirects(create_client):
    client, _ = create_client
    for path in ("/create?mode=human", "/create/?mode=human", "/create?mode=avh"):
        resp = client.get(path, follow_redirects=False)
        assert resp.status_code == 301
        assert resp.headers["location"] == "/human/"


def test_human_hub_serves_static(create_client):
    client, _ = create_client
    resp = client.get("/human/")
    assert resp.status_code == 200
    assert "Playground" in resp.text
    assert 'data-human-page' in resp.text
    assert "Your games" not in resp.text
    assert "Resume saved games in Spectator" in resp.text


def test_create_game_via_api_v1(create_client):
    client, harness_dir = create_client

    reg = client.post("/api/v1/agents", json={"id": "composer-2.5"})
    assert reg.status_code == 200
    api_key = reg.json()["api_key"]

    create = client.post(
        "/api/v1/games",
        headers={"Authorization": f"Bearer {api_key}"},
        json={},
    )
    assert create.status_code == 200
    assert create.json()["ok"] is True
    assert "game_id" in create.json()

    keys_file = harness_dir / "api_keys.json"
    assert keys_file.exists()
    assert "composer-2.5" in keys_file.read_text(encoding="utf-8")

    games = client.get("/api/games").json()["games"]
    assert any(g["status"] == "in_progress" for g in games)


def test_legacy_post_create_removed(create_client):
    client, _ = create_client
    resp = client.post("/create", data={"model_id": "composer-2.5"})
    assert resp.status_code == 405
