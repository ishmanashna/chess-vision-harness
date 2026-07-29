"""Phase 2 tests for human play API (/api/play)."""

from __future__ import annotations

from test_human_vs_agent import _auth, _create_human_game, _register_agent, human_client


def _play_auth(play_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {play_token}"}


def test_play_token_auth(human_client, monkeypatch):
    client, _ = human_client
    api_key, _ = _register_agent(client)
    data = _create_human_game(client, api_key, monkeypatch=monkeypatch)
    game_id = data["game_id"]
    play_token = data["play_token"]

    ok = client.get(f"/api/play/{game_id}/position", headers=_play_auth(play_token))
    assert ok.status_code == 200, ok.text
    assert "fen" in ok.json()

    missing = client.get(f"/api/play/{game_id}/position")
    assert missing.status_code == 401

    bad = client.get(f"/api/play/{game_id}/position", headers=_play_auth("not-the-token"))
    assert bad.status_code == 401

    query_ok = client.get(f"/api/play/{game_id}/position?token={play_token}")
    assert query_ok.status_code == 200


def test_play_illegal_move(human_client, monkeypatch):
    client, _ = human_client
    api_key, _ = _register_agent(client)
    data = _create_human_game(client, api_key, agent_color="black", monkeypatch=monkeypatch)
    game_id = data["game_id"]
    play_token = data["play_token"]

    illegal = client.post(
        f"/api/play/{game_id}/move/e2e5",
        headers=_play_auth(play_token),
    )
    assert illegal.status_code == 400
    assert "Illegal" in illegal.json()["error"] or "Invalid" in illegal.json()["error"]


def test_play_off_turn(human_client, monkeypatch):
    client, _ = human_client
    api_key, _ = _register_agent(client)
    data = _create_human_game(client, api_key, monkeypatch=monkeypatch)
    game_id = data["game_id"]
    play_token = data["play_token"]

    off_turn = client.post(
        f"/api/play/{game_id}/move/e7e5",
        headers=_play_auth(play_token),
    )
    assert off_turn.status_code == 400
    assert off_turn.json()["error"] == "Not your turn"


def test_fen_only_on_play_api(human_client, monkeypatch):
    client, _ = human_client
    api_key, _ = _register_agent(client)
    data = _create_human_game(client, api_key, monkeypatch=monkeypatch)
    game_id = data["game_id"]
    play_token = data["play_token"]

    play_pos = client.get(f"/api/play/{game_id}/position", headers=_play_auth(play_token))
    assert play_pos.status_code == 200
    play_json = play_pos.json()
    assert play_json.get("fen")
    assert "legal_moves_uci" in play_json

    agent_status = client.get(f"/api/v1/games/{game_id}/status", headers=_auth(api_key))
    assert agent_status.status_code == 200
    status_json = agent_status.json()
    assert "fen" not in status_json
    assert "board_fen" not in status_json
    assert "legal_moves_uci" not in status_json

    agent_board = client.get(f"/api/v1/games/{game_id}/board", headers=_auth(api_key))
    assert agent_board.status_code == 200
    assert agent_board.headers["content-type"] == "image/png"


def test_human_agent_game_over_http(human_client, monkeypatch):
    client, _ = human_client
    api_key, _ = _register_agent(client)
    data = _create_human_game(client, api_key, monkeypatch=monkeypatch)
    game_id = data["game_id"]
    play_token = data["play_token"]

    agent_move = client.post(f"/api/v1/games/{game_id}/move/e2e4", headers=_auth(api_key))
    assert agent_move.status_code == 200, agent_move.text

    human_move = client.post(
        f"/api/play/{game_id}/move/e7e5",
        headers=_play_auth(play_token),
    )
    assert human_move.status_code == 200, human_move.text
    body = human_move.json()
    assert body["your_turn"] is False
    assert body.get("fen")
    assert body["game_over"] is False
    assert body.get("human_color") == "BLACK"
    assert body.get("agent_joined") is True
    assert "legal_moves_uci" in body
    assert body.get("agent_display_name")
    assert body.get("agent_elo") is not None

    agent_move2 = client.post(f"/api/v1/games/{game_id}/move/g1f3", headers=_auth(api_key))
    assert agent_move2.status_code == 200, agent_move2.text

    human_move2 = client.post(
        f"/api/play/{game_id}/move/b8c6",
        headers=_play_auth(play_token),
    )
    assert human_move2.status_code == 200, human_move2.text

    pos = client.get(f"/api/play/{game_id}/position", headers=_play_auth(play_token))
    assert pos.status_code == 200
    pos_json = pos.json()
    assert pos_json["move_count"] == 4
    assert pos_json["agent_joined"] is True
    assert pos_json.get("human_color") == "BLACK"
    assert pos_json.get("agent_elo") is not None


def test_play_position_includes_move_rows(human_client, monkeypatch):
    client, _ = human_client
    api_key, _ = _register_agent(client)
    data = _create_human_game(client, api_key, monkeypatch=monkeypatch)
    game_id = data["game_id"]
    play_token = data["play_token"]

    client.post(f"/api/v1/games/{game_id}/move/e2e4", headers=_auth(api_key))
    client.post(
        f"/api/play/{game_id}/move/e7e5",
        headers=_play_auth(play_token),
    )

    pos = client.get(f"/api/play/{game_id}/position", headers=_play_auth(play_token))
    assert pos.status_code == 200
    body = pos.json()
    assert body["move_rows"] == [
        {"num": 1, "white": "e4", "black": "e5"},
    ]
    assert body["move_count"] == 2


def test_play_page_html(human_client, monkeypatch):
    client, _ = human_client
    api_key, _ = _register_agent(client)
    data = _create_human_game(client, api_key, monkeypatch=monkeypatch)
    game_id = data["game_id"]

    page = client.get(f"/play/{game_id}")
    assert page.status_code == 200, page.text
    body = page.text
    assert "play-page.js" in body
    assert "data-play-root" in body
    assert "data-play-moves" in body
    assert "data-draw-offer" in body
    assert "data-download-board" in body
    assert "favicon.ico" in body
    assert f"/g/{game_id}" in body
    assert "common.js" in body
    assert "btn.addEventListener('click',function(){apply(current()" not in body

    missing = client.get("/play/not-a-game")
    assert missing.status_code == 404


def test_human_resign(human_client, monkeypatch):
    client, _ = human_client
    api_key, _ = _register_agent(client)
    data = _create_human_game(client, api_key, agent_color="black", monkeypatch=monkeypatch)
    game_id = data["game_id"]
    play_token = data["play_token"]

    resign = client.post(f"/api/play/{game_id}/resign", headers=_play_auth(play_token))
    assert resign.status_code == 200, resign.text
    assert resign.json()["result"] == "0-1"
    assert resign.json()["game_over"] is True

    finished_move = client.post(
        f"/api/play/{game_id}/move/e7e5",
        headers=_play_auth(play_token),
    )
    assert finished_move.status_code == 400


def test_play_position_idle_end_reason(human_client, monkeypatch):
    from chess_harness.limits import HarnessLimits

    client, _ = human_client
    monkeypatch.setattr(
        "chess_harness.board_controller.load_limits",
        lambda: HarnessLimits(idle_timeout_sec=0),
    )
    api_key, _ = _register_agent(client)
    data = _create_human_game(client, api_key, monkeypatch=monkeypatch)
    game_id = data["game_id"]
    play_token = data["play_token"]

    pos = client.get(f"/api/play/{game_id}/position", headers=_play_auth(play_token))
    assert pos.status_code == 200, pos.text
    body = pos.json()
    assert body["game_over"] is True
    assert body["result"] == "*"
    assert body["end_reason"] == "inactivity"
    assert body["end_reason_label"] == "No result (idle timeout)"


def test_play_board_png_human_orientation(human_client, monkeypatch):
    client, harness_dir = human_client
    api_key, _ = _register_agent(client)
    data = _create_human_game(client, api_key, agent_color="black", monkeypatch=monkeypatch)
    game_id = data["game_id"]
    play_token = data["play_token"]

    client.post(f"/api/v1/games/{game_id}/move/e2e4", headers=_auth(api_key))

    no_auth = client.get(f"/api/play/{game_id}/board.png")
    assert no_auth.status_code == 401

    agent_png = harness_dir / "games" / game_id / "board.png"
    assert agent_png.exists()
    agent_bytes = agent_png.read_bytes()

    human_png = client.get(
        f"/api/play/{game_id}/board.png",
        headers=_play_auth(play_token),
    )
    assert human_png.status_code == 200, human_png.text
    assert human_png.headers["content-type"] == "image/png"
    assert human_png.content != agent_bytes
