"""Integration tests for /api/v1 public agent HTTP API."""

from __future__ import annotations

import json

from conftest import LOW_OPPONENT

from chess_harness.game_manager import GameManager
from harness_client import auth_headers
from leak_guards import assert_game_api_no_leaks


def test_api_v1_full_game_flow(api_client):
    client, harness_dir = api_client

    reg = client.post("/api/v1/agents", json={"id": "api-agent", "name": "API Agent"})
    assert reg.status_code == 200
    reg_data = reg.json()
    assert reg_data["ok"] is True
    assert reg_data["model_id"] == "api-agent"
    assert reg_data["name"] == "API Agent"
    assert "api_key" in reg_data
    assert_game_api_no_leaks(reg_data)
    api_key = reg_data["api_key"]

    keys_file = harness_dir / "api_keys.json"
    assert keys_file.exists()
    assert api_key not in keys_file.read_text(encoding="utf-8")

    listed = client.get("/api/v1/agents")
    assert listed.status_code == 200
    agents = listed.json()["agents"]
    assert any(a["id"] == "api-agent" for a in agents)
    assert "api_key" not in listed.text

    create = client.post(
        "/api/v1/games",
        headers=auth_headers(api_key),
        json={"opponent": LOW_OPPONENT, "agent_color": "white"},
    )
    assert create.status_code == 200
    game = create.json()
    assert game["ok"] is True
    game_id = game["game_id"]
    assert game.get("board_url") == f"/api/v1/games/{game_id}/board"
    assert "board_path" not in game
    assert_game_api_no_leaks(game)

    status = client.get(f"/api/v1/games/{game_id}/status", headers=auth_headers(api_key))
    assert status.status_code == 200
    status_data = status.json()
    assert status_data["ok"] is True
    assert_game_api_no_leaks(status_data)

    board = client.get(f"/api/v1/games/{game_id}/board", headers=auth_headers(api_key))
    assert board.status_code == 200
    assert board.headers["content-type"] == "image/png"
    assert board.content[:8] == b"\x89PNG\r\n\x1a\n"

    move = client.post(
        f"/api/v1/games/{game_id}/move/e2e4",
        headers=auth_headers(api_key),
    )
    assert move.status_code == 200
    move_data = move.json()
    assert move_data["ok"] is True
    assert_game_api_no_leaks(move_data)

    bad_move = client.post(
        f"/api/v1/games/{game_id}/move/a9a9",
        headers=auth_headers(api_key),
    )
    assert bad_move.status_code == 400
    assert bad_move.json()["ok"] is False
    assert_game_api_no_leaks(bad_move.json())

    pgn_blocked = client.get(f"/api/v1/games/{game_id}/pgn", headers=auth_headers(api_key))
    assert pgn_blocked.status_code == 400
    assert pgn_blocked.json()["ok"] is False

    resign = client.post(f"/api/v1/games/{game_id}/resign", headers=auth_headers(api_key))
    assert resign.status_code == 200
    resign_data = resign.json()
    assert resign_data["ok"] is True
    assert_game_api_no_leaks(resign_data)

    pgn = client.get(f"/api/v1/games/{game_id}/pgn", headers=auth_headers(api_key))
    assert pgn.status_code == 200
    pgn_data = pgn.json()
    assert pgn_data["ok"] is True
    assert "pgn" in pgn_data
    assert_game_api_no_leaks(pgn_data)

    leaderboard = client.get("/api/v1/leaderboard")
    assert leaderboard.status_code == 200
    assert leaderboard.json()["ok"] is True

    legacy = client.get("/api/games")
    assert legacy.status_code == 200
    payload = legacy.json()
    assert isinstance(payload, dict)
    assert isinstance(payload.get("games"), list)
    assert "total" in payload


