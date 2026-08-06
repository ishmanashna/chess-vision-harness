"""Public puzzle watching / replay tests (/p/{attempt_id}, /api/v1/puzzles/public/*).

Observer-safety contract under test:
- While active, public state/browse never leak the solution, submitted moves,
  opponent line, hidden FENs, or spoiler (mate / sacrifice) themes.
- Replay unlocks only after the attempt finishes and is then complete.
- Watch page + board.image + board.txt are answer-safe while active.
"""

from __future__ import annotations

import shutil
from typing import Any, Dict, List

import pytest
from fastapi.testclient import TestClient

from conftest import FIXTURES

from chess_harness.game_manager import GameManager
from chess_harness.puzzle_import import PuzzleImporter

_LEAK_KEYS = frozenset(
    {
        "solution_moves",
        "submitted_moves",
        "opponent_moves",
        "board_fen",
        "start_fen",
        "puzzle_id",
        # spelling variants nobody may publish while active:
        "first_wrong_move",
        "failure_reason",
    }
)


def _assert_no_leak(obj: Any) -> None:
    if isinstance(obj, dict):
        for key, value in obj.items():
            assert key not in _LEAK_KEYS, f"leaked observer key: {key}"
            _assert_no_leak(value)
    elif isinstance(obj, list):
        for item in obj:
            _assert_no_leak(item)


def _row(
    puzzle_id: str,
    moves: List[str],
    rating: int = 1500,
    themes: str = "opening",
    game_url: str = "https://lichess.org/x",
) -> Dict[str, str]:
    import chess

    return {
        "PuzzleId": puzzle_id,
        "FEN": chess.STARTING_FEN,
        "Moves": " ".join(moves),
        "Rating": str(rating),
        "RatingDeviation": "75",
        "Popularity": "90",
        "NbPlays": "5000",
        "Themes": themes,
        "GameUrl": game_url,
        "OpeningTags": "test",
        "DailyDate": "2024-01-01",
    }


@pytest.fixture
def observer_client(tmp_path, monkeypatch):
    harness_dir = tmp_path / "harness"
    harness_dir.mkdir()
    shutil.copy(FIXTURES / "models.json", harness_dir / "models.json")
    monkeypatch.setenv("CHESS_HARNESS_DIR", str(harness_dir))
    monkeypatch.setenv("MODELS_FILE", str(harness_dir / "models.json"))

    PuzzleImporter().import_rows(
        [
            _row(
                "pz-a",
                ["e2e4", "e7e5", "g1f3", "g8f6", "f1c4"],
                rating=1500,
                themes="opening",
                game_url="https://lichess.org/a",
            ),
            _row(
                "pz-b",
                ["d2d4", "d7d5", "c2c4"],
                rating=1200,
                themes="opening",
                game_url="https://lichess.org/b",
            ),
            _row(
                "pz-c",
                ["c2c4", "e7e5", "g1f3"],
                rating=1800,
                themes="mateIn2",
                game_url="https://lichess.org/c",
            ),
        ]
    )

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
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    return data


def _public_state(client: TestClient, attempt_id: str) -> Dict[str, Any]:
    resp = client.get(f"/api/v1/puzzles/public/{attempt_id}")
    assert resp.status_code == 200
    return resp.json()


def test_public_state_active_is_secret_safe(observer_client):
    client, _ = observer_client
    key = _register(client, "observer-agent")

    start = _start(client, key, rating_min=1700, rating_max=1900)
    assert start["puzzle_id"] == "pz-c"
    attempt_id = start["attempt_id"]

    state = _public_state(client, attempt_id)
    _assert_no_leak(state)
    assert state["status"] == "active"
    assert state["result"] is None
    assert state["moves_played"] == 0
    assert state["agent_name"] == "observer-agent"
    assert state["themes"] == [], "spoiler theme 'mateIn2' must be withheld"
    assert " b " in state["fen"], "live board fen must reflect the visible position"

    # pz-c's solution is a single agent move: after it the attempt is finished.
    before = state["fen"]
    move = client.post(
        f"/api/v1/puzzles/{attempt_id}/move/e5", headers=_auth(key)
    )
    assert move.status_code == 200

    state2 = _public_state(client, attempt_id)
    _assert_no_leak(state2)
    assert state2["status"] == "finished"
    assert state2["result"] == "correct"
    assert state2["moves_played"] == 1
    assert state2["fen"] != before

    # A multi-move puzzle stays active after a correct move, still leak-free.
    start2 = _start(client, key, rating_min=1400, rating_max=1600)
    assert start2["puzzle_id"] == "pz-a"
    aid2 = start2["attempt_id"]
    assert _public_state(client, aid2)["status"] == "active"
    resp = client.post(f"/api/v1/puzzles/{aid2}/move/e5", headers=_auth(key))
    assert resp.status_code == 200
    st3 = _public_state(client, aid2)
    _assert_no_leak(st3)
    assert st3["status"] == "active"
    assert st3["moves_played"] == 1


def test_watch_page_board_media_and_missing(observer_client):
    client, _ = observer_client
    key = _register(client, "page-agent")
    start = _start(client, key, rating_min=1100, rating_max=1300)
    attempt_id = start["attempt_id"]

    page = client.get(f"/p/{attempt_id}")
    assert page.status_code == 200
    assert page.headers["content-type"].startswith("text/html")
    assert f'data-attempt-id="{attempt_id}"' in page.text
    assert "/js/puzzle-watch.js" in page.text
    assert "solution" not in page.text.lower()

    img = client.get(f"/p/{attempt_id}/board.png")
    assert img.status_code == 200
    assert img.headers["content-type"] == "image/png"
    assert img.content[:8] == b"\x89PNG\r\n\x1a\n"

    text = client.get(f"/p/{attempt_id}/board.txt")
    assert text.status_code == 200
    assert "a b c d e f g h" in text.text
    assert "side_to_move:" in text.text
    assert "solution" not in text.text.lower()

    missing = client.get("/p/does-not-exist")
    assert missing.status_code == 404
    assert client.get("/p/does-not-exist/board.png").status_code == 404


