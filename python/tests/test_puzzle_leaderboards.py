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
    assert "themes" not in row, "themes never leave the puzzle records"
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
    assert row["full"] == 1
    assert row["mean_accuracy"] == pytest.approx(0.75, abs=1e-4)
    assert row["full_position_rate"] == pytest.approx(0.5, abs=1e-4)


def test_identify_leaderboard_empty(tmp_path):
    board = build_identify_leaderboard(attempts=IdentifyAttemptStore(tmp_path / "empty.json"))
    assert board["agents"] == []


def test_export_public_snapshots_writes_two_files(tmp_path, monkeypatch):
    harness = tmp_path / "harness"
    harness.mkdir()
    _write(harness / "models.json", {"models": [{"id": "solo", "name": "Solo", "elo": 650.0}]})
    monkeypatch.setenv("CHESS_HARNESS_DIR", str(harness))
    from chess_harness.snapshot_leaderboard import export_public_snapshots
    out = tmp_path / "out"
    written = export_public_snapshots(
        output_path=out / "leaderboard.json", puzzle_path=out / "puzzles_leaderboard.json",
        registry=ModelRegistry(harness / "models.json"))
    assert [p.name for p in written.values()] == [
        "leaderboard.json", "puzzles_leaderboard.json", "identify_leaderboard.json"]
    ladder = json.loads(written["leaderboard"].read_text(encoding="utf-8"))
    assert ladder["agents"][0]["id"] == "solo"
    puzzles = json.loads(written["puzzles"].read_text(encoding="utf-8"))
    assert puzzles["agents"] == []
    assert puzzles["puzzles"] == []
    assert "identify_leaderboard.json" in [p.name for p in out.iterdir()]


def test_live_puzzle_leaderboard_and_legacy_redirects(tmp_path, monkeypatch):
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
        for path in ("/api/leaderboard/puzzles/live", "/data/puzzles_leaderboard.json"):
            resp = client.get(path)
            assert resp.status_code == 200
            assert resp.headers.get("cache-control") == "public, max-age=5"
            data = resp.json()
            assert isinstance(data.get("agents"), list)
            assert isinstance(data.get("generated_at"), str)
        assert isinstance(client.get("/api/leaderboard/puzzles/live").json().get("puzzles"), list)
        for path, location in (("/puzzles", "/launch/?flow=puzzles"), ("/puzzles/", "/launch/?flow=puzzles")):
            resp = client.get(path, follow_redirects=False)
            assert resp.status_code == 301
            assert resp.headers["location"] == location
        for path in ("/api/leaderboard/identify/live", "/data/identify_leaderboard.json"):
            resp = client.get(path)
            assert resp.status_code == 200
            assert resp.headers.get("cache-control") == "public, max-age=5"
            data = resp.json()
            assert isinstance(data.get("agents"), list)
            assert isinstance(data.get("generated_at"), str)
    finally:
        spec._game_service = None
        spec._controller = None
        if spec._engine is not None:
            spec._engine.quit()
            spec._engine = None


def test_puzzles_launcher_page_deleted_launch_is_dropdown():
    text = (ROOT / "public-site" / "launch" / "index.html").read_text(encoding="utf-8")
    for needle in ('data-launch-mode', '<option value="engine">Agent vs Engine</option>',
                   '<option value="avaa">Agent vs Agent</option>',
                   '<option value="playground">Playground</option>',
                   '<option value="puzzles">Puzzles</option>',
                   '<option value="identify">Board identification</option>',
                   "Select your model", "Display name"):
        assert needle in text, needle
    assert "data-launch-flow" not in text
    assert "launcher-model-select" not in text
    assert not (ROOT / "public-site" / "puzzles" / "index.html").exists()
    js = (ROOT / "public-site" / "js" / "launcher.js").read_text(encoding="utf-8")
    assert "/api/v1/puzzles/start" in js
    assert "/api/v1/identify/start" in js
    assert '"/p/" + attemptId' in js
    assert '"/i/" + attemptId' in js


def test_launch_page_has_five_flows_and_scripts():
    text = (ROOT / "public-site" / "launch" / "index.html").read_text(encoding="utf-8")
    for flow in ("engine", "avaa", "playground", "puzzles", "identify"):
        assert '<option value="%s">' % flow in text
    for needle in ('data-launch-page', "data-create-form", "data-create-result",
                   "data-inscribe-submit", "/js/launcher.js", "/js/create-result.js",
                   "/js/create-match.js", "/js/create-human-wait.js"):
        assert needle in text, needle
    js = (ROOT / "public-site" / "js" / "launcher.js").read_text(encoding="utf-8")
    for needle in ('"/api/v1/games"', '"/api/v1/games/human"',
                   '"/api/v1/games/agent-vs-agent"', '"/api/v1/puzzles/start"',
                   '"/api/v1/identify/start"', '"/api/v1/agents"'):
        assert needle in js, needle


