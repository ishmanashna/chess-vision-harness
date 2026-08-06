"""Tests for the Phase 9 puzzle and board-identification leaderboards."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from chess_harness.identify_attempt import IdentifyAttemptStore
from chess_harness.models import ModelRegistry
from chess_harness.puzzle_attempt import PuzzleAttemptStore
from chess_harness.puzzle_leaderboard import build_identify_leaderboard, build_puzzle_leaderboard
from chess_harness.puzzle_ratings import PuzzleRatingStore
from chess_harness.puzzle_store import PuzzleStore

ROOT = Path(__file__).resolve().parents[2]

M = {"agent-a": {"id": "agent-a", "name": "Agent A", "elo": 700.0},
     "agent-b": {"id": "agent-b", "name": "Agent B", "elo": 680.0}}


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _registry(tmp_path: Path, models=None) -> ModelRegistry:
    _write(tmp_path / "models.json", {"models": models or list(M.values())})
    return ModelRegistry(tmp_path / "models.json")


def _attempts(**rows) -> dict:
    return {"version": 1, "attempts": rows}


def test_puzzle_leaderboard_agent_stats_and_sort(tmp_path):
    _write(tmp_path / "ratings.json", {"version": 1, "puzzles": {},
           "agents": {"agent-a": {"rating": 1650.0, "deviation": 80.0, "games": 5, "solves": 3}}})
    a = {"status": "finished", "puzzle_id": "pz-1", "model_id": "agent-a"}
    _write(tmp_path / "attempts.json", _attempts(
        p1={**a, "attempt_id": "p1", "result": "correct", "started_at": "2026-08-01T10:00:00+00:00"},
        p2={**a, "attempt_id": "p2", "result": "correct", "started_at": "2026-08-01T11:00:00+00:00"},
        p3={**a, "attempt_id": "p3", "result": "failed", "started_at": "2026-08-01T12:00:00+00:00"},
        p4={**a, "attempt_id": "p4", "result": None, "status": "abandoned",
            "started_at": "2026-08-01T13:00:00+00:00"},
        p5={"model_id": "agent-b", "attempt_id": "p5", "puzzle_id": "pz-1",
            "status": "finished", "result": "failed", "started_at": "2026-08-01T14:00:00+00:00"},
    ))
    board = build_puzzle_leaderboard(
        ratings=PuzzleRatingStore(tmp_path / "ratings.json"),
        attempts=PuzzleAttemptStore(tmp_path / "attempts.json"),
        puzzles=PuzzleStore(tmp_path / "dataset.json", tmp_path / "manifest.json"),
        registry=_registry(tmp_path))
    assert board["version"] == 1 and isinstance(board["generated_at"], str)
    by_id = {a["id"]: a for a in board["agents"]}
    aa = by_id["agent-a"]
    assert (aa["rating"], aa["deviation"]) == (1650.0, 80.0)
    assert aa["attempts"] == 3 and aa["solves"] == 2
    assert aa["solve_rate"] == pytest.approx(0.6667, abs=1e-4)
    ab = by_id["agent-b"]
    assert ab["rating"] is None and ab["attempts"] == 1 and ab["solves"] == 0
    assert [a["id"] for a in board["agents"]] == ["agent-a", "agent-b"]


def test_puzzle_content_rows_use_frozen_import_difficulty(tmp_path):
    _write(tmp_path / "dataset.json", {"version": 1, "puzzles": {"pz-1": {
        "puzzle_id": "pz-1", "rating": 1500, "rating_deviation": 120, "popularity": 88,
        "nb_plays": 12345, "themes": ["mateIn2", "sacrifice"], "game_url": "https://lichess.org/abc"}}})
    # Legacy runtime records (if any) are ignored: import estimate wins.
    _write(tmp_path / "ratings.json", {"version": 1, "agents": {},
           "puzzles": {"pz-1": {"rating": 1400.0, "deviation": 90.0, "games": 3, "solves": 1}}})
    _write(tmp_path / "attempts.json", _attempts(
        old={"attempt_id": "pz-old", "model_id": "agent-a", "puzzle_id": "pz-1",
             "status": "finished", "result": "correct", "started_at": "2026-08-01T10:00:00+00:00"},
        new={"attempt_id": "pz-new", "model_id": "agent-b", "puzzle_id": "pz-1",
             "status": "finished", "result": "failed", "started_at": "2026-08-02T10:00:00+00:00"},
    ))
    board = build_puzzle_leaderboard(
        ratings=PuzzleRatingStore(tmp_path / "ratings.json"),
        attempts=PuzzleAttemptStore(tmp_path / "attempts.json"),
        puzzles=PuzzleStore(tmp_path / "dataset.json", tmp_path / "manifest.json"),
        registry=_registry(tmp_path))
    (row,) = board["puzzles"]
    assert row["id"] == "pz-1" and row["rating"] == 1500.0 and row["deviation"] == 120.0
    assert row["attempts"] == 2 and row["solves"] == 1 and row["solve_rate"] == 0.5
    assert row["themes"] == ["mateIn2", "sacrifice"]
    assert row["popularity"] == 88 and row["nb_plays"] == 12345
    assert row["source"] == "https://lichess.org/abc"
    assert row["watch_url"] == "/p/pz-new"


def test_identify_leaderboard_stats(tmp_path):
    _write(tmp_path / "identify.json", {"version": 1, "attempts": {
        "bi-1": {"attempt_id": "bi-1", "model_id": "agent-a", "status": "finished",
                 "result": "correct", "score": {"accuracy": 1.0, "full_position": True}},
        "bi-2": {"attempt_id": "bi-2", "model_id": "agent-a", "status": "finished",
                 "result": "failed", "score": {"accuracy": 0.5, "full_position": False}},
        "bi-3": {"attempt_id": "bi-3", "model_id": "agent-a", "status": "abandoned",
                 "result": None, "score": None},
    }})
    board = build_identify_leaderboard(
        attempts=IdentifyAttemptStore(tmp_path / "identify.json"), registry=_registry(tmp_path))
    (row,) = board["agents"]
    assert row["id"] == "agent-a" and row["name"] == "Agent A" and row["attempts"] == 2
    assert row["mean_accuracy"] == pytest.approx(0.75, abs=1e-4)
    assert row["full_position_rate"] == pytest.approx(0.5, abs=1e-4)


def test_identify_leaderboard_empty(tmp_path):
    board = build_identify_leaderboard(attempts=IdentifyAttemptStore(tmp_path / "empty.json"))
    assert board["agents"] == []


def test_export_public_snapshots_writes_three_files(tmp_path, monkeypatch):
    harness = tmp_path / "harness"
    harness.mkdir()
    _write(harness / "models.json", {"models": [{"id": "solo", "name": "Solo", "elo": 650.0}]})
    monkeypatch.setenv("CHESS_HARNESS_DIR", str(harness))
    from chess_harness.snapshot_leaderboard import export_public_snapshots
    out = tmp_path / "out"
    written = export_public_snapshots(
        output_path=out / "leaderboard.json", puzzle_path=out / "puzzles_leaderboard.json",
        identify_path=out / "identify_leaderboard.json", registry=ModelRegistry(harness / "models.json"))
    assert [p.name for p in written.values()] == [
        "leaderboard.json", "puzzles_leaderboard.json", "identify_leaderboard.json"]
    ladder = json.loads(written["leaderboard"].read_text(encoding="utf-8"))
    assert ladder["agents"][0]["id"] == "solo"
    for key in ("puzzles", "identify"):
        data = json.loads(written[key].read_text(encoding="utf-8"))
        assert data["agents"] == [] and isinstance(data["generated_at"], str)
    puzzles = json.loads(written["puzzles"].read_text(encoding="utf-8"))
    assert puzzles["puzzles"] == []
    assert json.loads(written["identify"].read_text(encoding="utf-8"))["agents"] == []


def test_live_puzzle_and_identify_leaderboards(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from conftest import FIXTURES
    from chess_harness.game_manager import GameManager

    harness_dir = tmp_path / "harness"
    harness_dir.mkdir()
    shutil.copy(FIXTURES / "models.json", harness_dir / "models.json")
    monkeypatch.setenv("CHESS_HARNESS_DIR", str(harness_dir))
    monkeypatch.setenv("MODELS_FILE", str(harness_dir / "models.json"))
    import chess_harness.spectator as spec
    spec._base = str(harness_dir)
    spec.game_manager = GameManager(str(harness_dir))
    spec._controller = None
    spec._game_service = None
    client = TestClient(spec.app)
    try:
        for path in ("/api/leaderboard/puzzles/live", "/api/leaderboard/identify/live",
                     "/data/puzzles_leaderboard.json", "/data/identify_leaderboard.json"):
            resp = client.get(path)
            assert resp.status_code == 200
            assert resp.headers.get("cache-control") == "no-store"
            data = resp.json()
            assert isinstance(data.get("agents"), list)
            assert isinstance(data.get("generated_at"), str)
        assert isinstance(client.get("/api/leaderboard/puzzles/live").json().get("puzzles"), list)
        for path in ("/puzzles", "/puzzles/"):
            resp = client.get(path)
            assert resp.status_code == 200
            assert "puzzle-launcher" in resp.text
    finally:
        spec._game_service = None
        spec._controller = None
        if spec._engine is not None:
            spec._engine.quit()
            spec._engine = None


def test_puzzles_launcher_page_has_tabs_and_scripts():
    text = (ROOT / "public-site" / "puzzles" / "index.html").read_text(encoding="utf-8")
    for needle in ('data-launcher-tab="puzzles"', 'data-launcher-tab="identify"',
                   "data-launcher-form", "data-launcher-result",
                   "/js/puzzle-launcher.js", 'id="launcher-model-select"',
                   'id="nav-puzzles"'):
        assert needle in text
    js = (ROOT / "public-site" / "js" / "puzzle-launcher.js").read_text(encoding="utf-8")
    assert "/api/v1/puzzles/start" in js
    assert "/api/v1/identify/start" in js
    assert '"/p/" + attemptId' in js
    assert '"/i/" + attemptId' in js


def test_all_headers_have_puzzles_nav():
    for rel in ("index.html", "create/index.html", "spectator/index.html",
                "leaderboard/index.html", "human/index.html", "contact/index.html",
                "puzzles/index.html"):
        text = (ROOT / "public-site" / rel).read_text(encoding="utf-8")
        assert 'id="nav-puzzles"' in text, rel
    header = (ROOT / "python" / "src" / "chess_harness" / "ladder_display.py").read_text(encoding="utf-8")
    assert 'id="nav-puzzles"' in header


def test_proxy_allows_puzzle_leaderboard_paths():
    text = (ROOT / "public-site" / "functions" / "_proxy.js").read_text(encoding="utf-8")
    assert "/api/leaderboard/puzzles/live" in text
    assert "/api/leaderboard/identify/live" in text
    assert 'startsWith("/p/")' in text
    assert 'startsWith("/i/")' in text


def test_leaderboard_page_has_tabs_and_scripts():
    text = (ROOT / "public-site" / "leaderboard" / "index.html").read_text(encoding="utf-8")
    for needle in ('data-lb-tab="agents"', 'data-lb-tab="puzzles"', 'data-lb-tab="identify"',
                   'data-lb-panel="puzzles"', 'data-lb-panel="identify"',
                   "/js/puzzle-leaderboards.js", "data-puzzle-leaderboard",
                   "data-puzzle-content-leaderboard", "data-identify-leaderboard"):
        assert needle in text
    # Phase C: identify columns relabeled to percentage-of-correct copy.
    assert "% pieces correct" in text
    assert "% boards correct" in text
    # Phase B: puzzle difficulty copy states it is frozen at the import estimate.
    assert "imported Lichess estimate and never changes" in text