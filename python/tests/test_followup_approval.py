"""Tests for approval-gated follow-up game creation (/api/v1/games/followup)."""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

import pytest
from fastapi.testclient import TestClient

from conftest import FIXTURES, LOW_OPPONENT

from chess_harness.game_manager import GameManager
from chess_harness.spectator import app

LOOPBACK = {"Host": "127.0.0.1:8765"}
PUBLIC = {"Host": "example.com"}


@pytest.fixture
def api_client(tmp_path, monkeypatch):
    harness_dir = tmp_path / "harness"
    harness_dir.mkdir()
    shutil.copy(FIXTURES / "models.json", harness_dir / "models.json")
    monkeypatch.setenv("CHESS_HARNESS_DIR", str(harness_dir))
    monkeypatch.setenv("MODELS_FILE", str(harness_dir / "models.json"))

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
    if hasattr(spec, "_get_controller"):
        try:
            spec._get_controller().opponent_mgr.release()
        except Exception:
            pass


def _register(client, model_id: str) -> str:
    resp = client.post("/api/v1/agents", json={"id": model_id})
    assert resp.status_code == 200
    return resp.json()["api_key"]


def _auth(key: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


def _fabricate_game(harness_dir, game_id: str, model_id: str, status: str) -> None:
    gm = GameManager(str(harness_dir))
    state: Dict[str, Any] = {
        "game_id": game_id,
        "model_name": model_id,
        "agent_color": "WHITE",
        "status": status,
        "result": "1-0" if status == "finished" else None,
        "moves": [],
    }
    gm.save_state(game_id, state)


def _request(client, key: str, game_id: str):
    return client.post(f"/api/v1/games/{game_id}/request-followup", headers=_auth(key))


def _approve(client, game_id: str, headers=LOOPBACK):
    return client.post(
        f"/api/v1/games/{game_id}/approve-followup", headers=headers
    )


def _followup(client, key: str, previous_game_id: str, model: str, **extra):
    body = {"previous_game_id": previous_game_id, "model": model, **extra}
    return client.post("/api/v1/games/followup", headers=_auth(key), json=body)


def _expire_approval(harness_dir, game_id: str) -> None:
    path = harness_dir / "followup_approvals.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["approvals"][game_id]["expires_at"] = (
        datetime.now(timezone.utc) - timedelta(seconds=10)
    ).isoformat()
    path.write_text(json.dumps(data), encoding="utf-8")


def test_followup_requires_finished_game_and_participant(api_client):
    client, harness_dir = api_client
    key = _register(client, "followup-a")
    other_key = _register(client, "followup-b")
    game_id = "game-prev-finished-check"
    _fabricate_game(harness_dir, game_id, "followup-a", "in_progress")

    missing = client.post(
        "/api/v1/games/game-does-not-exist/request-followup", headers=_auth(key)
    )
    assert missing.status_code == 404

    stranger = _request(client, other_key, game_id)
    assert stranger.status_code == 401

    in_progress = _request(client, key, game_id)
    assert in_progress.status_code == 409
    assert in_progress.json()["ok"] is False

    _fabricate_game(harness_dir, game_id, "followup-a", "finished")
    ok = _request(client, key, game_id)
    assert ok.status_code == 200
    assert ok.json()["state"] == "requested"


def test_followup_request_is_idempotent(api_client):
    client, harness_dir = api_client
    key = _register(client, "followup-idem")
    game_id = "game-prev-idem"
    _fabricate_game(harness_dir, game_id, "followup-idem", "finished")

    first = _request(client, key, game_id)
    second = _request(client, key, game_id)
    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["state"] == "requested"


def test_followup_without_approval_is_rejected(api_client):
    client, harness_dir = api_client
    key = _register(client, "followup-noapprove")
    game_id = "game-prev-noapprove"
    _fabricate_game(harness_dir, game_id, "followup-noapprove", "finished")

    _request(client, key, game_id)
    resp = _followup(
        client, key, game_id, "followup-noapprove",
        opponent=LOW_OPPONENT, agent_color="white",
    )
    assert resp.status_code == 409
    assert "not yet approved" in resp.json()["error"]


def test_followup_approve_then_create_success(api_client):
    client, harness_dir = api_client
    key = _register(client, "followup-ok")
    game_id = "game-prev-ok"
    _fabricate_game(harness_dir, game_id, "followup-ok", "finished")

    _request(client, key, game_id)
    approved = _approve(client, game_id)
    assert approved.status_code == 200
    data = approved.json()
    assert data["state"] == "approved"
    assert data["model_id"] == "followup-ok"
    assert data["expires_at"]

    resp = _followup(
        client, key, game_id, "followup-ok",
        opponent=LOW_OPPONENT, agent_color="white",
    )
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert payload["ok"] is True
    assert payload["previous_game_id"] == game_id
    new_id = payload["game_id"]
    assert new_id != game_id
    assert payload["board_url"] == f"/api/v1/games/{new_id}/board"
    assert "board_path" not in payload
    brief = payload["agent_brief"]
    assert f"Game ID: {new_id}" in brief
    assert f"{new_id}/board" in brief

    status = client.get(f"/api/v1/games/{new_id}/status", headers=_auth(key))
    assert status.status_code == 200
    assert status.json()["ok"] is True

    store = json.loads(
        (harness_dir / "followup_approvals.json").read_text(encoding="utf-8")
    )
    assert store["approvals"][game_id]["state"] == "used"


