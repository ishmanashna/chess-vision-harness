"""Tests for parent orchestration: approval lifecycle + scoped child credentials."""

from __future__ import annotations

import shutil
from typing import Any, Dict

import pytest
from fastapi.testclient import TestClient

from conftest import FIXTURES, LOW_OPPONENT

from chess_harness.child_credentials import ChildCredentialStore
from chess_harness.game_manager import GameManager
from chess_harness.orchestrations import OrchestrationError, OrchestrationStore
from chess_harness.spectator import app

LOOPBACK = {"Host": "127.0.0.1:8765"}


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


def _register(client, model_id: str) -> str:
    resp = client.post("/api/v1/agents", json={"id": model_id})
    assert resp.status_code == 200
    return resp.json()["api_key"]


def _auth(key: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


def _create(
    client,
    key: str,
    mode: str,
    white: Dict[str, Any],
    black: Dict[str, Any],
    **extra,
):
    body = {"mode": mode, "white": white, "black": black, **extra}
    return client.post("/api/v1/orchestrations", headers=_auth(key), json=body)


def _approve(client, orchestration_id: str, headers):
    return client.post(f"/api/v1/orchestrations/{orchestration_id}/approve", headers=headers)


def _launch(client, orchestration_id: str, key: str):
    return client.post(f"/api/v1/orchestrations/{orchestration_id}/launch", headers=_auth(key))


def _child_vs_engine_body(child_model: str) -> Dict[str, Any]:
    return {
        "mode": "child_vs_engine",
        "white": {"kind": "model", "role": "child", "model_id": child_model},
        "black": {"kind": "engine"},
        "engine_opponent": LOW_OPPONENT,
    }


# --- Store unit tests -------------------------------------------------------


def test_child_credential_mint_verify(tmp_path):
    store = ChildCredentialStore(tmp_path / "child_credentials.json")
    issued = store.mint("game-abc", "WHITE", "orch-child")
    assert issued["key"]
    assert issued["credential_id"].startswith("cred-")
    assert issued["game_id"] == "game-abc"
    assert issued["side"] == "WHITE"
    assert "pgn" in issued["scopes"]

    verified = store.verify(issued["key"])
    assert verified is not None
    assert verified["model_id"] == "orch-child"
    assert verified["credential_id"] == issued["credential_id"]

    assert store.verify("wrong-key") is None


def test_child_credential_revoked_at_game_end(tmp_path):
    store = ChildCredentialStore(tmp_path / "child_credentials.json")
    issued = store.mint("game-abc", "BLACK", "model-b")
    assert store.revoke_game("game-abc") == 1
    assert store.verify(issued["key"]) is None


def test_orchestration_lifecycle(tmp_path):
    store = OrchestrationStore(tmp_path / "orchestrations.json")
    record = store.create(
        "orch-parent",
        "child_vs_engine",
        {"kind": "model", "model_id": "model-c", "role": "child"},
        {"kind": "engine"},
        engine_opponent=LOW_OPPONENT,
    )
    assert record["approval_state"] == "draft"
    with pytest.raises(OrchestrationError):
        store.launch(record["orchestration_id"], "game-1", "agent_vs_engine")
    store.approve(record["orchestration_id"])
    launched = store.launch(record["orchestration_id"], "game-1", "agent_vs_engine")
    assert launched["approval_state"] == "launched"
    assert launched["game_id"] == "game-1"
    assert launched["participants"]["white"]["status"] == "issued"
    assert launched["result"] is None


def test_orchestration_bad_modes(tmp_path):
    store = OrchestrationStore(tmp_path / "orchestrations.json")
    with pytest.raises(OrchestrationError):
        store.create("parent", "bogus", {"kind": "model", "role": "parent"}, {"kind": "engine"})
    with pytest.raises(OrchestrationError):
        store.create(
            "parent",
            "parent_vs_child",
            {"kind": "model", "role": "parent"},
            {"kind": "model", "role": "parent"},
        )
    with pytest.raises(OrchestrationError):
        store.create(
            "parent",
            "child_vs_engine",
            {"kind": "model", "role": "child"},
            {"kind": "engine"},
        )


# ---------------------------------------------------------------------- API tests ----


def test_create_orchestration_draft(api_client):
    client, harness_dir = api_client
    key = _register(client, "orch-parent")
    _register(client, "orch-child")

    resp = _create(client, key, **_child_vs_engine_body("orch-child"))
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["approval_state"] == "draft"

    games_dir = harness_dir / "games"
    assert not games_dir.exists() or not list(games_dir.iterdir())


def test_create_orchestration_rejects_unknown_model(api_client):
    client, _ = api_client
    parent_key = _register(client, "orch-parent2")
    resp = _create(client, parent_key, **_child_vs_engine_body("ghost-model"))
    assert resp.status_code == 400
    assert "not inscribed" in resp.json()["error"]


def test_launch_requires_approval(api_client):
    client, _ = api_client
    key = _register(client, "orch-parent3")
    _register(client, "orch-child3")
    created = _create(client, key, **_child_vs_engine_body("orch-child3")).json()
    orch_id = created["orchestration_id"]

    resp = _launch(client, orch_id, key)
    assert resp.status_code == 409
    assert "approved" in resp.json()["error"]


def test_approve_requires_parent_or_operator(api_client, monkeypatch):
    client, _ = api_client
    parent_key = _register(client, "orch-parent4")
    other_key = _register(client, "orch-other4")
    created = _create(client, parent_key, **_child_vs_engine_body("orch-other4")).json()
    orch_id = created["orchestration_id"]

    denied = _approve(client, orch_id, _auth(other_key))
    assert denied.status_code == 403

    from_loopback = _approve(client, orch_id, LOOPBACK)
    assert from_loopback.status_code == 200

    created2 = _create(client, parent_key, **_child_vs_engine_body("orch-other4")).json()
    monkeypatch.setenv("CHESS_HARNESS_ORCHESTRATION_SECRET", "s3cret")
    via_secret = _approve(
        client,
        created2["orchestration_id"],
        {"Host": "example.com", "X-Chess-Harness-Orchestration-Secret": "s3cret"},
    )
    assert via_secret.status_code == 200
    assert via_secret.json()["approval_state"] == "approved"


def test_child_vs_engine_full_flow(api_client):
    client, _ = api_client
    parent_key = _register(client, "orch-parent5")
    child_key = _register(client, "orch-child5")

    created = _create(client, parent_key, **_child_vs_engine_body("orch-child5")).json()
    orch_id = created["orchestration_id"]
    assert _approve(client, orch_id, _auth(parent_key)).status_code == 200

    launched = _launch(client, orch_id, parent_key)
    assert launched.status_code == 200, launched.text
    payload = launched.json()
    assert payload["ok"] is True
    assert payload["game_id"]
    game_id = payload["game_id"]
    child_side = payload["white"]
    assert child_side["role"] == "child"
    assert child_side["api_key"]
    assert "Game ID:" in child_side["agent_brief"]
    child_cred = child_side["api_key"]

    status = client.get(f"/api/v1/games/{game_id}/status", headers=_auth(child_cred))
    assert status.status_code == 200
    assert status.json()["ok"] is True
    assert status.json()["agent_color"] == "WHITE"

    board = client.get(f"/api/v1/games/{game_id}/board", headers=_auth(child_cred))
    assert board.status_code == 200
    assert board.headers["content-type"].startswith("image/png")

    board_txt = client.get(f"/api/v1/games/{game_id}/board.txt", headers=_auth(child_cred))
    assert board_txt.status_code == 200

    move = client.post(f"/api/v1/games/{game_id}/move/e2e4", headers=_auth(child_cred))
    assert move.status_code == 200, move.text

    forbidden_create = client.post("/api/v1/games", headers=_auth(child_cred), json={})
    assert forbidden_create.status_code == 403

    other_game = client.post(
        "/api/v1/games", headers=_auth(child_key), json={"opponent": LOW_OPPONENT}
    ).json()
    stranger = client.get(
        f"/api/v1/games/{other_game['game_id']}/status", headers=_auth(child_cred)
    )
    assert stranger.status_code == 403


def test_scoped_credential_rejects_out_of_scope_actions(api_client):
    client, _ = api_client
    parent_key = _register(client, "orch-parent6")
    _register(client, "orch-child6")
    created = _create(client, parent_key, **_child_vs_engine_body("orch-child6")).json()
    orch_id = created["orchestration_id"]
    _approve(client, orch_id, _auth(parent_key))
    launched = _launch(client, orch_id, parent_key).json()
    child_cred = launched["white"]["api_key"]
    game_id = launched["game_id"]

    imagine = client.post(
        f"/api/v1/games/{game_id}/imagine", headers=_auth(child_cred), json={"moves": ["e2e4"]}
    )
    assert imagine.status_code == 403

    orchestration_create = client.post(
        "/api/v1/orchestrations",
        headers=_auth(child_cred),
        json=_child_vs_engine_body("orch-child6"),
    )
    assert orchestration_create.status_code == 403


def test_parent_child_avaa_two_briefs(api_client):
    client, _ = api_client
    parent_key = _register(client, "orch-parent7")
    _register(client, "orch-child7")
    body = {
        "mode": "parent_vs_child",
        "white": {"kind": "model", "role": "parent", "model_id": "orch-parent7"},
        "black": {"kind": "model", "role": "child", "model_id": "orch-child7"},
    }
    created = _create(client, parent_key, **body).json()
    orch_id = created["orchestration_id"]
    _approve(client, orch_id, _auth(parent_key))
    launched = _launch(client, orch_id, parent_key)
    assert launched.status_code == 200, launched.text
    payload = launched.json()
    assert payload["game_type"] == "agent_vs_agent"
    assert "api_key" in payload["white"]
    assert "api_key" in payload["black"]
    game_id = payload["game_id"]

    parent_board = client.get(f"/api/v1/games/{game_id}/board", headers=_auth(parent_key))
    assert parent_board.status_code == 200
    child_board = client.get(
        f"/api/v1/games/{game_id}/board", headers=_auth(payload["black"]["api_key"])
    )
    assert child_board.status_code == 200


def test_launch_happy_home_envelope(api_client):
    client, _ = api_client
    parent_key = _register(client, "orch-parent8")
    _register(client, "orch-child8")
    created = _create(client, parent_key, **_child_vs_engine_body("orch-child8")).json()
    orch_id = created["orchestration_id"]
    _approve(client, orch_id, _auth(parent_key))
    launched = _launch(client, orch_id, parent_key)
    assert launched.status_code == 200, launched.text
    payload = launched.json()
    env = payload["white"]["envelope"]
    assert env["role"] == "child"
    assert env["side"] == "WHITE"
    assert env["game_id"] == payload["game_id"]
    assert env["api_base"]
    assert env["api_key"] == payload["white"]["api_key"]
    assert env["opponent"] == "Engine"
    assert "Game ID:" in env["brief"]


def test_child_vs_child_avaa_two_scoped_creds(api_client):
    client, _ = api_client
    parent_key = _register(client, "orch-parent10")
    _register(client, "orch-child-w")
    _register(client, "orch-child-b")
    body = {
        "mode": "child_vs_child",
        "white": {"kind": "model", "role": "child", "model_id": "orch-child-w"},
        "black": {"kind": "model", "role": "child", "model_id": "orch-child-b"},
    }
    created = _create(client, parent_key, **body).json()
    orch_id = created["orchestration_id"]
    assert _approve(client, orch_id, _auth(parent_key)).status_code == 200
    launched = _launch(client, orch_id, parent_key)
    assert launched.status_code == 200, launched.text
    payload = launched.json()
    assert payload["game_type"] == "agent_vs_agent"
    game_id = payload["game_id"]
    white_key = payload["white"]["api_key"]
    black_key = payload["black"]["api_key"]
    assert white_key != black_key
    assert payload["white"]["envelope"]["role"] == "child"
    assert payload["black"]["envelope"]["role"] == "child"
    assert "Game ID:" in payload["white"]["agent_brief"]
    assert "Game ID:" in payload["black"]["agent_brief"]

    for key in (white_key, black_key):
        assert client.get(f"/api/v1/games/{game_id}/status", headers=_auth(key)).status_code == 200

    first = client.post(f"/api/v1/games/{game_id}/move/e2e4", headers=_auth(white_key))
    assert first.status_code == 200, first.text
    off_turn = client.post(f"/api/v1/games/{game_id}/move/d2d4", headers=_auth(white_key))
    assert off_turn.status_code == 400
    second = client.post(f"/api/v1/games/{game_id}/move/e7e5", headers=_auth(black_key))
    assert second.status_code == 200, second.text

    # Credentials expire at game end: after a resignation, scoped calls are
    # rejected on every granted action (plan Phase 2: "expiries at game end").
    resigned = client.post(
        f"/api/v1/games/{game_id}/resign", headers=_auth(black_key)
    )
    assert resigned.status_code == 200, resigned.text
    for key in (white_key, black_key):
        assert client.get(
            f"/api/v1/games/{game_id}/status", headers=_auth(key)
        ).status_code == 403
        assert client.get(
            f"/api/v1/games/{game_id}/board", headers=_auth(key)
        ).status_code == 403
    assert client.post(
        f"/api/v1/games/{game_id}/move/e7e6", headers=_auth(white_key)
    ).status_code == 403


def test_status_reports_join_and_finish(api_client):
    client, _ = api_client
    parent_key = _register(client, "orch-parent9")
    _register(client, "orch-child9")
    body = {
        "mode": "parent_vs_child",
        "white": {"kind": "model", "role": "parent", "model_id": "orch-parent9"},
        "black": {"kind": "model", "role": "child", "model_id": "orch-child9"},
    }
    created = _create(client, parent_key, **body).json()
    orch_id = created["orchestration_id"]

    draft = client.get(f"/api/v1/orchestrations/{orch_id}", headers=_auth(parent_key))
    assert draft.status_code == 200
    assert draft.json()["approval_state"] == "draft"
    assert draft.json()["game"] is None
    assert draft.json()["participants"]["black"]["role"] == "child"
    assert draft.json()["participants"]["black"]["status"] == "pending"

    _approve(client, orch_id, _auth(parent_key))
    launched = _launch(client, orch_id, parent_key).json()
    game_id = launched["game_id"]
    child_cred = launched["black"]["api_key"]

    live = client.get(f"/api/v1/orchestrations/{orch_id}", headers=_auth(parent_key))
    assert live.status_code == 200
    body = live.json()
    assert body["approval_state"] == "launched"
    assert body["game"]["game_id"] == game_id
    assert body["game"]["move_count"] == 0
    assert body["game"]["turn"] == "WHITE"
    assert body["game"]["white_joined"] is False
    assert body["game"]["black_joined"] is False
    assert body["participants"]["black"]["brief_available"] is True
    assert "api_key" not in body["participants"]["black"]
    assert "envelope" not in body["participants"]["black"]
    assert "agent_brief" not in body["participants"]["black"]

    # Child fetches board -> black_joined flips in the parent status.
    client.get(f"/api/v1/games/{game_id}/board", headers=_auth(child_cred))
    joined = client.get(f"/api/v1/orchestrations/{orch_id}", headers=_auth(parent_key))
    j = joined.json()
    assert j["game"]["black_joined"] is True
    assert j["game"]["both_sides_joined"] is False

    # Parent (white) makes a move -> turn flips to black.
    moved = client.post(f"/api/v1/games/{game_id}/move/e2e4", headers=_auth(parent_key))
    assert moved.status_code == 200, moved.text
    after = client.get(f"/api/v1/orchestrations/{orch_id}", headers=_auth(parent_key))
    g = after.json()["game"]
    assert g["move_count"] == 1
    assert g["turn"] == "BLACK"
    assert g["white_joined"] is True
    assert g["both_sides_joined"] is True