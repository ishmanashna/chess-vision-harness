"""Integration tests for agent-vs-agent play (Phases 0–1)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from harness_client import configure_spectator_harness, make_test_client, teardown_spectator_harness
from leak_guards import assert_game_api_no_leaks

from chess_harness.game_manager import GameManager
from chess_harness.game_types import GAME_TYPE_AGENT_VS_AGENT


@pytest.fixture
def avaa_client(tmp_path, monkeypatch):
    harness_dir = configure_spectator_harness(tmp_path / "harness", monkeypatch)
    client = make_test_client()
    yield client, harness_dir
    teardown_spectator_harness()


def _auth(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}"}


def _register_pair(client: TestClient) -> tuple[str, str, str, str]:
    white = client.post("/api/v1/agents", json={"id": "avaa-white", "name": "White Agent"})
    black = client.post("/api/v1/agents", json={"id": "avaa-black", "name": "Black Agent"})
    assert white.status_code == 200
    assert black.status_code == 200
    white_key = white.json()["api_key"]
    black_key = black.json()["api_key"]
    return white_key, black_key, "avaa-white", "avaa-black"


def _create_avaa(
    client: TestClient,
    white_key: str,
    white_id: str,
    black_id: str,
) -> str:
    create = client.post(
        "/api/v1/games/agent-vs-agent",
        headers=_auth(white_key),
        json={"white_model_id": white_id, "black_model_id": black_id},
    )
    assert create.status_code == 200, create.text
    data = create.json()
    assert data["ok"] is True
    assert data.get("agent_color") == "WHITE"
    assert data.get("your_turn") is True
    assert_game_api_no_leaks(data)
    return data["game_id"]


def test_avaa_new_game_no_engine(avaa_client):
    client, harness_dir = avaa_client
    white_key, _, white_id, black_id = _register_pair(client)
    game_id = _create_avaa(client, white_key, white_id, black_id)

    state = GameManager(str(harness_dir)).load_state(game_id)
    assert state is not None
    assert state["game_type"] == GAME_TYPE_AGENT_VS_AGENT
    assert state.get("opponent_id") is None
    assert state.get("opponent_uci_config") is None
    assert state["white_model_id"] == white_id
    assert state["black_model_id"] == black_id

    game_dir = harness_dir / "games" / game_id
    assert (game_dir / "board.png").exists()
    assert (game_dir / "board_white.png").exists()
    assert (game_dir / "board_black.png").exists()
    # Role boards alias the same white-bottom content as spectator board.png
    canonical = (game_dir / "board.png").read_bytes()
    assert (game_dir / "board_white.png").read_bytes() == canonical
    assert (game_dir / "board_black.png").read_bytes() == canonical


def test_avaa_turn_and_board_access(avaa_client):
    client, _ = avaa_client
    white_key, black_key, white_id, black_id = _register_pair(client)
    game_id = _create_avaa(client, white_key, white_id, black_id)

    white_board = client.get(f"/api/v1/games/{game_id}/board", headers=_auth(white_key))
    assert white_board.status_code == 200
    assert white_board.content[:8] == b"\x89PNG\r\n\x1a\n"

    black_board_wait = client.get(f"/api/v1/games/{game_id}/board", headers=_auth(black_key))
    assert black_board_wait.status_code == 200
    assert black_board_wait.content[:8] == b"\x89PNG\r\n\x1a\n"
    assert black_board_wait.content == white_board.content

    move = client.post(
        f"/api/v1/games/{game_id}/move/e2e4",
        headers=_auth(white_key),
    )
    assert move.status_code == 200
    move_data = move.json()
    assert move_data["your_turn"] is False
    assert_game_api_no_leaks(move_data)

    white_status = client.get(f"/api/v1/games/{game_id}/status", headers=_auth(white_key))
    assert white_status.status_code == 200
    assert white_status.json()["your_turn"] is False

    black_status = client.get(f"/api/v1/games/{game_id}/status", headers=_auth(black_key))
    assert black_status.status_code == 200
    assert black_status.json()["your_turn"] is True

    white_board_after = client.get(f"/api/v1/games/{game_id}/board", headers=_auth(white_key))
    assert white_board_after.status_code == 200

    black_board = client.get(f"/api/v1/games/{game_id}/board", headers=_auth(black_key))
    assert black_board.status_code == 200


def test_avaa_off_turn_move_400(avaa_client):
    client, _ = avaa_client
    white_key, black_key, white_id, black_id = _register_pair(client)
    game_id = _create_avaa(client, white_key, white_id, black_id)

    off_turn = client.post(
        f"/api/v1/games/{game_id}/move/e7e5",
        headers=_auth(black_key),
    )
    assert off_turn.status_code == 400
    assert off_turn.json()["error"] == "Not your turn"


def test_avaa_few_plies_no_engine(avaa_client):
    client, harness_dir = avaa_client
    white_key, black_key, white_id, black_id = _register_pair(client)
    game_id = _create_avaa(client, white_key, white_id, black_id)

    sequence = [
        (white_key, "e2e4"),
        (black_key, "e7e5"),
        (white_key, "g1f3"),
        (black_key, "b8c6"),
    ]
    for key, uci in sequence:
        resp = client.post(
            f"/api/v1/games/{game_id}/move/{uci}",
            headers=_auth(key),
        )
        assert resp.status_code == 200, resp.text
        assert_game_api_no_leaks(resp.json())

    state = GameManager(str(harness_dir)).load_state(game_id)
    assert state is not None
    assert len(state["moves"]) == 4
    assert state["moves"] == ["e2e4", "e7e5", "g1f3", "b8c6"]
    assert state["status"] == "in_progress"


def test_avaa_participant_auth(avaa_client):
    client, harness_dir = avaa_client
    white_key, black_key, white_id, black_id = _register_pair(client)
    from chess_harness.api_keys import ApiKeyStore

    outsider_key = ApiKeyStore(path=harness_dir / "api_keys.json").create("composer-2.5")
    game_id = _create_avaa(client, white_key, white_id, black_id)

    denied = client.get(f"/api/v1/games/{game_id}/status", headers=_auth(outsider_key))
    assert denied.status_code == 401

    black_create = client.post(
        "/api/v1/games/agent-vs-agent",
        headers=_auth(black_key),
        json={"white_model_id": white_id, "black_model_id": black_id},
    )
    assert black_create.status_code == 200
    assert black_create.json().get("agent_color") == "BLACK"
    assert black_create.json().get("your_turn") is False


def test_avaa_refresh_board_image(avaa_client):
    """AvA refresh must call render_avaa_boards (no KeyError on agent_color)."""
    client, harness_dir = avaa_client
    white_key, _, white_id, black_id = _register_pair(client)
    game_id = _create_avaa(client, white_key, white_id, black_id)
    game_dir = harness_dir / "games" / game_id
    for name in ("board.png", "board_white.png", "board_black.png"):
        (game_dir / name).unlink()

    from chess_harness.spectator import _get_controller

    assert _get_controller().refresh_board_image(game_id) is True
    canonical = (game_dir / "board.png").read_bytes()
    assert canonical[:8] == b"\x89PNG\r\n\x1a\n"
    assert (game_dir / "board_white.png").read_bytes() == canonical
    assert (game_dir / "board_black.png").read_bytes() == canonical


def test_avaa_same_model_requires_peer_key(avaa_client):
    client, _ = avaa_client
    reg = client.post("/api/v1/agents", json={"id": "same-model", "name": "Same"})
    assert reg.status_code == 200
    key = reg.json()["api_key"]
    create = client.post(
        "/api/v1/games/agent-vs-agent",
        headers=_auth(key),
        json={"white_model_id": "same-model", "black_model_id": "same-model"},
    )
    assert create.status_code == 400
    assert "peer_api_key" in create.json().get("error", "").lower()


def test_avaa_same_model_side_bound_keys(avaa_client):
    """Same inscribed model can play both sides with two distinct keys."""
    client, harness_dir = avaa_client
    white_reg = client.post("/api/v1/agents", json={"id": "mirror-agent", "name": "Mirror"})
    black_reg = client.post("/api/v1/agents", json={"id": "mirror-agent", "name": "Mirror"})
    assert white_reg.status_code == 200
    assert black_reg.status_code == 200
    white_key = white_reg.json()["api_key"]
    black_key = black_reg.json()["api_key"]
    assert white_key != black_key

    create = client.post(
        "/api/v1/games/agent-vs-agent",
        headers=_auth(white_key),
        json={
            "white_model_id": "mirror-agent",
            "black_model_id": "mirror-agent",
            "peer_api_key": black_key,
        },
    )
    assert create.status_code == 200, create.text
    data = create.json()
    assert data["ok"] is True
    assert data.get("agent_color") == "WHITE"
    assert data.get("your_turn") is True
    assert data["white"]["model_id"] == "mirror-agent"
    assert data["black"]["model_id"] == "mirror-agent"
    assert white_key in data["white"]["agent_brief"]
    assert black_key in data["black"]["agent_brief"]
    game_id = data["game_id"]

    state = GameManager(str(harness_dir)).load_state(game_id)
    assert state is not None
    assert state["white_model_id"] == "mirror-agent"
    assert state["black_model_id"] == "mirror-agent"
    assert state.get("white_key_fp")
    assert state.get("black_key_fp")
    assert state["white_key_fp"] != state["black_key_fp"]

    # Wrong key for the model cannot play either side.
    third = client.post("/api/v1/agents", json={"id": "mirror-agent", "name": "Mirror"})
    outsider = third.json()["api_key"]
    denied = client.get(f"/api/v1/games/{game_id}/status", headers=_auth(outsider))
    assert denied.status_code == 401

    white_status = client.get(f"/api/v1/games/{game_id}/status", headers=_auth(white_key))
    assert white_status.status_code == 200
    assert white_status.json()["your_turn"] is True
    assert white_status.json()["agent_color"] == "WHITE"

    black_status = client.get(f"/api/v1/games/{game_id}/status", headers=_auth(black_key))
    assert black_status.status_code == 200
    assert black_status.json()["your_turn"] is False
    assert black_status.json()["agent_color"] == "BLACK"

    off_turn = client.post(
        f"/api/v1/games/{game_id}/move/e7e5",
        headers=_auth(black_key),
    )
    assert off_turn.status_code == 400
    assert off_turn.json()["error"] == "Not your turn"

    sequence = [
        (white_key, "e2e4"),
        (black_key, "e7e5"),
        (white_key, "g1f3"),
        (black_key, "b8c6"),
    ]
    for key, uci in sequence:
        resp = client.post(
            f"/api/v1/games/{game_id}/move/{uci}",
            headers=_auth(key),
        )
        assert resp.status_code == 200, resp.text

    state = GameManager(str(harness_dir)).load_state(game_id)
    assert state["moves"] == ["e2e4", "e7e5", "g1f3", "b8c6"]
    assert state["white_joined"] is True
    assert state["black_joined"] is True


def test_avaa_same_model_rejects_identical_peer_key(avaa_client):
    client, _ = avaa_client
    reg = client.post("/api/v1/agents", json={"id": "one-key", "name": "One"})
    assert reg.status_code == 200
    key = reg.json()["api_key"]
    create = client.post(
        "/api/v1/games/agent-vs-agent",
        headers=_auth(key),
        json={
            "white_model_id": "one-key",
            "black_model_id": "one-key",
            "peer_api_key": key,
        },
    )
    assert create.status_code == 400
    assert "differ" in create.json().get("error", "").lower()


def test_avaa_direct_dual_briefs(avaa_client):
    client, harness_dir = avaa_client
    white_key, black_key, white_id, black_id = _register_pair(client)
    create = client.post(
        "/api/v1/games/agent-vs-agent",
        headers=_auth(white_key),
        json={
            "white_model_id": white_id,
            "black_model_id": black_id,
            "peer_api_key": black_key,
        },
    )
    assert create.status_code == 200, create.text
    data = create.json()
    assert data["ok"] is True
    assert "agent_brief" in data
    assert data["white"]["model_id"] == white_id
    assert data["black"]["model_id"] == black_id
    assert white_key in data["white"]["agent_brief"]
    assert black_key in data["black"]["agent_brief"]
    assert black_key not in data["agent_brief"]
    assert data["white"]["agent_brief"] != data["black"]["agent_brief"]

    # Single-key create (Find match / API client) still returns only caller brief.
    solo = client.post(
        "/api/v1/games/agent-vs-agent",
        headers=_auth(white_key),
        json={"white_model_id": white_id, "black_model_id": black_id},
    )
    assert solo.status_code == 200
    solo_data = solo.json()
    assert "white" not in solo_data
    assert "black" not in solo_data
    assert "agent_brief" in solo_data

    state = GameManager(str(harness_dir)).load_state(data["game_id"])
    assert state["white_joined"] is False
    assert state["black_joined"] is False


def test_avaa_joined_on_status_board_move_not_imagine(avaa_client):
    client, harness_dir = avaa_client
    white_key, black_key, white_id, black_id = _register_pair(client)
    game_id = _create_avaa(client, white_key, white_id, black_id)
    gm = GameManager(str(harness_dir))

    imag = client.post(
        f"/api/v1/games/{game_id}/imagine",
        headers=_auth(white_key),
        json={"moves": ["e2e4"]},
    )
    assert imag.status_code == 200
    state = gm.load_state(game_id)
    assert state["white_joined"] is False
    assert state["black_joined"] is False

    status = client.get(f"/api/v1/games/{game_id}/status", headers=_auth(white_key))
    assert status.status_code == 200
    body = status.json()
    assert body["white_joined"] is True
    assert body["black_joined"] is False
    state = gm.load_state(game_id)
    assert state["white_joined"] is True
    assert state["black_joined"] is False

    board = client.get(f"/api/v1/games/{game_id}/board", headers=_auth(black_key))
    assert board.status_code == 200
    state = gm.load_state(game_id)
    assert state["white_joined"] is True
    assert state["black_joined"] is True

    spec = client.get(f"/api/games/{game_id}/state")
    assert spec.status_code == 200
    assert spec.json()["white_joined"] is True
    assert spec.json()["black_joined"] is True


def test_avaa_idle_deferred_until_both_joined(avaa_client, monkeypatch):
    from chess_harness.limits import HarnessLimits
    from chess_harness.spectator import _get_controller

    client, harness_dir = avaa_client
    white_key, black_key, white_id, black_id = _register_pair(client)
    game_id = _create_avaa(client, white_key, white_id, black_id)

    monkeypatch.setattr(
        "chess_harness.board_controller.load_limits",
        lambda: HarnessLimits(idle_timeout_sec=0),
    )
    ctrl = _get_controller()
    ended = ctrl.check_idle_games()
    assert game_id not in ended
    state = GameManager(str(harness_dir)).load_state(game_id)
    assert state["status"] == "in_progress"

    client.get(f"/api/v1/games/{game_id}/status", headers=_auth(white_key))
    ended = ctrl.check_idle_games()
    assert game_id not in ended

    client.get(f"/api/v1/games/{game_id}/status", headers=_auth(black_key))
    ended = ctrl.check_idle_games()
    assert game_id in ended
    state = GameManager(str(harness_dir)).load_state(game_id)
    assert state["status"] == "finished"
    assert state["result"] == "*"


def test_avaa_board_text_is_role_authenticated(avaa_client):
    client, _ = avaa_client
    white_key, black_key, white_id, black_id = _register_pair(client)
    game_id = _create_avaa(client, white_key, white_id, black_id)

    white_text = client.get(f"/api/v1/games/{game_id}/board.txt", headers=_auth(white_key))
    black_text = client.get(f"/api/v1/games/{game_id}/board.txt", headers=_auth(black_key))
    assert white_text.status_code == 200
    assert black_text.status_code == 200
    assert white_text.text == black_text.text
    assert "8 r n b q k b n r" in white_text.text

    client.post(f"/api/v1/games/{game_id}/move/e2e4", headers=_auth(white_key))
    updated = client.get(f"/api/v1/games/{game_id}/board.txt", headers=_auth(black_key))
    assert updated.status_code == 200
    assert "4 . . . . P . . ." in updated.text

    outsider = client.post("/api/v1/agents", json={"id": "avaa-text-outsider"}).json()["api_key"]
    denied = client.get(f"/api/v1/games/{game_id}/board.txt", headers=_auth(outsider))
    assert denied.status_code == 401