def test_followup_approval_is_single_use(api_client):
    client, harness_dir = api_client
    key = _register(client, "followup-single")
    game_id = "game-prev-single"
    _fabricate_game(harness_dir, game_id, "followup-single", "finished")

    _request(client, key, game_id)
    _approve(client, game_id)
    first = _followup(
        client, key, game_id, "followup-single",
        opponent=LOW_OPPONENT, agent_color="black",
    )
    assert first.status_code == 200
    second = _followup(
        client, key, game_id, "followup-single",
        opponent=LOW_OPPONENT, agent_color="white",
    )
    assert second.status_code == 409
    assert "already been used" in second.json()["error"]


def test_followup_expired_approval_rejected(api_client):
    client, harness_dir = api_client
    key = _register(client, "followup-expiry")
    game_id = "game-prev-expiry"
    _fabricate_game(harness_dir, game_id, "followup-expiry", "finished")

    _request(client, key, game_id)
    _approve(client, game_id)
    _expire_approval(harness_dir, game_id)

    resp = _followup(
        client, key, game_id, "followup-expiry",
        opponent=LOW_OPPONENT, agent_color="white",
    )
    assert resp.status_code == 409
    assert "expired" in resp.json()["error"]

    re_request = _request(client, key, game_id)
    assert re_request.status_code == 200
    assert re_request.json()["state"] == "requested"


def test_followup_model_mismatch_rejected(api_client):
    client, harness_dir = api_client
    key_a = _register(client, "followup-owner")
    key_b = _register(client, "followup-other")
    game_id = "game-prev-mismatch"
    _fabricate_game(harness_dir, game_id, "followup-owner", "finished")

    _request(client, key_a, game_id)
    _approve(client, game_id)

    wrong_body = _followup(
        client, key_b, game_id, "followup-owner",
        opponent=LOW_OPPONENT, agent_color="white",
    )
    assert wrong_body.status_code == 400
    assert "must match" in wrong_body.json()["error"]

    right_body = _followup(
        client, key_b, game_id, "followup-other",
        opponent=LOW_OPPONENT, agent_color="white",
    )
    assert right_body.status_code == 409
    assert "belongs to another model" in right_body.json()["error"]


def test_followup_approve_requires_request(api_client):
    client, harness_dir = api_client
    key = _register(client, "followup-noreq")
    game_id = "game-prev-noreq"
    _fabricate_game(harness_dir, game_id, "followup-noreq", "finished")

    resp = _approve(client, game_id)
    assert resp.status_code == 409
    assert "No follow-up request" in resp.json()["error"]

    unknown = _approve(client, "game-never-requested")
    assert unknown.status_code == 409


def test_followup_approve_requires_loopback_or_secret(api_client, monkeypatch):
    client, harness_dir = api_client
    key = _register(client, "followup-gate")
    game_id = "game-prev-gate"
    _fabricate_game(harness_dir, game_id, "followup-gate", "finished")
    _request(client, key, game_id)

    denied = _approve(client, game_id, headers=PUBLIC)
    assert denied.status_code == 403

    monkeypatch.setenv("CHESS_HARNESS_FOLLOWUP_APPROVAL_SECRET", "s3cret")
    secret_ok = _approve(
        client, game_id, headers={"Host": "example.com", "X-Chess-Harness-Followup-Secret": "s3cret"}
    )
    assert secret_ok.status_code == 200
    assert secret_ok.json()["state"] == "approved"


def test_followup_approval_ttl_env(api_client, monkeypatch):
    client, harness_dir = api_client
    monkeypatch.setenv("CHESS_HARNESS_FOLLOWUP_APPROVAL_TTL_SEC", "7200")
    key = _register(client, "followup-ttl")
    game_id = "game-prev-ttl"
    _fabricate_game(harness_dir, game_id, "followup-ttl", "finished")

    _request(client, key, game_id)
    approved = _approve(client, game_id).json()
    delta = (
        datetime.fromisoformat(approved["expires_at"])
        - datetime.fromisoformat(approved["approved_at"])
    )
    assert delta == timedelta(seconds=7200)


def test_existing_create_endpoint_stays_approval_free(api_client):
    client, _ = api_client
    key = _register(client, "followup-plain")
    resp = client.post(
        "/api/v1/games",
        headers=_auth(key),
        json={"opponent": LOW_OPPONENT, "agent_color": "white"},
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    assert "game_id" in resp.json()
