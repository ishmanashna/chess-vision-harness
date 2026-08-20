"""Tests for P8: Glicko-2 puzzle ratings and attempt persistence.

Covers the pure math (win/loss direction, deviation decay, reproducibility),
the persistent store (agent wins vs puzzle wins, abandon = no rating,
runtime puzzle difficulty, idempotency), the API integration (attempt move
stamps rating fields, review exposes them), and the non-regression rule that
game Elo / ``models.json`` is untouched.
"""

from __future__ import annotations

import json
import shutil
from typing import Any, Dict, List

import pytest
from fastapi.testclient import TestClient

from conftest import FIXTURES

from chess_harness.game_manager import GameManager
from chess_harness.glicko2 import DEFAULT_RATING, GlickoRating, update_rating
from chess_harness.puzzle_import import PuzzleImporter
from chess_harness.puzzle_ratings import AGENT_START_RATING, PuzzleRatingStore
from chess_harness.puzzle_store import PuzzleStore


def _row(
    puzzle_id: str,
    moves: List[str],
    rating: int = 1500,
    deviation: int = 75,
    themes: str = "opening",
    game_url: str = "https://lichess.org/x",
) -> Dict[str, str]:
    import chess

    return {
        "PuzzleId": puzzle_id,
        "FEN": chess.STARTING_FEN,
        "Moves": " ".join(moves),
        "Rating": str(rating),
        "RatingDeviation": str(deviation),
        "Popularity": "90",
        "NbPlays": "5000",
        "Themes": themes,
        "GameUrl": game_url,
        "OpeningTags": "test",
        "DailyDate": "2024-01-01",
    }


def _import(harness_dir) -> None:
    PuzzleImporter().import_rows(
        [
            _row(
                "pz-a",
                ["e2e4", "e7e5", "g1f3", "g8f6", "f1c4"],
                rating=1500,
                game_url="https://lichess.org/a",
            ),
            _row(
                "pz-b",
                ["d2d4", "d7d5", "c2c4"],
                rating=1200,
                game_url="https://lichess.org/b",
            ),
            _row(
                "pz-c",
                ["c2c4", "e7e5", "g1f3"],
                rating=2000,
                themes="mateIn2",
                game_url="https://lichess.org/c",
            ),
        ]
    )


@pytest.fixture
def p8_client(tmp_path, monkeypatch):
    harness_dir = tmp_path / "harness"
    harness_dir.mkdir()
    shutil.copy(FIXTURES / "models.json", harness_dir / "models.json")
    monkeypatch.setenv("CHESS_HARNESS_DIR", str(harness_dir))
    monkeypatch.setenv("MODELS_FILE", str(harness_dir / "models.json"))
    _import(harness_dir)

    import chess_harness.api_limits as api_limits
    import chess_harness.spectator as spec

    api_limits.get_limit_enforcer().reset_counters()
    spec._base = str(harness_dir)
    spec.game_manager = GameManager(str(harness_dir))
    spec._controller = None
    spec._game_service = None

    from chess_harness.spectator import app as spectator_app

    client = TestClient(spectator_app)
    yield client, harness_dir
    api_limits.get_limit_enforcer().reset_counters()
    spec._game_service = None
    spec._controller = None
    if spec._engine is not None:
        spec._engine.quit()
        spec._engine = None
    if hasattr(spec._get_controller(), "opponent_mgr"):
        spec._get_controller().opponent_mgr.release()


def _auth(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}"}


def _register(client: TestClient, agent_id: str) -> str:
    resp = client.post("/api/v1/agents", json={"id": agent_id, "name": agent_id})
    assert resp.status_code == 200
    return resp.json()["api_key"]


