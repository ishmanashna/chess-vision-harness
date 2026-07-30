"""Tests for AvaA lobby store."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from chess_harness.lobby import (
    ELO_BAND,
    LobbyStore,
    assign_colors,
)


def test_create_list_cancel(tmp_path):
    store = LobbyStore(tmp_path / "lobbies.json")
    lob = store.create_waiting(
        host_model_id="host-a",
        host_display_name="Host A",
        host_elo=500,
    )
    assert lob["status"] == "waiting"
    assert "color_offer" not in lob
    waiting = store.list_waiting()
    assert len(waiting) == 1
    assert store.cancel(lob["lobby_id"], "host-a") is True
    assert store.list_waiting() == []


def test_reattach_waiting_lobby(tmp_path):
    store = LobbyStore(tmp_path / "lobbies.json")
    first = store.create_waiting(
        host_model_id="host-a",
        host_display_name="Host A",
        host_elo=500,
    )
    second = store.create_waiting(
        host_model_id="host-a",
        host_display_name="Host A",
        host_elo=500,
    )
    assert second["lobby_id"] != first["lobby_id"]
    assert store.find_waiting_for_model("host-a")["lobby_id"] == first["lobby_id"]
    assert len(store.list_waiting()) == 2


def test_find_waiting_for_model(tmp_path):
    store = LobbyStore(tmp_path / "lobbies.json")
    assert store.find_waiting_for_model("host-a") is None
    lob = store.create_waiting(
        host_model_id="host-a",
        host_display_name="Host A",
        host_elo=500,
    )
    found = store.find_waiting_for_model("host-a")
    assert found is not None
    assert found["lobby_id"] == lob["lobby_id"]


def test_find_matchable_elo_band(tmp_path):
    store = LobbyStore(tmp_path / "lobbies.json")
    near = store.create_waiting(
        host_model_id="host-near",
        host_display_name="Near",
        host_elo=500,
    )
    store.create_waiting(
        host_model_id="host-far",
        host_display_name="Far",
        host_elo=500 + ELO_BAND + 50,
    )
    found = store.find_matchable("joiner", 520)
    assert found is not None
    assert found["lobby_id"] == near["lobby_id"]
    assert store.find_matchable("joiner", 500 + 2 * ELO_BAND + 100) is None


def test_assign_colors_random():
    seen = set()
    for _ in range(40):
        colors = assign_colors("host", "join")
        pair = (colors["white_model_id"], colors["black_model_id"])
        assert set(pair) == {"host", "join"}
        seen.add(pair)
    assert ("host", "join") in seen
    assert ("join", "host") in seen


def test_mark_matched(tmp_path):
    store = LobbyStore(tmp_path / "lobbies.json")
    lob = store.create_waiting(
        host_model_id="a",
        host_display_name="A",
        host_elo=500,
    )
    matched = store.mark_matched(
        lob["lobby_id"],
        game_id="game-1",
        white_model_id="a",
        black_model_id="b",
    )
    assert matched is not None
    assert matched["status"] == "matched"
    assert matched["game_id"] == "game-1"
    assert store.list_waiting() == []
