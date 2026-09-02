"""Tests for committee prompt-test play (Phase 5)."""

from __future__ import annotations

import shutil
from datetime import datetime, timedelta, timezone

from chess_harness import commands
from chess_harness.board_controller import BoardController
from chess_harness.game_manager import GameManager
from chess_harness.prompt_packs import assert_creatable, load_pack
from chess_harness.prompt_test import (
    cmd_prompt_test_say,
    cmd_prompt_test_start,
    cmd_prompt_test_thread,
    cmd_prompt_test_vote,
)

from conftest import FIXTURES


def _harness_setup(tmp_path, monkeypatch, *, mkdir: bool = True) -> str:
    harness_dir = tmp_path / "harness"
    if mkdir:
        harness_dir.mkdir()
    shutil.copy(FIXTURES / "models.json", harness_dir / "models.json")
    monkeypatch.setenv("CHESS_HARNESS_DIR", str(harness_dir))
    monkeypatch.setenv("MODELS_FILE", str(harness_dir / "models.json"))
    return str(harness_dir)


def _start_committee(tmp_path, monkeypatch):
    harness_dir = _harness_setup(tmp_path, monkeypatch)
    result = cmd_prompt_test_start("composer-2.5", ["e"], opponent="random")
    assert result["ok"] is True
    game = result["games"][0]
    return harness_dir, game["game_id"]


def test_assert_creatable_committee_pack():
    pack = assert_creatable("e")
    assert pack.kind == "committee"
    assert pack.seats == 3


def test_start_committee_three_seats(tmp_path, monkeypatch):
    harness_dir, game_id = _start_committee(tmp_path, monkeypatch)
    state = GameManager(harness_dir).load_state(game_id)
    assert state["prompt_pack_kind"] == "committee"
    assert state["agent_color"] == "WHITE"


def test_cmd_move_rejects_committee_game(tmp_path, monkeypatch):
    harness_dir, game_id = _start_committee(tmp_path, monkeypatch)
    move = commands.cmd_move(game_id, "e2e4")
    assert move["ok"] is False
    assert "vote" in move["error"].lower()
    state = GameManager(harness_dir).load_state(game_id)
    assert state["moves"] == []


def test_say_updates_thread_and_activity(tmp_path, monkeypatch):
    harness_dir, game_id = _start_committee(tmp_path, monkeypatch)
    gm = GameManager(harness_dir)
    before = gm.load_state(game_id)["last_activity"]

    say = cmd_prompt_test_say(game_id, 1, "I see e2e4")
    assert say["ok"] is True
    assert say["ply"] == 0
    assert len(say["notes"]) == 1
    assert say["notes"][0]["seat"] == 1
    assert say["notes"][0]["ply"] == 0
    assert say["notes"][0]["text"] == "I see e2e4"

    thread = cmd_prompt_test_thread(game_id)
    assert thread["ok"] is True
    assert thread["notes"] == say["notes"]

    after = gm.load_state(game_id)["last_activity"]
    assert after >= before


def test_two_votes_play_and_advance_ply(tmp_path, monkeypatch):
    harness_dir, game_id = _start_committee(tmp_path, monkeypatch)
    gm = GameManager(harness_dir)

    v1 = cmd_prompt_test_vote(game_id, 1, "e2e4")
    assert v1["ok"] is True
    assert v1["status"] == "open"

    v2 = cmd_prompt_test_vote(game_id, 2, "e2e4")
    assert v2["ok"] is True
    assert v2.get("move") == "e2e4"
    assert v2["ply"] == 0
    assert v2["status"] == "played"

    state = gm.load_state(game_id)
    assert state["status"] == "in_progress"
    assert state["moves"][0] == "e2e4"
    assert len(state["moves"]) >= 1

    v3 = cmd_prompt_test_vote(game_id, 3, "e2e3")
    assert v3["ok"] is False
    assert "wrong ply" in v3["error"].lower()

    thread = cmd_prompt_test_thread(game_id)
    assert thread["ok"] is True
    assert thread["ply"] == 1
    assert thread["status"] == "open"