def _start(client: TestClient, api_key: str, **params) -> Dict[str, Any]:
    resp = client.post(
        "/api/v1/puzzles/start", headers=_auth(api_key), params=params or None
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _solve(client: TestClient, api_key: str, attempt_id: str) -> Dict[str, Any]:
    # pz-a solution after setup: e7e5 g1f3 g8f6 f1c4 (agent moves only).
    for move, expect_finished in [("e7e5", False), ("g8f6", True)]:
        resp = client.post(
            f"/api/v1/puzzles/{attempt_id}/move/{move}", headers=_auth(api_key)
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        if expect_finished:
            assert data["status"] == "finished"
            assert data["result"] == "correct"
            return data
    raise AssertionError("solve did not finish")


def _failed(client: TestClient, api_key: str, attempt_id: str) -> Dict[str, Any]:
    resp = client.post(
        f"/api/v1/puzzles/{attempt_id}/move/a7a6", headers=_auth(api_key)
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["result"] == "failed"
    return resp.json()


# ---------------------------------------------------------------------------
# Glicko-2 math
# ---------------------------------------------------------------------------


def test_glicko2_win_loss_direction_and_deviation():
    player = GlickoRating()
    puzzle = GlickoRating(1500, 100, 0.06)

    win = update_rating(player, puzzle.rating, puzzle.deviation, 1.0)
    loss = update_rating(player, puzzle.rating, puzzle.deviation, 0.0)

    assert win.rating > player.rating > loss.rating
    assert win.deviation < player.deviation
    assert loss.deviation < player.deviation
    assert 0.0 < win.volatility <= 0.1
    assert DEFAULT_RATING == 1500.0


def test_glicko2_reproducible_and_converging():
    puzzle = GlickoRating(1800, 80, 0.06)
    a = GlickoRating()
    b = GlickoRating()

    seq = [update_rating(a, puzzle.rating, puzzle.deviation, 1.0)]
    for _ in range(3):
        seq.append(
            update_rating(seq[-1], puzzle.rating, puzzle.deviation, 1.0)
        )

    for i in range(4):
        v = update_rating(b, puzzle.rating, puzzle.deviation, 1.0)
        assert v.rating == pytest.approx(seq[i].rating, abs=0.01)
        assert v.deviation == pytest.approx(seq[i].deviation, abs=0.01)
        b = v

    assert seq[-1].deviation < seq[0].deviation


def test_glicko2_strong_player_small_gain():
    weak = GlickoRating(1200, 80)
    strong = GlickoRating(2500, 90)
    # Beating a much weaker puzzle moves a top player very little.
    result = update_rating(strong, weak.rating, weak.deviation, 1.0)
    assert result.rating < strong.rating + 20


# ---------------------------------------------------------------------------
# Store semantics
# ---------------------------------------------------------------------------


def _attempt_record(
    harness_dir,
    model_id: str,
    puzzle_id: str,
    result: str,
    status: str = "finished",
) -> Dict[str, Any]:
    import chess

    return {
        "attempt_id": "pz-test",
        "model_id": model_id,
        "puzzle_id": puzzle_id,
        "status": status,
        "result": result,
        "puzzle_rating": PuzzleStore().get(puzzle_id)["rating"],
        "rating_after": None,
        "started_at": "2024-01-01T00:00:00+00:00",
        "finished_at": "2024-01-01T00:01:00+00:00",
    }


def test_new_agent_starts_at_easy_floor(p8_client):
    store = PuzzleRatingStore()
    agent = store.agent_rating("fresh-agent")
    assert agent["rating"] == AGENT_START_RATING
    assert agent["deviation"] == 350.0


def test_store_agent_win_moves_agent_only(p8_client):
    _, harness_dir = p8_client
    store = PuzzleRatingStore()

    initial_agent = store.agent_rating("solve-agent")
    fields = store.record_attempt(
        _attempt_record(harness_dir, "solve-agent", "pz-a", "correct")
    )
    assert fields is not None
    assert fields["rating_after"] > fields["rating_before"]
    assert fields["rating_change"] > 0
    assert fields["puzzle_rating_after"] == fields["puzzle_rating_before"]
    assert fields["puzzle_rating_change"] == 0.0
    assert fields["elapsed_seconds"] == 60.0

    agent = store.agent_rating("solve-agent")
    assert agent["rating"] > AGENT_START_RATING
    assert agent["games"] == 1
    assert agent["solves"] == 1

    # Puzzle difficulty is frozen at the imported estimate — it never moves.
    puzzle = store.puzzle_rating("pz-a")
    assert puzzle["rating"] == 1500.0
    assert puzzle["deviation"] == 75.0
    assert puzzle["games"] == 0
    assert puzzle["solves"] == 0


def test_store_puzzle_win_and_frozen_difficulty(p8_client):
    _, harness_dir = p8_client
    store = PuzzleRatingStore()

    # pz-c imported difficulty 2000 — frozen at that estimate forever.
    before = store.puzzle_rating("pz-c")
    assert before["rating"] == 2000.0

    fields = store.record_attempt(
        _attempt_record(harness_dir, "losing-agent", "pz-c", "failed")
    )
    assert fields["rating_after"] < fields["rating_before"]
    assert fields["puzzle_rating_after"] == fields["puzzle_rating_before"]
    assert fields["puzzle_rating_after"] == 2000.0

    agent = store.agent_rating("losing-agent")
    assert agent["rating"] < AGENT_START_RATING
    assert agent["games"] == 1
    assert agent["solves"] == 0

    assert store.puzzle_rating("pz-c")["rating"] == 2000.0


def test_store_abandon_and_technical_failure_no_rating(p8_client):
    _, harness_dir = p8_client
    store = PuzzleRatingStore()

    fields = store.record_attempt(
        _attempt_record(harness_dir, "walker", "pz-a", None, status="abandoned")
    )
    assert fields is None
    assert store.agent_rating("walker")["games"] == 0

    gone = store.record_attempt(
        _attempt_record(harness_dir, "incomplete", "pz-a", None, status="active")
    )
    assert gone is None
    assert store.agent_rating("incomplete")["games"] == 0


def test_store_idempotent_and_persists(p8_client):
    _, harness_dir = p8_client
    store = PuzzleRatingStore()
    record = _attempt_record(harness_dir, "repeater", "pz-a", "correct")

    first = store.record_attempt(dict(record))
    record["rating_after"] = first["rating_after"]
    again = store.record_attempt(dict(record))
    assert again is None  # already rated

    # Reload from disk: same values survive process restart semantics.
    reloaded = PuzzleRatingStore()
    assert reloaded.agent_rating("repeater") == store.agent_rating("repeater")

    assert (harness_dir / "puzzle_ratings.json").exists()
    data = json.loads(
        (harness_dir / "puzzle_ratings.json").read_text(encoding="utf-8")
    )
    assert "repeater" in data["agents"]
    # Puzzle side is frozen: never persisted by attempts.
    assert "pz-a" not in data["puzzles"]


def test_store_ratings_never_touch_models_elo():
    # PuzzleRatingStore writes only its own file; models.json is untouched.
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        harness = Path(tmp)
        store = PuzzleRatingStore(harness / "puzzle_ratings.json")
        store.record_attempt(
            {
                "attempt_id": "x",
                "model_id": "m",
                "puzzle_id": "pz-a",
                "status": "finished",
                "result": "correct",
                "puzzle_rating": 1500,
                "rating_after": None,
                "started_at": "2024-01-01T00:00:00+00:00",
                "finished_at": "2024-01-01T00:01:00+00:00",
            }
        )
        assert not (harness / "models.json").exists()
        assert (harness / "puzzle_ratings.json").exists()


# ---------------------------------------------------------------------------
# API integration
# ---------------------------------------------------------------------------


def test_api_correct_solve_stamps_and_reviews(p8_client):
    client, _ = p8_client
    key = _register(client, "solver")

    start = _start(client, key, rating_min=1400, rating_max=1600)
    attempt_id = start["attempt_id"]
    assert start["puzzle_id"] == "pz-a"

    data = _solve(client, key, attempt_id)
    assert data["status"] == "finished"

    review = client.get(
        f"/api/v1/puzzles/{attempt_id}/review", headers=_auth(key)
    ).json()
    assert review["rating_before"] == AGENT_START_RATING
    assert review["rating_after"] > AGENT_START_RATING
    assert review["rating_change"] > 0
    assert review["content_version"] is not None
    assert review["puzzle_rating_before"] == 1500.0
    assert review["puzzle_rating_after"] == review["puzzle_rating_before"]
    assert review["puzzle_rating_change"] == 0.0


def test_api_wrong_move_rates_as_puzzle_win(p8_client):
    client, _ = p8_client
    key = _register(client, "blunderer")

    start = _start(client, key, rating_min=1400, rating_max=1600)
    attempt_id = start["attempt_id"]

    _failed(client, key, attempt_id)

    review = client.get(
        f"/api/v1/puzzles/{attempt_id}/review", headers=_auth(key)
    ).json()
    assert review["result"] == "failed"
    assert review["rating_after"] < review["rating_before"]
    assert review["rating_before"] == AGENT_START_RATING


def test_api_abandon_never_rates(p8_client):
    client, _ = p8_client
    key = _register(client, "doubter")

    start = _start(client, key, rating_min=1400, rating_max=1600)
    attempt_id = start["attempt_id"]

    resp = client.post(
        f"/api/v1/puzzles/{attempt_id}/abandon", headers=_auth(key)
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "abandoned"

    review = client.get(
        f"/api/v1/puzzles/{attempt_id}/review", headers=_auth(key)
    ).json()
    assert review["status"] == "abandoned"
    assert "rating_after" not in review

    store = PuzzleRatingStore()
    assert store.agent_rating("doubter")["games"] == 0


def test_api_puzzle_difficulty_frozen_and_models_untouched(p8_client):
    client, harness_dir = p8_client
    key = _register(client, "difficulty-shifter")

    # A finished attempt on pz-a leaves its difficulty at the import estimate.
    store = PuzzleRatingStore()
    before = store.puzzle_rating("pz-a")["rating"]
    assert before == 1500.0
    start = _start(client, key, rating_min=1400, rating_max=1600)
    _solve(client, key, start["attempt_id"])
    after = store.puzzle_rating("pz-a")["rating"]
    assert after == before  # frozen — agents rate against it, it never moves

    models = json.loads(
        (harness_dir / "models.json").read_text(encoding="utf-8")
    )
    model = next(m for m in models["models"] if m.get("id") == "difficulty-shifter")
    assert model.get("elo") == 500  # inscription default, untouched by puzzles


def test_cli_ratings_smoke(p8_client):
    import chess_harness.commands as commands

    # Register an attempt so the command has data; then call it directly.
    store = PuzzleRatingStore()
    store.record_attempt(
        {
            "attempt_id": "pz-cli",
            "model_id": "cli-agent",
            "puzzle_id": "pz-a",
            "status": "finished",
            "result": "correct",
            "puzzle_rating": 1500,
            "rating_after": None,
            "started_at": "2024-01-01T00:00:00+00:00",
            "finished_at": "2024-01-01T00:01:00+00:00",
        }
    )
    assert commands.cmd_puzzles_ratings() == 0