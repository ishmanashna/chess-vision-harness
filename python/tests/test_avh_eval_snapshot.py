"""AvH spectator eval: snapshot on move, no Stockfish per poll."""

from __future__ import annotations

import chess_harness.spectator as spec
from chess_harness.game_manager import GameManager
from test_human_vs_agent import _auth, _create_human_game, _register_agent, human_client


def test_avh_move_snapshots_last_eval_cp(human_client, monkeypatch):
    client, harness_dir = human_client
    api_key, _ = _register_agent(client)
    created = _create_human_game(client, api_key, monkeypatch=monkeypatch)
    game_id = created["game_id"]

    move = client.post(f"/api/v1/games/{game_id}/move/e2e4", headers=_auth(api_key))
    assert move.status_code == 200, move.text

    state = GameManager(str(harness_dir)).load_state(game_id)
    assert state is not None
    assert state.get("last_eval_cp") is not None


def test_avh_state_poll_uses_snapshot_not_live_eval(human_client, monkeypatch):
    client, harness_dir = human_client
    api_key, _ = _register_agent(client)
    created = _create_human_game(client, api_key, monkeypatch=monkeypatch)
    game_id = created["game_id"]

    move = client.post(f"/api/v1/games/{game_id}/move/e2e4", headers=_auth(api_key))
    assert move.status_code == 200, move.text

    state = GameManager(str(harness_dir)).load_state(game_id)
    assert state is not None
    assert state.get("last_eval_cp") is not None

    spec._eval_cache.clear()
    calls = {"n": 0}

    def counting_eval(fen: str):
        calls["n"] += 1
        return 42

    monkeypatch.setattr(spec, "_eval_position", counting_eval)

    first = client.get(f"/api/games/{game_id}/state")
    assert first.status_code == 200
    assert first.json().get("eval_ui") is not None
    assert calls["n"] == 0

    second = client.get(f"/api/games/{game_id}/state")
    assert second.status_code == 200
    assert second.json().get("eval_ui") is not None
    assert calls["n"] == 0
