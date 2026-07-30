"""Spectator list enrichment: game_type and finished AvE Elo."""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from conftest import FIXTURES, LOW_OPPONENT

from chess_harness.game_manager import GameManager
from chess_harness.game_service import GameService
from chess_harness.game_types import DEFAULT_GAME_TYPE, GAME_TYPE_AGENT_VS_AGENT
from chess_harness.limits import HarnessLimits
from chess_harness.models import ModelRegistry
from chess_harness.spectator import _enrich_list_game, app

REPO_ROOT = Path(__file__).resolve().parents[2]
PUBLIC_SITE = REPO_ROOT / "public-site"


@pytest.fixture
def list_client(tmp_path, monkeypatch):
    harness_dir = tmp_path / "harness"
    harness_dir.mkdir()
    shutil.copy(FIXTURES / "models.json", harness_dir / "models.json")
    monkeypatch.setenv("CHESS_HARNESS_DIR", str(harness_dir))
    monkeypatch.setenv("MODELS_FILE", str(harness_dir / "models.json"))

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
    try:
        spec._get_controller().opponent_mgr.release()
    except Exception:
        pass


def test_enrich_list_game_defaults_game_type():
    row = _enrich_list_game(
        {
            "game_id": "legacy-ave",
            "state": {
                "status": "in_progress",
                "agent_color": "WHITE",
                "model_name": "composer-2.5",
                "board_fen": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
                "moves": [],
                "pgn_headers": {},
            },
        }
    )
    assert row["game_type"] == DEFAULT_GAME_TYPE
    assert row["white_display_name"] == "composer-2.5"
    assert row["black_display_name"]
    assert row["white_elo"] is not None
    assert "(" not in row["black_display_name"]


def test_enrich_list_game_strips_elo_suffix_from_names():
    row = _enrich_list_game(
        {
            "game_id": "suffix-ave",
            "state": {
                "status": "in_progress",
                "agent_color": "BLACK",
                "model_name": "composer-2.5",
                "opponent_label": "MiMo V2.5 Black (418)",
                "board_fen": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
                "moves": [],
                "pgn_headers": {},
            },
        }
    )
    assert row["white_display_name"] == "MiMo V2.5 Black"
    assert row["black_display_name"] == "composer-2.5"
    assert "(418)" not in row["white_display_name"]


def test_enrich_list_game_includes_quality_fields():
    row = _enrich_list_game(
        {
            "game_id": "quality-avaa",
            "state": {
                "status": "in_progress",
                "game_type": GAME_TYPE_AGENT_VS_AGENT,
                "white_display_name": "Alpha",
                "black_display_name": "Beta",
                "white_model_id": "a",
                "black_model_id": "b",
                "agent_color": "WHITE",
                "board_fen": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
                "moves": [],
                "white_accuracy": 91.2,
                "black_accuracy": 88.4,
                "white_play_rating": 1523.7,
                "black_play_rating": 1498.2,
                "quality_at": "2026-07-30T12:00:00Z",
            },
        }
    )
    assert row["white_accuracy"] == 91.2
    assert row["black_accuracy"] == 88.4
    assert row["white_play_rating"] == 1523.7
    assert row["black_play_rating"] == 1498.2
    assert row["quality_at"] == "2026-07-30T12:00:00Z"


def test_spectator_page_modern_column_headers(list_client):
    client, _ = list_client
    html = client.get("/spectator/").text
    for label in (
        "White Elo",
        "Black Elo",
        "Acc.",
        "Est. Elo",
        "Turn / result",
    ):
        assert label in html
    assert 'data-sort="whiteElo"' in html
    assert 'data-sort="blackElo"' in html
    assert 'data-sort="accuracy"' in html
    assert 'data-sort="estimatedElo"' in html
    assert 'class="col-side"' in html
    assert 'class="col-quality"' in html
    assert 'class="col-est-elo"' in html
    assert ">Agent</th>" not in html
    assert ">Opponent</th>" not in html
    assert html.count('colspan="10"') >= 2


def test_games_list_js_modern_columns():
    js = (PUBLIC_SITE / "js" / "games-list.js").read_text(encoding="utf-8")
    assert "white_display_name" in js
    assert "whiteElo" in js
    assert "blackElo" in js
    assert "qualityPair" in js
    assert "nameWithoutElo" in js
    assert "colspan=\"10\"" in js
    assert "agent_name" not in js


def test_spectator_list_ave_finished_agent_elo(list_client):
    client, harness_dir = list_client
    registry = ModelRegistry(harness_dir / "models.json")
    start_elo = round(registry.get_elo("composer-2.5"))
    svc = GameService(GameManager(str(harness_dir)))

    created = svc.new_game(
        "ave-finished",
        "white",
        opponent_id=LOW_OPPONENT,
        model_name="composer-2.5",
    )
    assert created.get("ok") is True, created

    resigned = svc.resign("ave-finished")
    assert resigned["ok"] is True

    listed = client.get("/api/games?status=finished")
    assert listed.status_code == 200
    row = next(g for g in listed.json()["games"] if g["game_id"] == "ave-finished")
    assert row["game_type"] == DEFAULT_GAME_TYPE
    assert row["white_display_name"]
    assert row["black_display_name"]
    assert row["white_elo"] is not None
    assert row["black_elo"] is not None
    assert not re.search(r"\(\d+\)$", row["black_display_name"])
    assert row["agent_elo"] is not None
    assert row["agent_elo"] != start_elo
    assert row["elo_change"]
    assert str(row["agent_elo"]) in row["elo_change"]


def test_spectator_list_ave_idle_timeout_unranked(list_client, monkeypatch):
    client, harness_dir = list_client
    monkeypatch.setattr(
        "chess_harness.board_controller.load_limits",
        lambda: HarnessLimits(idle_timeout_sec=0),
    )
    svc = GameService(GameManager(str(harness_dir)))
    created = svc.new_game(
        "ave-idle",
        "white",
        opponent_id=LOW_OPPONENT,
        model_name="composer-2.5",
    )
    assert created.get("ok") is True, created

    svc.prune_idle_games()

    listed = client.get("/api/games?status=finished")
    assert listed.status_code == 200
    row = next(g for g in listed.json()["games"] if g["game_id"] == "ave-idle")
    assert row["game_type"] == DEFAULT_GAME_TYPE
    assert row.get("agent_elo") is None
    assert row.get("elo_change") in ("", None)
    assert row.get("result") == "*"
    assert row.get("turn") != "*"
    assert "No result" in str(row.get("turn") or row.get("end_reason_label") or "")


def test_spectator_list_avaa_white_black_columns(list_client):
    client, harness_dir = list_client
    white = client.post("/api/v1/agents", json={"id": "list-white", "name": "White Agent"})
    black = client.post("/api/v1/agents", json={"id": "list-black", "name": "Black Agent"})
    white_key = white.json()["api_key"]
    create = client.post(
        "/api/v1/games/agent-vs-agent",
        headers={"Authorization": f"Bearer {white_key}"},
        json={"white_model_id": "list-white", "black_model_id": "list-black"},
    )
    assert create.status_code == 200
    game_id = create.json()["game_id"]

    listed = client.get("/api/games?status=in_progress")
    row = next(g for g in listed.json()["games"] if g["game_id"] == game_id)
    assert row["game_type"] == GAME_TYPE_AGENT_VS_AGENT
    assert row["white_display_name"] == "White Agent"
    assert row["black_display_name"] == "Black Agent"
    assert row["white_elo"] is not None
    assert row["black_elo"] is not None
    assert row["agent_elo"] == row["white_elo"]
