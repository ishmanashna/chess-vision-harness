"""Phase 2: packed games off public numbers, loopback-only spectator."""

from __future__ import annotations

import shutil
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from conftest import FIXTURES

from chess_harness import commands
from chess_harness.board_controller import BoardController
from chess_harness.finished_games_db import get_finished_game
from chess_harness.game_manager import GameManager
from chess_harness.models import ModelRegistry
from chess_harness.paths import resolve_finished_games_db
from chess_harness.results import ResultsManager
from chess_harness.spectator import app


def _harness_setup(tmp_path, monkeypatch) -> Path:
    harness_dir = tmp_path / "harness"
    harness_dir.mkdir()
    shutil.copy(FIXTURES / "models.json", harness_dir / "models.json")
    monkeypatch.setenv("CHESS_HARNESS_DIR", str(harness_dir))
    monkeypatch.setenv("MODELS_FILE", str(harness_dir / "models.json"))
    return harness_dir


def _registry(harness_dir: Path) -> ModelRegistry:
    return ModelRegistry(harness_dir / "models.json")


def _last_result(harness_dir: Path) -> dict:
    rows = ResultsManager(base_dir=str(harness_dir)).load_results()
    assert rows, "expected at least one result row"
    return rows[-1]


@pytest.fixture
def privacy_client(tmp_path, monkeypatch):
    harness_dir = _harness_setup(tmp_path, monkeypatch)

    import chess_harness.api_limits as api_limits
    import chess_harness.spectator as spec

    api_limits.get_limit_enforcer().reset_counters()
    spec._base = str(harness_dir)
    spec.game_manager = GameManager(str(harness_dir))
    spec._controller = None
    spec._game_service = None

    client = TestClient(app)
    yield client, harness_dir
    api_limits.get_limit_enforcer().reset_counters()
    spec._game_service = None
    spec._controller = None
    if spec._engine is not None:
        spec._engine.quit()
        spec._engine = None
    if hasattr(spec._get_controller(), "opponent_mgr"):
        spec._get_controller().opponent_mgr.release()


def test_packed_resign_unrated_no_elo_no_sqlite(tmp_path, monkeypatch):
    harness_dir = _harness_setup(tmp_path, monkeypatch)
    game_id = "packed-resign"
    elo_before = _registry(harness_dir).get_elo("composer-2.5")

    assert commands.cmd_new(
        game_id,
        "white",
        None,
        model_name="composer-2.5",
        force=True,
        opponent="random",
        prompt_pack="a",
    )["ok"]

    gm = GameManager(str(harness_dir))
    ctrl = BoardController(gm)
    scheduled: list[str] = []

    with patch(
        "chess_harness.board_controller.schedule_game_quality",
        side_effect=lambda gid, **kw: scheduled.append(gid),
    ):
        out = ctrl.resign(game_id)

    assert out["ok"] is True
    row = _last_result(harness_dir)
    assert row["prompt_pack"] == "a"
    assert row["rated"] is False
    assert _registry(harness_dir).get_elo("composer-2.5") == elo_before
    assert get_finished_game(game_id, db_path=resolve_finished_games_db()) is None
    assert scheduled == [game_id]


def test_untagged_resign_rates_and_sqlite_writes(tmp_path, monkeypatch):
    harness_dir = _harness_setup(tmp_path, monkeypatch)
    game_id = "untagged-resign"
    elo_before = _registry(harness_dir).get_elo("composer-2.5")

    assert commands.cmd_new(
        game_id,
        "white",
        None,
        model_name="composer-2.5",
        force=True,
        opponent="random",
    )["ok"]

    gm = GameManager(str(harness_dir))
    ctrl = BoardController(gm)
    out = ctrl.resign(game_id)

    assert out["ok"] is True
    row = _last_result(harness_dir)
    assert "prompt_pack" not in row
    assert row.get("rated") is not False
    assert _registry(harness_dir).get_elo("composer-2.5") != elo_before
    assert get_finished_game(game_id, db_path=resolve_finished_games_db()) is not None


def test_aggregators_skip_packed_rows(tmp_path, monkeypatch):
    harness_dir = _harness_setup(tmp_path, monkeypatch)
    shutil.copy(FIXTURES / "models.json", harness_dir / "models.json")
    rm = ResultsManager(base_dir=str(harness_dir))
    rows = [
        {
            "game_id": "rated-1",
            "model_name": "composer-2.5",
            "result": "1-0",
            "accuracy": 80.0,
            "play_rating": 1200.0,
        },
        {
            "game_id": "packed-1",
            "model_name": "composer-2.5",
            "result": "0-1",
            "prompt_pack": "b",
            "rated": False,
            "accuracy": 90.0,
            "play_rating": 1300.0,
        },
    ]
    for row in rows:
        rm.append_result(row)

    scored = rm.count_scored_by_model()
    quality = rm.aggregate_quality_by_model()

    assert scored["composer-2.5"] == 1
    assert quality["composer-2.5"]["quality_games"] == 1
    assert quality["composer-2.5"]["mean_accuracy"] == 80.0


def test_spectator_loopback_sees_packed_game(privacy_client):
    client, harness_dir = privacy_client
    game_id = "packed-loopback"
    assert commands.cmd_new(
        game_id,
        "white",
        None,
        model_name="composer-2.5",
        force=True,
        opponent="random",
        prompt_pack="c",
    )["ok"]

    headers = {"Host": "127.0.0.1"}
    listed = client.get("/api/games", headers=headers).json()
    ids = {g["game_id"] for g in listed["games"]}
    assert game_id in ids

    assert client.get(f"/api/games/{game_id}/state", headers=headers).status_code == 200
    assert client.get(f"/g/{game_id}/board.png", headers=headers).status_code == 200


def test_spectator_public_hides_packed_game(privacy_client):
    client, _harness_dir = privacy_client
    game_id = "packed-public"
    assert commands.cmd_new(
        game_id,
        "white",
        None,
        model_name="composer-2.5",
        force=True,
        opponent="random",
        prompt_pack="d",
    )["ok"]

    headers = {"Host": "example.com"}
    listed = client.get("/api/games", headers=headers).json()
    ids = {g["game_id"] for g in listed["games"]}
    assert game_id not in ids

    assert client.get(f"/api/games/{game_id}/state", headers=headers).status_code == 404
    assert client.get(f"/g/{game_id}/board.png", headers=headers).status_code == 404
    assert client.get(f"/g/{game_id}", headers=headers).status_code == 404