def test_three_different_votes_tied_no_move(tmp_path, monkeypatch):
    harness_dir, game_id = _start_committee(tmp_path, monkeypatch)
    gm = GameManager(harness_dir)

    cmd_prompt_test_vote(game_id, 1, "e2e4")
    cmd_prompt_test_vote(game_id, 2, "e2e3")
    tied = cmd_prompt_test_vote(game_id, 3, "d2d4")

    assert tied["ok"] is True
    assert tied["status"] == "tied"
    state = gm.load_state(game_id)
    assert state["status"] == "in_progress"
    assert state["moves"] == []


def test_illegal_majority_rejected_clears_votes(tmp_path, monkeypatch):
    harness_dir, game_id = _start_committee(tmp_path, monkeypatch)
    gm = GameManager(harness_dir)

    cmd_prompt_test_vote(game_id, 1, "e2e5")
    rejected = cmd_prompt_test_vote(game_id, 2, "e2e5")

    assert rejected["ok"] is True
    assert rejected["status"] == "rejected"
    assert rejected["votes"] == []
    state = gm.load_state(game_id)
    assert state["status"] == "in_progress"
    assert state["moves"] == []


def test_say_resets_idle_timeout(tmp_path, monkeypatch):
    harness_dir, game_id = _start_committee(tmp_path, monkeypatch)
    monkeypatch.setenv("CHESS_HARNESS_IDLE_TIMEOUT_SEC", "60")
    gm = GameManager(harness_dir)
    ctrl = BoardController(gm)
    stale = datetime.now(timezone.utc) - timedelta(seconds=120)

    control_id = cmd_prompt_test_start("composer-2.5", ["e"], opponent="random")["games"][0]["game_id"]
    control_state = gm.load_state(control_id)
    control_state["last_activity"] = stale.isoformat()
    gm.save_state(control_id, control_state)
    ended_control = ctrl.check_idle_games()
    assert control_id in ended_control

    state = gm.load_state(game_id)
    state["last_activity"] = stale.isoformat()
    gm.save_state(game_id, state)

    say = cmd_prompt_test_say(game_id, 1, "still here")
    assert say["ok"] is True

    ended_after = ctrl.check_idle_games()
    assert game_id not in ended_after
    assert gm.load_state(game_id)["status"] == "in_progress"


def test_vote_resets_idle_timeout(tmp_path, monkeypatch):
    harness_dir, game_id = _start_committee(tmp_path, monkeypatch)
    monkeypatch.setenv("CHESS_HARNESS_IDLE_TIMEOUT_SEC", "60")
    gm = GameManager(harness_dir)
    ctrl = BoardController(gm)
    stale = datetime.now(timezone.utc) - timedelta(seconds=120)

    state = gm.load_state(game_id)
    state["last_activity"] = stale.isoformat()
    gm.save_state(game_id, state)

    vote = cmd_prompt_test_vote(game_id, 1, "e2e4")
    assert vote["ok"] is True

    ended_after = ctrl.check_idle_games()
    assert game_id not in ended_after
    assert gm.load_state(game_id)["status"] == "in_progress"


def test_say_and_vote_rejected_after_resign(tmp_path, monkeypatch):
    harness_dir, game_id = _start_committee(tmp_path, monkeypatch)
    gm = GameManager(harness_dir)
    resigned = commands.cmd_resign(game_id)
    assert resigned["ok"] is True
    assert gm.load_state(game_id)["status"] != "in_progress"

    say = cmd_prompt_test_say(game_id, 1, "after the game")
    assert say["ok"] is False
    assert "already over" in say["error"].lower()

    vote = cmd_prompt_test_vote(game_id, 1, "e2e4")
    assert vote["ok"] is False
    assert "already over" in vote["error"].lower()
    assert gm.load_state(game_id)["moves"] == []


def test_thread_does_not_advance_after_game_over(tmp_path, monkeypatch):
    harness_dir, game_id = _start_committee(tmp_path, monkeypatch)
    gm = GameManager(harness_dir)

    cmd_prompt_test_vote(game_id, 1, "e2e4")
    played = cmd_prompt_test_vote(game_id, 2, "e2e4")
    assert played["ok"] is True
    assert played["status"] == "played"
    assert played["ply"] == 0

    resigned = commands.cmd_resign(game_id)
    assert resigned["ok"] is True

    thread = cmd_prompt_test_thread(game_id)
    assert thread["ok"] is True
    assert thread["ply"] == 0
    assert thread["status"] == "played"


def test_committee_pack_metadata():
    pack = load_pack("e")
    assert pack.kind == "committee"
    assert pack.seats == 3
