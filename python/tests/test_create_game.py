"""Tests for Create Game spectator page."""

from __future__ import annotations

import shutil

import pytest
from fastapi.testclient import TestClient

from conftest import FIXTURES

from chess_harness.game_manager import GameManager
from chess_harness.spectator import app


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


def test_create_game_get_renders_model_only_form(create_client):
    client, _ = create_client
    resp = client.get("/create")
    assert resp.status_code == 200
    assert "Create Game" in resp.text
    assert 'name="model_id"' in resp.text
    assert 'name="api_key"' not in resp.text
    assert 'name="opponent"' not in resp.text
    assert 'name="agent_color"' not in resp.text


def test_create_game_post_happy_path(create_client):
    client, harness_dir = create_client

    resp = client.post("/create", data={"model_id": "composer-2.5"})
    assert resp.status_code == 200
    assert "Game created" in resp.text
    assert "Copy prompt" in resp.text
    assert "Authorization: Bearer" in resp.text
    assert "game-" in resp.text

    keys_file = harness_dir / "api_keys.json"
    assert keys_file.exists()
    assert "composer-2.5" in keys_file.read_text(encoding="utf-8")

    games = client.get("/api/games").json()
    assert any(g["status"] == "in_progress" for g in games)


def test_create_game_post_requires_model(create_client):
    client, _ = create_client
    resp = client.post("/create", data={"model_id": ""})
    assert resp.status_code == 200
    assert "Select a model" in resp.text
