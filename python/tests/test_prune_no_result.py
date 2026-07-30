"""Phase 1: prune-no-result operator CLI (rebuild Elo + orphan scrub)."""

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

    assert cmd_prune_no_result(export_snapshot=True) == 0
    assert not gm.game_exists("idle-1")
    remaining = rm.load_results()
    assert len(remaining) == 1
    assert remaining[0]["game_id"] == "rated-1"
    assert rebuild_calls
    assert snapshot_calls


def test_prune_no_result_scrubs_orphan_results(harness, monkeypatch):
    rm = ResultsManager(base_dir=str(harness))
    results_file = harness / "results.jsonl"
    results_file.write_text(
        json.dumps(
            {
                "game_id": "orphan-idle",
                "model_name": "agent-a",
                "result": "*",
                "reason": "inactivity",
            }
        )
        + "\n"
        + json.dumps(
            {
                "game_id": "rated-keep",
                "model_name": "agent-a",
                "result": "1-0",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    rebuild_calls = []

    def fake_rebuild():
        rebuild_calls.append(True)

    monkeypatch.setattr("chess_harness.commands.cmd_rebuild_elo", fake_rebuild)
    monkeypatch.setattr(
        "chess_harness.snapshot_leaderboard.export_leaderboard_snapshot",
        lambda: harness / "leaderboard.json",
    )

    assert cmd_prune_no_result(export_snapshot=False) == 0
    remaining = rm.load_results()
    assert len(remaining) == 1
    assert remaining[0]["game_id"] == "rated-keep"
    assert rebuild_calls


def test_prune_no_result_dry_run(harness, capsys):
    gm = GameManager(str(harness))
    _write_idle_game(gm, "idle-dry")
    results_file = harness / "results.jsonl"
    results_file.write_text(
        json.dumps(
            {
                "game_id": "orphan-dry",
                "model_name": "agent-a",
                "result": "*",
                "reason": "inactivity",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    assert cmd_prune_no_result(dry_run=True) == 0
    assert gm.game_exists("idle-dry")
    assert ResultsManager(base_dir=str(harness)).load_results()
    out = capsys.readouterr().out
    assert "would remove idle-dry" in out
    assert "would scrub orphan results for orphan-dry" in out
    assert "would rebuild-elo" in out
    assert "dry run" in out.lower()


def test_prune_no_result_keeps_legacy_idle_resign(harness, monkeypatch):
    """Decisive games with end_reason inactivity (old idle→resign) must stay."""
    gm = GameManager(str(harness))
    rm = ResultsManager(base_dir=str(harness))
    state = {
        "game_id": "legacy-idle-resign",
        "status": "finished",
        "result": "0-1",
        "end_reason": "inactivity",
        "agent_color": "WHITE",
        "model_name": "agent-a",
        "moves": ["e2e4"],
        "pgn_headers": {"Result": "0-1"},
        "board_fen": "start",
    }
    gm.save_state("legacy-idle-resign", state)
    gm.get_pgn_path("legacy-idle-resign").write_text('[Result "0-1"]\n', encoding="utf-8")
    (harness / "results.jsonl").write_text(
        json.dumps(
            {
                "game_id": "legacy-idle-resign",
                "model_name": "agent-a",
                "result": "0-1",
                "reason": "inactivity",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr("chess_harness.commands.cmd_rebuild_elo", lambda: None)
    monkeypatch.setattr(
        "chess_harness.snapshot_leaderboard.export_leaderboard_snapshot",
        lambda: harness / "leaderboard.json",
    )

    assert cmd_prune_no_result(export_snapshot=False) == 0
    assert gm.game_exists("legacy-idle-resign")
    remaining = rm.load_results()
    assert len(remaining) == 1
    assert remaining[0]["game_id"] == "legacy-idle-resign"


def test_prune_no_result_empty(harness, capsys):
    assert cmd_prune_no_result() == 0
    assert "No no-result games" in capsys.readouterr().out
