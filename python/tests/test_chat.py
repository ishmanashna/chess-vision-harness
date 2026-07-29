"""Phase 6 tests for human-vs-agent chat."""

from __future__ import annotations

import json

from test_human_vs_agent import _auth, _create_human_game, _register_agent, human_client


def _play_auth(play_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {play_token}"}


def test_chat_auth_and_validation(human_client, monkeypatch):
    client, harness_dir = human_client
    api_key, _ = _register_agent(client)
    data = _create_human_game(client, api_key, monkeypatch=monkeypatch)
    game_id = data["game_id"]
    play_token = data["play_token"]

    missing = client.post(f"/api/play/{game_id}/chat", json={"text": "hi"})
    assert missing.status_code == 401

    empty = client.post(
        f"/api/play/{game_id}/chat",
        headers=_play_auth(play_token),
        json={"text": "   "},
    )
    assert empty.status_code == 400
    assert "empty" in empty.json()["error"].lower()

    too_long = client.post(
        f"/api/play/{game_id}/chat",
        headers=_play_auth(play_token),
        json={"text": "x" * 501},
    )
    assert too_long.status_code == 422

    agent_denied = client.post(
        f"/api/v1/games/{game_id}/chat",
        headers=_auth("not-a-key"),
        json={"text": "hello"},
    )
    assert agent_denied.status_code == 401


def test_chat_human_agent_roundtrip(human_client, monkeypatch):
    client, harness_dir = human_client
    api_key, _ = _register_agent(client)
    data = _create_human_game(client, api_key, nickname="Alice", monkeypatch=monkeypatch)
    game_id = data["game_id"]
    play_token = data["play_token"]

    human_post = client.post(
        f"/api/play/{game_id}/chat",
        headers=_play_auth(play_token),
        json={"text": "Good luck!"},
    )
    assert human_post.status_code == 200, human_post.text
    human_body = human_post.json()
    assert human_body["ok"] is True
    assert human_body["message"]["from"] == "human"
    assert human_body["message"]["from_label"] == "Alice"
    assert human_body["message"]["text"] == "Good luck!"
    assert human_body["chat_seq"] == 1

    agent_post = client.post(
        f"/api/v1/games/{game_id}/chat",
        headers=_auth(api_key),
        json={"text": "Thanks — you too."},
    )
    assert agent_post.status_code == 200, agent_post.text
    agent_body = agent_post.json()
    assert agent_body["message"]["from"] == "agent"
    assert agent_body["chat_seq"] == 2

    poll = client.get(
        f"/api/play/{game_id}/chat?since=1",
        headers=_play_auth(play_token),
    )
    assert poll.status_code == 200
    poll_body = poll.json()
    assert poll_body["chat_seq"] == 2
    assert len(poll_body["messages"]) == 1
    assert poll_body["messages"][0]["text"] == "Thanks — you too."

    chat_path = harness_dir / "games" / game_id / "chat.jsonl"
    assert chat_path.exists()
    rows = [json.loads(line) for line in chat_path.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 2
    assert rows[0]["seq"] == 1
    assert rows[1]["seq"] == 2

    state = json.loads((harness_dir / "games" / game_id / "state.json").read_text(encoding="utf-8"))
    assert state.get("chat_seq") == 2


def test_chat_off_turn_allowed(human_client, monkeypatch):
    client, _ = human_client
    api_key, _ = _register_agent(client)
    data = _create_human_game(client, api_key, agent_color="white", monkeypatch=monkeypatch)
    game_id = data["game_id"]
    play_token = data["play_token"]

    off_turn = client.post(
        f"/api/play/{game_id}/chat",
        headers=_play_auth(play_token),
        json={"text": "While you think…"},
    )
    assert off_turn.status_code == 200, off_turn.text

    agent_chat = client.post(
        f"/api/v1/games/{game_id}/chat",
        headers=_auth(api_key),
        json={"text": "One moment."},
    )
    assert agent_chat.status_code == 200, agent_chat.text


def test_agent_brief_documents_chat(human_client, monkeypatch):
    client, _ = human_client
    api_key, _ = _register_agent(client)
    data = _create_human_game(client, api_key, monkeypatch=monkeypatch)
    brief = data.get("agent_brief") or ""
    assert "/api/v1/games/" in brief and "/chat" in brief
    assert "chat_seq" in brief
    assert "social" in brief.lower() or "position source" in brief.lower()


def test_status_includes_chat_seq_after_chat(human_client, monkeypatch):
    client, _ = human_client
    api_key, _ = _register_agent(client)
    data = _create_human_game(client, api_key, nickname="Alice", monkeypatch=monkeypatch)
    game_id = data["game_id"]
    play_token = data["play_token"]

    status_before = client.get(f"/api/v1/games/{game_id}/status", headers=_auth(api_key))
    assert status_before.status_code == 200
    assert status_before.json().get("chat_seq") == 0

    client.post(
        f"/api/play/{game_id}/chat",
        headers=_play_auth(play_token),
        json={"text": "Hello agent"},
    )

    status_after = client.get(f"/api/v1/games/{game_id}/status", headers=_auth(api_key))
    assert status_after.status_code == 200
    assert status_after.json().get("chat_seq") == 1