def test_replay_blocked_while_active(observer_client):
    client, _ = observer_client
    key = _register(client, "blocked-agent")
    start = _start(client, key, rating_min=1400, rating_max=1600)
    attempt_id = start["attempt_id"]

    replay = client.get(f"/api/v1/puzzles/public/{attempt_id}/replay")
    assert replay.status_code == 409

    abandoned = client.post(
        f"/api/v1/puzzles/{attempt_id}/abandon", headers=_auth(key)
    )
    assert abandoned.status_code == 200
    assert client.get(f"/api/v1/puzzles/public/{attempt_id}/replay").status_code == 404


def test_correct_solve_replay_unlocks(observer_client):
    client, _ = observer_client
    key = _register(client, "solver-agent")
    start = _start(client, key, rating_min=1400, rating_max=1600)
    attempt_id = start["attempt_id"]

    for mv in ("e5", "Nf6"):
        resp = client.post(
            f"/api/v1/puzzles/{attempt_id}/move/{mv}", headers=_auth(key)
        )
        assert resp.status_code == 200

    state = _public_state(client, attempt_id)
    _assert_no_leak(state)
    assert state["status"] == "finished"
    assert state["result"] == "correct"
    assert state["moves_played"] == 2

    replay = client.get(f"/api/v1/puzzles/public/{attempt_id}/replay")
    assert replay.status_code == 200
    rv = replay.json()
    assert rv["result"] == "correct"
    assert rv["submitted_moves"] == ["e7e5", "g8f6"]
    assert rv["opponent_moves"] == ["g1f3", "f1c4"]
    assert rv["solution_moves"] == ["e7e5", "g1f3", "g8f6", "f1c4"]
    assert rv["themes"] == ["opening"]
    assert rv["source_link"] == "https://lichess.org/a"
    assert rv["started_at"] and rv["finished_at"]

    labels = [p["label"] for p in rv["plies"]]
    assert "1. e5" in labels
    assert "1... Nf3" in labels
    assert rv["plies"][0]["fen"] != rv["start_fen"], "first ply advances the board"
    final = rv["plies"][-1]["fen"]
    assert final == state["fen"], "final replay position must match the live board"


def test_wrong_move_replay_shows_failure_only_after_end(observer_client):
    client, _ = observer_client
    key = _register(client, "failing-agent")
    start = _start(client, key, rating_min=1700, rating_max=1900)
    attempt_id = start["attempt_id"]

    wrong = client.post(
        f"/api/v1/puzzles/{attempt_id}/move/a7a6", headers=_auth(key)
    )
    assert wrong.status_code == 200
    assert wrong.json()["result"] == "failed"

    replay = client.get(f"/api/v1/puzzles/public/{attempt_id}/replay")
    assert replay.status_code == 200
    rv = replay.json()
    assert rv["result"] == "failed"
    assert rv["failure_reason"] == "wrong_move"
    assert rv["first_wrong_move"] == "a7a6"
    assert rv["submitted_moves"] == [], "no correct moves preceded the failure"

    state = _public_state(client, attempt_id)
    _assert_no_leak(state)
    assert state["status"] == "finished"
    assert state["result"] == "failed"


def test_public_browse_lists_without_secrets(observer_client):
    client, _ = observer_client
    key = _register(client, "browse-agent")

    active = _start(client, key, rating_min=1400, rating_max=1600)
    won = _start(client, key, rating_min=1700, rating_max=1900, theme="mateIn2")
    client.post(f"/api/v1/puzzles/{won['attempt_id']}/move/a7a6", headers=_auth(key))
    gone = _start(client, key, rating_min=1100, rating_max=1300)
    client.post(f"/api/v1/puzzles/{gone['attempt_id']}/abandon", headers=_auth(key))

    resp = client.get("/api/v1/puzzles/public/attempts")
    assert resp.status_code == 200
    data = resp.json()
    rows = data["attempts"]
    ids = {row["attempt_id"] for row in rows}
    assert active["attempt_id"] in ids
    assert won["attempt_id"] in ids
    assert gone["attempt_id"] not in ids, "abandoned attempts are not listed"

    for row in rows:
        _assert_no_leak(row)
        assert row["watch_url"].startswith("/p/")
        assert row["result"] in (None, "correct", "failed")

    won_row = next(r for r in rows if r["attempt_id"] == won["attempt_id"])
    assert won_row["status"] == "finished"
    assert won_row["result"] == "failed"
    assert won_row["themes"] == [], "spoiler theme withheld even in discovery"

    active_only = client.get("/api/v1/puzzles/public/attempts", params={"status": "active"})
    active_ids = {r["attempt_id"] for r in active_only.json()["attempts"]}
    assert active["attempt_id"] in active_ids
    assert won["attempt_id"] not in active_ids

    finished_only = client.get("/api/v1/puzzles/public/attempts", params={"status": "finished"})
    finished_ids = {r["attempt_id"] for r in finished_only.json()["attempts"]}
    assert won["attempt_id"] in finished_ids
    assert active["attempt_id"] not in finished_ids