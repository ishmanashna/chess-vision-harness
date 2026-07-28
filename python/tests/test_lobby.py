"""Tests for AvaA lobby store."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from chess_harness.lobby import (
    ELO_BAND,
    LobbyStore,
    MAX_LOBBIES_PER_MODEL,
    assign_colors,
)


def test_create_list_cancel(tmp_path):
    store = LobbyStore(tmp_path / "lobbies.json")
    lob = store.create_waiting(
        host_model_id="host-a",
        host_display_name="Host A",
        host_elo=500,
        color_offer="white",
    )
    assert lob["status"] == "waiting"
    assert lob["color_offer"] == "white"
    waiting = store.list_waiting()
    assert len(waiting) == 1
    assert store.cancel(lob["lobby_id"], "host-a") is True
    assert store.list_waiting() == []


def test_max_lobbies_per_model(tmp_path):
    store = LobbyStore(tmp_path / "lobbies.json")
    for _ in range(MAX_LOBBIES_PER_MODEL):
        store.create_waiting(
            host_model_id="host-a",
            host_display_name="Host A",
            host_elo=500,
            color_offer="random",
        )
    try:
        store.create_waiting(
            host_model_id="host-a",
            host_display_name="Host A",
            host_elo=500,
            color_offer="random",
        )
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_find_matchable_elo_band(tmp_path):
    store = LobbyStore(tmp_path / "lobbies.json")
    near = store.create_waiting(
        host_model_id="host-near",
        host_display_name="Near",
        host_elo=500,
        color_offer="black",
    )
    store.create_waiting(
        host_model_id="host-far",
        host_display_name="Far",
        host_elo=500 + ELO_BAND + 50,
        color_offer="white",
    )
    found = store.find_matchable("joiner", 520)
    assert found is not None
    assert found["lobby_id"] == near["lobby_id"]
    # Outside band relative to both hosts (500 and 1150)
    assert store.find_matchable("joiner", 500 + 2 * ELO_BAND + 100) is None


def test_assign_colors():
    w = assign_colors("white", "host", "join")
    assert w["white_model_id"] == "host"
    assert w["black_model_id"] == "join"
    b = assign_colors("black", "host", "join")
    assert b["white_model_id"] == "join"
    assert b["black_model_id"] == "host"


def test_mark_matched(tmp_path):
    store = LobbyStore(tmp_path / "lobbies.json")
    lob = store.create_waiting(
        host_model_id="a",
        host_display_name="A",
        host_elo=500,
        color_offer="random",
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
