"""Phase 3: prune-no-result operator CLI."""

from __future__ import annotations

import json

import pytest

from chess_harness.commands import cmd_prune_no_result
from chess_harness.game_manager import GameManager
from chess_harness.results import ResultsManager


@pytest.fixture
def harness(tmp_path, monkeypatch):
    harness_dir = tmp_path / "harness"
    harness_dir.mkdir()
    monkeypatch.setenv("CHESS_HARNESS_DIR", str(harness_dir))
    return harness_dir


def _write_idle_game(gm: GameManager, game_id: str) -> None:
    state = {
        "game_id": game_id,
        "status": "finished",
        "result": "*",
        "end_reason": "inactivity",
        "agent_color": "WHITE",
        "model_name": "agent-a",
        "moves": [],
        "pgn_headers": {"Result": "*"},
        "board_fen": "start",
    }
    gm.save_state(game_id, state)
    gm.get_game_dir(game_id).mkdir(parents=True, exist_ok=True)
    gm.get_pgn_path(game_id).write_text('[Result "*"]\n', encoding="utf-8")


def test_prune_no_result_removes_games_and_results(harness, monkeypatch):
    gm = GameManager(str(harness))
    rm = ResultsManager(base_dir=str(harness))
    _write_idle_game(gm, "idle-1")
    results_file = harness / "results.jsonl"
    results_file.write_text(
        json.dumps(
            {
                "game_id": "idle-1",
                "model_name": "agent-a",
                "result": "*",
            }
        )
        + "\n"
        + json.dumps(
            {
                "game_id": "rated-1",
                "model_name": "agent-a",
                "result": "1-0",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    snapshot_calls = []

    def fake_export():
        snapshot_calls.append(True)
        return harness / "leaderboard.json"

    monkeypatch.setattr(
        "chess_harness.snapshot_leaderboard.export_leaderboard_snapshot",
        fake_export,
    )

    assert cmd_prune_no_result(export_snapshot=True) == 0
    assert not gm.game_exists("idle-1")
    remaining = rm.load_results()
    assert len(remaining) == 1
    assert remaining[0]["game_id"] == "rated-1"
    assert snapshot_calls


def test_prune_no_result_dry_run(harness, capsys):
    gm = GameManager(str(harness))
    _write_idle_game(gm, "idle-dry")

    assert cmd_prune_no_result(dry_run=True) == 0
    assert gm.game_exists("idle-dry")
    out = capsys.readouterr().out
    assert "would remove idle-dry" in out
    assert "dry run" in out.lower()


def test_prune_no_result_empty(harness, capsys):
    assert cmd_prune_no_result() == 0
    assert "No no-result games" in capsys.readouterr().out