def test_api_v1_auth_and_model_mismatch(api_client):
    client, _ = api_client

    reg_a = client.post("/api/v1/agents", json={"id": "agent-a", "name": "A"})
    reg_b = client.post("/api/v1/agents", json={"id": "agent-b", "name": "B"})
    key_a = reg_a.json()["api_key"]
    key_b = reg_b.json()["api_key"]

    create = client.post(
        "/api/v1/games",
        headers=auth_headers(key_a),
        json={"opponent": LOW_OPPONENT, "agent_color": "white"},
    )
    game_id = create.json()["game_id"]

    denied = client.get(f"/api/v1/games/{game_id}/status", headers=auth_headers(key_b))
    assert denied.status_code == 401

    missing = client.get(f"/api/v1/games/{game_id}/status")
    assert missing.status_code == 401

    unknown = client.get(
        "/api/v1/games/missing-game/status",
        headers=auth_headers(key_a),
    )
    assert unknown.status_code == 404


def test_api_v1_board_text_fallback_is_live_and_authenticated(api_client):
    client, _ = api_client
    reg = client.post("/api/v1/agents", json={"id": "text-agent"})
    api_key = reg.json()["api_key"]
    other = client.post("/api/v1/agents", json={"id": "other-text-agent"})
    other_key = other.json()["api_key"]

    create = client.post(
        "/api/v1/games",
        headers=auth_headers(api_key),
        json={"opponent": LOW_OPPONENT, "agent_color": "white"},
    )
    game_id = create.json()["game_id"]

    board = client.get(f"/api/v1/games/{game_id}/board.txt", headers=auth_headers(api_key))
    assert board.status_code == 200
    assert board.headers["content-type"].startswith("text/plain")
    assert board.headers["cache-control"] == "no-store"
    assert "8 r n b q k b n r" in board.text
    assert "1 R N B Q K B N R" in board.text
    assert "fen" not in board.text.lower()
    assert "legal" not in board.text.lower()

    denied = client.get(f"/api/v1/games/{game_id}/board.txt", headers=auth_headers(other_key))
    assert denied.status_code == 401

    moved = client.post(f"/api/v1/games/{game_id}/move/e2e4", headers=auth_headers(api_key))
    assert moved.status_code == 200
    updated = client.get(f"/api/v1/games/{game_id}/board.txt", headers=auth_headers(api_key))
    assert "4 . . . . P . . ." in updated.text


def test_api_v1_status_includes_play_rating(api_client):
    client, harness_dir = api_client
    reg = client.post("/api/v1/agents", json={"id": "est-agent", "name": "Est Agent"})
    api_key = reg.json()["api_key"]

    create = client.post(
        "/api/v1/games",
        headers=auth_headers(api_key),
        json={"opponent": LOW_OPPONENT, "agent_color": "white"},
    )
    game_id = create.json()["game_id"]

    gm = GameManager(str(harness_dir))
    state = gm.load_state(game_id)
    state.update(
        {
            "status": "finished",
            "result": "1-0",
            "quality_at": "2026-01-01T00:00:00+00:00",
            "white_accuracy": 90.0,
            "black_accuracy": 55.0,
            "white_play_rating": 1200.0,
            "black_play_rating": 800.0,
            "agent_play_rating": 1200.0,
        }
    )
    gm.save_state(game_id, state)

    status = client.get(f"/api/v1/games/{game_id}/status", headers=auth_headers(api_key))
    assert status.status_code == 200
    data = status.json()
    assert data["ok"] is True
    assert data["white_play_rating"] == 1200.0
    assert data["black_play_rating"] == 800.0
    assert data["agent_play_rating"] == 1200.0
    assert data["white_accuracy"] == 90.0
    assert_game_api_no_leaks(data)


