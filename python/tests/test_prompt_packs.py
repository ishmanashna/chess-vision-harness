"""Tests for prompt pack registry and tagged game creation (Phase 1)."""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from conftest import FIXTURES

from chess_harness import commands
from chess_harness.game_manager import GameManager
from chess_harness.paths import project_root
from chess_harness.prompt_packs import assert_creatable, load_pack
from chess_harness.spectator import app


def _pack_body_hash(pack_id: str) -> str:
    body = (project_root() / "config" / "prompt_packs" / f"{pack_id}.txt").read_text(
        encoding="utf-8"
    )
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _harness_setup(tmp_path, monkeypatch) -> Path:
    harness_dir = tmp_path / "harness"
    harness_dir.mkdir()
    shutil.copy(FIXTURES / "models.json", harness_dir / "models.json")
    monkeypatch.setenv("CHESS_HARNESS_DIR", str(harness_dir))
    monkeypatch.setenv("MODELS_FILE", str(harness_dir / "models.json"))
    return harness_dir


def test_load_pack_b_hash_matches_file():
    pack = load_pack("b")
    assert pack.body_hash == _pack_body_hash("b")
    assert pack.kind == "overlay"


def test_cmd_new_prompt_pack_b_stores_state(tmp_path, monkeypatch):
    harness_dir = _harness_setup(tmp_path, monkeypatch)
    game_id = "prompt-pack-b-test"
    result = commands.cmd_new(
        game_id,
        "white",
        None,
        model_name="composer-2.5",
        force=True,
        opponent="random",
        prompt_pack="b",
    )
    assert result["ok"] is True
    state = GameManager(str(harness_dir)).load_state(game_id)
    assert state is not None
    assert state["prompt_pack"] == "b"
    assert state["prompt_pack_hash"] == _pack_body_hash("b")
    assert state["prompt_pack_kind"] == "overlay"


def test_cmd_new_prompt_pack_a_works(tmp_path, monkeypatch):
    harness_dir = _harness_setup(tmp_path, monkeypatch)
    game_id = "prompt-pack-a-test"
    result = commands.cmd_new(
        game_id,
        "white",
        None,
        model_name="composer-2.5",
        force=True,
        opponent="random",
        prompt_pack="a",
    )
    assert result["ok"] is True
    state = GameManager(str(harness_dir)).load_state(game_id)
    assert state["prompt_pack"] == "a"
    assert state["prompt_pack_kind"] == "overlay"


def test_cmd_new_unknown_pack_fails_no_game(tmp_path, monkeypatch):
    harness_dir = _harness_setup(tmp_path, monkeypatch)
    game_id = "prompt-pack-nope-test"
    result = commands.cmd_new(
        game_id,
        "white",
        None,
        model_name="composer-2.5",
        force=True,
        opponent="random",
        prompt_pack="nope",
    )
    assert result["ok"] is False
    assert "Unknown prompt pack" in result["error"]
    assert GameManager(str(harness_dir)).load_state(game_id) is None


def test_cmd_new_committee_pack_stores_state(tmp_path, monkeypatch):
    harness_dir = _harness_setup(tmp_path, monkeypatch)
    game_id = "prompt-pack-e-test"
    result = commands.cmd_new(
        game_id,
        "white",
        None,
        model_name="composer-2.5",
        force=True,
        opponent="random",
        prompt_pack="e",
    )
    assert result["ok"] is True
    state = GameManager(str(harness_dir)).load_state(game_id)
    assert state is not None
    assert state["prompt_pack"] == "e"
    assert state["prompt_pack_hash"] == _pack_body_hash("e")
    assert state["prompt_pack_kind"] == "committee"


def test_cmd_new_untagged_has_no_prompt_pack(tmp_path, monkeypatch):
    harness_dir = _harness_setup(tmp_path, monkeypatch)
    game_id = "prompt-pack-untagged-test"
    result = commands.cmd_new(
        game_id,
        "white",
        None,
        model_name="composer-2.5",
        force=True,
        opponent="random",
    )
    assert result["ok"] is True
    state = GameManager(str(harness_dir)).load_state(game_id)
    assert "prompt_pack" not in state
    assert "prompt_pack_hash" not in state
    assert "prompt_pack_kind" not in state


def test_assert_creatable_accepts_committee():
    pack = assert_creatable("e")
    assert pack.kind == "committee"
    assert pack.seats == 3


@pytest.fixture
def games_api_client(tmp_path, monkeypatch):
    harness_dir = _harness_setup(tmp_path, monkeypatch)

    import chess_harness.api_limits as api_limits
    import chess_harness.spectator as spec

    api_limits.get_limit_enforcer().reset_counters()
    spec._base = str(harness_dir)
    spec.game_manager = GameManager(str(harness_dir))
    spec._controller = None
    spec._game_service = None

    client = TestClient(app)
    yield client, harness_dir
    api_limits.get_limit_enforcer().reset_counters()
    spec._game_service = None
    spec._controller = None
    if spec._engine is not None:
        spec._engine.quit()
        spec._engine = None
    if hasattr(spec._get_controller(), "opponent_mgr"):
        spec._get_controller().opponent_mgr.release()


def _register(client: TestClient, agent_id: str) -> str:
    resp = client.post("/api/v1/agents", json={"id": agent_id, "name": agent_id})
    assert resp.status_code == 200
    return resp.json()["api_key"]


def _auth(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}"}


@pytest.mark.parametrize("pack_id", ["a", "b"])
def test_http_create_game_loopback_prompt_pack(games_api_client, pack_id):
    client, harness_dir = games_api_client
    api_key = _register(client, "composer-2.5")
    resp = client.post(
        "/api/v1/games",
        headers={**_auth(api_key), "Host": "127.0.0.1"},
        json={"prompt_pack": pack_id, "opponent": "random"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    game_id = data["game_id"]
    state = GameManager(str(harness_dir)).load_state(game_id)
    assert state["prompt_pack"] == pack_id
    assert state["prompt_pack_hash"] == _pack_body_hash(pack_id)


def test_http_create_game_non_loopback_prompt_pack_forbidden(games_api_client):
    client, _harness_dir = games_api_client
    api_key = _register(client, "composer-2.5")
    resp = client.post(
        "/api/v1/games",
        headers={**_auth(api_key), "Host": "example.com"},
        json={"prompt_pack": "a", "opponent": "random"},
    )
    assert resp.status_code == 403
    assert "loopback" in resp.json()["error"].lower()