def test_all_headers_have_single_launcher_nav():
    for rel in ("index.html", "spectator/index.html", "leaderboard/index.html",
                "contact/index.html", "launch/index.html"):
        text = (ROOT / "public-site" / rel).read_text(encoding="utf-8")
        assert 'id="nav-create"' in text, rel
        assert 'id="nav-puzzles"' not in text, rel
        assert 'id="nav-human"' not in text, rel
    header = (ROOT / "python" / "src" / "chess_harness" / "ladder_display.py").read_text(encoding="utf-8")
    assert 'id="nav-create"' in header
    assert 'id="nav-puzzles"' not in header
    assert 'id="nav-human"' not in header


def test_no_orientation_sublabel_in_observer_pages():
    """Phase 7: 'white at bottom' and 'a1 bottom-left' removed from observer HTML."""
    for rel in ("p/index.html", "i/index.html"):
        text = (ROOT / "public-site" / rel).read_text(encoding="utf-8")
        assert "white at bottom" not in text.lower(), f"{rel} still has orientation sub-label"
        assert "a1 bottom-left" not in text.lower(), f"{rel} still has orientation sub-label"


def test_proxy_allows_puzzle_leaderboard_paths():
    import json

    contract_path = ROOT / "public-site" / "functions" / "proxy-routes.contract.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    exact = contract["proxy_path_exact"]
    watch_assets = contract["watch_asset_path_prefixes"]
    assert "/api/leaderboard/puzzles/live" in exact
    assert "/api/leaderboard/identify/live" in exact
    assert "/p/" in watch_assets
    assert "/i/" in watch_assets
    middleware = (ROOT / "public-site" / "functions" / "_middleware.js").read_text(encoding="utf-8")
    assert "isCalibrationPath" in middleware
    assert "isWatchShellHtml" in middleware


def test_pages_middleware_unknown_api_returns_json_404():
    text = (ROOT / "public-site" / "functions" / "_middleware.js").read_text(encoding="utf-8")
    assert 'pathname.startsWith("/api/")' in text
    assert "/api/edge-health" in text
    assert 'application/json' in text
    assert 'error: "Not Found"' in text
    assert "isCalibrationPath" in text
    assert 'text/plain' not in text
    assert "/identify" in text
    assert "flow=identify" in text
    assert "flow=playground" in text


def test_puzzle_watch_joins_performance_by_model_id():
    text = (ROOT / "public-site" / "js" / "puzzle-watch.js").read_text(encoding="utf-8")
    assert "state.model_id" in text
    assert "agents.find((a) => a.id === modelId)" in text
    assert "mean_play_rating" in text


def test_leaderboard_page_is_unified_no_tabs():
    text = (ROOT / "public-site" / "leaderboard" / "index.html").read_text(encoding="utf-8")
    for needle in ('data-show-unified-stats', "PUZZLES", "% pieces",
                   "% boards", "data-engines-leaderboard",
                   "data-sort=\"puzzle_rating\"", "data-sort=\"identify_mean_accuracy\"",
                   'data-sort="puzzle_solve_ratio"'):
        assert needle in text, needle
    assert "Pz att" not in text
    assert "Pz sol" not in text
    assert "Id att" not in text
    assert 'data-sort="puzzle_solve_rate"' not in text, "legacy solve-rate key removed"
    assert "<th scope=\"col\">Themes</th>" not in text, "theme column removed"
    assert "data-puzzle-content-leaderboard" not in text, "puzzle content section removed"
    assert "Solve rate" not in text, "puzzle content section removed"
    assert "data-lb-tab" not in text
    assert "data-lb-panel" not in text
    assert "data-puzzle-leaderboard" not in text
    assert "data-identify-leaderboard" not in text
    assert "?tab=" not in text
    assert "white at bottom" not in text.lower(), "orientation sub-label removed"
    assert "a1 bottom-left" not in text.lower(), "orientation sub-label removed"
    common = (ROOT / "public-site" / "js" / "common.js").read_text(encoding="utf-8")
    assert "data-show-unified-stats" in common
    assert "puzzle_solve_rate" not in common
    assert "puzzle_solve_ratio" in common
    assert "formatPuzzleRatio" in common
    assert "identify_full_position_rate" in common
    css = (ROOT / "public-site" / "css" / "site.css").read_text(encoding="utf-8")
    assert ".leaderboard-table .elo" in css
    assert ".leaderboard-table .accuracy" not in css, "accuracy cell is a plain td like other metrics"