def test_ave_agent_joined_false_until_board_read(api_client):
    client, harness_dir = api_client
    reg = client.post("/api/v1/agents", json={"id": "ave-join-agent", "name": "AvE Join"})
    api_key = reg.json()["api_key"]

    create = client.post(
        "/api/v1/games",
        headers=auth_headers(api_key),
        json={"opponent": LOW_OPPONENT, "agent_color": "white"},
    )
    assert create.status_code == 200, create.text
    game_id = create.json()["game_id"]

    gm = GameManager(str(harness_dir))
    assert gm.load_state(game_id).get("agent_joined") is False

    spec = client.get(f"/api/games/{game_id}/state")
    assert spec.status_code == 200
    assert spec.json().get("agent_joined") is False

    status = client.get(f"/api/v1/games/{game_id}/status", headers=auth_headers(api_key))
    assert status.status_code == 200
    assert gm.load_state(game_id).get("agent_joined") is False

    board = client.get(f"/api/v1/games/{game_id}/board", headers=auth_headers(api_key))
    assert board.status_code == 200
    assert gm.load_state(game_id).get("agent_joined") is True
    assert client.get(f"/api/games/{game_id}/state").json().get("agent_joined") is True

    gm.save_state(game_id, {**gm.load_state(game_id), "agent_joined": False})
    text = client.get(f"/api/v1/games/{game_id}/board.txt", headers=auth_headers(api_key))
    assert text.status_code == 200
    assert gm.load_state(game_id).get("agent_joined") is True


def test_api_v1_can_create_second_game_after_first_finishes(api_client):
    client, _ = api_client
    reg = client.post("/api/v1/agents", json={"id": "replay-agent", "name": "Replay"})
    api_key = reg.json()["api_key"]

    first = client.post(
        "/api/v1/games",
        headers=auth_headers(api_key),
        json={"opponent": LOW_OPPONENT, "agent_color": "white"},
    )
    assert first.status_code == 200
    first_id = first.json()["game_id"]

    client.post(f"/api/v1/games/{first_id}/resign", headers=auth_headers(api_key))

    second = client.post(
        "/api/v1/games",
        headers=auth_headers(api_key),
        json={"opponent": LOW_OPPONENT, "agent_color": "white"},
    )
    assert second.status_code == 200, second.text
    second_id = second.json()["game_id"]
    assert second_id != first_id

    move = client.post(
        f"/api/v1/games/{second_id}/move/e2e4",
        headers=auth_headers(api_key),
    )
    assert move.status_code == 200, move.text


def test_api_v1_observation_text_and_vision(api_client):
    client, _ = api_client

    vision_reg = client.post(
        "/api/v1/agents", json={"id": "vision-fixture", "name": "Vision Fixture"}
    )
    assert vision_reg.status_code == 200
    assert vision_reg.json()["observation"] == "vision"

    text_reg = client.post(
        "/api/v1/agents",
        json={"id": "text-fixture", "name": "Text Fixture", "observation": "text"},
    )
    assert text_reg.status_code == 200
    assert text_reg.json()["observation"] == "text"

    remint = client.post(
        "/api/v1/agents",
        json={"id": "text-fixture", "observation": "vision"},
    )
    assert remint.status_code == 200
    assert remint.json()["observation"] == "text"

    listed = {a["id"]: a for a in client.get("/api/v1/agents").json()["agents"]}
    assert listed["vision-fixture"]["observation"] == "vision"
    assert listed["text-fixture"]["observation"] == "text"

    bad = client.post(
        "/api/v1/agents",
        json={"id": "bad-obs", "observation": "fen"},
    )
    assert bad.status_code == 400


def test_api_v1_result_row_snapshots_observation(api_client):
    client, harness_dir = api_client
    reg = client.post(
        "/api/v1/agents",
        json={"id": "text-result-agent", "observation": "text"},
    )
    api_key = reg.json()["api_key"]

    create = client.post(
        "/api/v1/games",
        headers=auth_headers(api_key),
        json={"opponent": LOW_OPPONENT, "agent_color": "white"},
    )
    assert create.status_code == 200
    game_id = create.json()["game_id"]
    brief = create.json().get("agent_brief") or ""
    assert "image/png" not in brief.lower()
    assert "Do not fetch the board PNG" in brief

    state = GameManager(str(harness_dir)).load_state(game_id)
    assert state.get("observation") == "text"

    resign = client.post(
        f"/api/v1/games/{game_id}/resign", headers=auth_headers(api_key)
    )
    assert resign.status_code == 200

    results_path = harness_dir / "results.jsonl"
    rows = [json.loads(line) for line in results_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    row = next(r for r in rows if r.get("game_id") == game_id)
    assert row.get("observation") == "text"
