"""Phase 4 tests for AvH draw offers."""

from __future__ import annotations

import json

from chess_harness.game_manager import GameManager
from chess_harness.game_types import GAME_TYPE_HUMAN_VS_AGENT

from test_human_play_api import _play_auth
from test_human_vs_agent import _auth, _create_human_game, _register_agent

pytest_plugins = ["test_human_vs_agent"]


def test_agent_offers_human_accepts_draw(human_client, monkeypatch):
    client, harness_dir = human_client
    api_key, _ = _register_agent(client)
    data = _create_human_game(client, api_key, agent_color="black", monkeypatch=monkeypatch)
    game_id = data["game_id"]
    play_token = data["play_token"]

    # Human (white) opens; agent (black) to move
    client.post(f"/api/play/{game_id}/move/e2e4", headers=_play_auth(play_token))

    offer = client.post(f"/api/v1/games/{game_id}/draw/offer", headers=_auth(api_key))
    assert offer.status_code == 200, offer.text
    body = offer.json()
    assert body["draw_offer_pending"] is True
    assert body["draw_offered_by"] == "BLACK"
    assert body["you_offered_draw"] is True
    assert body["can_offer_draw"] is False

    pos = client.get(f"/api/play/{game_id}/position", headers=_play_auth(play_token))
    assert pos.status_code == 200
    pos_json = pos.json()
    assert pos_json["can_respond_draw"] is True
    assert pos_json["draw_offered_by"] == "BLACK"

    accept = client.post(f"/api/play/{game_id}/draw/accept", headers=_play_auth(play_token))
    assert accept.status_code == 200, accept.text
    accept_json = accept.json()
    assert accept_json["game_over"] is True
    assert accept_json["result"] == "1/2-1/2"
    assert accept_json["end_reason"] == "agreement"
    assert accept_json["end_reason_label"] == "Draw by agreement"

    rows = [
        json.loads(line)
        for line in (harness_dir / "results.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    row = next(r for r in rows if r.get("game_id") == game_id)
    assert row["result"] == "1/2-1/2"
    assert row["reason"] == "agreement"
    assert row["game_type"] == GAME_TYPE_HUMAN_VS_AGENT


def test_human_offers_agent_declines(human_client, monkeypatch):
    client, harness_dir = human_client
    api_key, _ = _register_agent(client)
    data = _create_human_game(client, api_key, agent_color="black", monkeypatch=monkeypatch)
    game_id = data["game_id"]
    play_token = data["play_token"]

    offer = client.post(f"/api/play/{game_id}/draw/offer", headers=_play_auth(play_token))
    assert offer.status_code == 200, offer.text
    assert offer.json()["you_offered_draw"] is True

    decline = client.post(f"/api/v1/games/{game_id}/draw/decline", headers=_auth(api_key))
    assert decline.status_code == 200, decline.text
    assert decline.json()["draw_offer_pending"] is False

    state = GameManager(str(harness_dir)).load_state(game_id)
    assert state is not None
    assert state.get("draw_offer") is None
    assert state["status"] == "in_progress"


def test_move_clears_pending_draw_offer(human_client, monkeypatch):
    client, harness_dir = human_client
    api_key, _ = _register_agent(client)
    data = _create_human_game(client, api_key, monkeypatch=monkeypatch)
    game_id = data["game_id"]
    play_token = data["play_token"]

    client.post(f"/api/v1/games/{game_id}/move/e2e4", headers=_auth(api_key))
    client.post(f"/api/play/{game_id}/draw/offer", headers=_play_auth(play_token))
    state = GameManager(str(harness_dir)).load_state(game_id)
    assert state is not None
    assert state.get("draw_offer") is not None

    move = client.post(
        f"/api/play/{game_id}/move/e7e5",
        headers=_play_auth(play_token),
    )
    assert move.status_code == 200, move.text

    state = GameManager(str(harness_dir)).load_state(game_id)
    assert state is not None
    assert state.get("draw_offer") is None


def test_draw_offer_off_turn_allowed(human_client, monkeypatch):
    client, _ = human_client
    api_key, _ = _register_agent(client)
    data = _create_human_game(client, api_key, monkeypatch=monkeypatch)
    game_id = data["game_id"]
    play_token = data["play_token"]
    assert data["human_color"] == "BLACK"

    pos = client.get(f"/api/play/{game_id}/position", headers=_play_auth(play_token))
    assert pos.status_code == 200
    assert pos.json()["can_offer_draw"] is True

    off_turn = client.post(f"/api/play/{game_id}/draw/offer", headers=_play_auth(play_token))
    assert off_turn.status_code == 200, off_turn.text
    body = off_turn.json()
    assert body["draw_offer_pending"] is True
    assert body["you_offered_draw"] is True
    assert body["can_offer_draw"] is False


def test_human_offers_draw_after_move(human_client, monkeypatch):
    client, _ = human_client
    api_key, _ = _register_agent(client)
    data = _create_human_game(client, api_key, agent_color="black", monkeypatch=monkeypatch)
    game_id = data["game_id"]
    play_token = data["play_token"]

    move = client.post(f"/api/play/{game_id}/move/e2e4", headers=_play_auth(play_token))
    assert move.status_code == 200, move.text

    pos = client.get(f"/api/play/{game_id}/position", headers=_play_auth(play_token))
    assert pos.status_code == 200
    assert pos.json()["can_offer_draw"] is True

    offer = client.post(f"/api/play/{game_id}/draw/offer", headers=_play_auth(play_token))
    assert offer.status_code == 200, offer.text
    assert offer.json()["you_offered_draw"] is True


def test_cannot_accept_own_draw_offer(human_client, monkeypatch):
    client, _ = human_client
    api_key, _ = _register_agent(client)
    data = _create_human_game(client, api_key, agent_color="black", monkeypatch=monkeypatch)
    game_id = data["game_id"]
    play_token = data["play_token"]

    client.post(f"/api/play/{game_id}/draw/offer", headers=_play_auth(play_token))
    own = client.post(f"/api/play/{game_id}/draw/accept", headers=_play_auth(play_token))
    assert own.status_code == 400
    assert "own" in own.json()["error"].lower()


def test_agent_brief_documents_draw(human_client, monkeypatch):
    client, _ = human_client
    api_key, _ = _register_agent(client)
    data = _create_human_game(client, api_key, monkeypatch=monkeypatch)
    brief = data.get("agent_brief") or ""
    assert "/draw/offer" in brief
    assert "/draw/accept" in brief
    assert "/draw/decline" in brief
    assert "/resign" in brief
    assert "when can_offer_draw is true" in brief
    assert "on your turn" not in brief.lower()
