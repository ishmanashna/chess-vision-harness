"""Phase 7: remove-game operator CLI."""

from __future__ import annotations

import json

import pytest

from chess_harness.commands import cmd_remove_game
from chess_harness.game_manager import GameManager
from chess_harness.results import ResultsManager


@pytest.fixture
def harness(tmp_path, monkeypatch):
    harness_dir = tmp_path / "harness"
    harness_dir.mkdir()
    monkeypatch.setenv("CHESS_HARNESS_DIR", str(harness_dir))
    return harness_dir


def _write_finished_game(gm: GameManager, game_id: str) -> None:
    state = {
        "game_id": game_id,
        "status": "finished",
        "result": "0-1",
        "end_reason": "resignation",
        "agent_color": "WHITE",
        "model_name": "agent-a",
        "moves": [],
        "pgn_headers": {"Result": "0-1"},
        "board_fen": "start",
    }
    gm.get_game_dir(game_id).mkdir(parents=True, exist_ok=True)
    gm.save_state(game_id, state)
    gm.get_pgn_path(game_id).write_text('[Result "0-1"]\n', encoding="utf-8")


def test_remove_game_dry_run(harness, capsys):
    gm = GameManager(str(harness))
    _write_finished_game(gm, "agent-test-1")
    results_file = harness / "results.jsonl"
    results_file.write_text(
        json.dumps({"game_id": "agent-test-1", "model_name": "agent-a", "result": "0-1"})
        + "\n",
        encoding="utf-8",
    )

    assert cmd_remove_game("agent-test-1", dry_run=True) == 0
    assert gm.game_exists("agent-test-1")
    assert ResultsManager(base_dir=str(harness)).load_results()
    out = capsys.readouterr().out
    assert "would remove" in out
    assert "would delete game directory agent-test-1" in out
    assert "dry run" in out.lower()


def test_remove_game_removes_dir_results_and_rebuilds(harness, monkeypatch):
    gm = GameManager(str(harness))
    rm = ResultsManager(base_dir=str(harness))
    _write_finished_game(gm, "agent-test-1")
    _write_finished_game(gm, "keep-me")
    results_file = harness / "results.jsonl"
    results_file.write_text(
        json.dumps({"game_id": "agent-test-1", "model_name": "agent-a", "result": "0-1"})
        + "\n"
        + json.dumps({"game_id": "keep-me", "model_name": "agent-a", "result": "1-0"})
        + "\n",
        encoding="utf-8",
    )

    rebuild_calls = []
    snapshot_calls = []

    def fake_rebuild():
        rebuild_calls.append(True)

    def fake_export():
        snapshot_calls.append(True)
        return harness / "leaderboard.json"

    monkeypatch.setattr("chess_harness.commands.cmd_rebuild_elo", fake_rebuild)
    monkeypatch.setattr(
        "chess_harness.snapshot_leaderboard.export_leaderboard_snapshot",
        fake_export,
    )

    assert cmd_remove_game("agent-test-1", export_snapshot=True) == 0
    assert not gm.game_exists("agent-test-1")
    assert gm.game_exists("keep-me")
    remaining = rm.load_results()
    assert len(remaining) == 1
    assert remaining[0]["game_id"] == "keep-me"
    assert rebuild_calls
    assert snapshot_calls


def test_remove_game_missing(harness, capsys):
    assert cmd_remove_game("no-such-game") == 1
    assert "No game or results found" in capsys.readouterr().out
