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

import chess
import pytest
from fastapi.testclient import TestClient

from conftest import FIXTURES

from chess_harness.game_manager import GameManager
from chess_harness.puzzle_attempt import PuzzleAttemptStore
from chess_harness.puzzle_import import PuzzleImporter
from leak_guards import assert_puzzle_no_leak


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


def test_public_state_active_includes_solution(observer_client):
    client, _ = observer_client
    key = _register(client, "observer-agent")

    start = _start(client, key, rating_min=1700, rating_max=1900)
    assert start["puzzle_id"] == "pz-c"
    attempt_id = start["attempt_id"]

    state = _public_state(client, attempt_id)
    assert_puzzle_no_leak(state)
    assert state["status"] == "active"
    assert state["result"] is None
    assert state["moves_played"] == 0
    assert state["agent_name"] == "observer-agent"
    assert state["submitted_moves"] == [], "no moves submitted yet"
    assert state["opponent_moves"] == []
    assert state["solution_moves"] == ["e7e5", "g1f3"]
    assert state["solution_agent_moves"] == ["e5"]
    assert state["solution_opponent_moves"] == ["Nf3"]
    assert "themes" not in state, "themes are never user-facing"
    assert state["key"], "attempt chain key is published"
    assert state["watch_url"] == f"/p/{attempt_id}"
    assert state["agent_joined"] is False
    assert " b " in state["fen"], "live board fen must reflect the visible position"

    # pz-c's solution is a single agent move: after it the attempt is finished.
    before = state["fen"]
    move = client.post(
        f"/api/v1/puzzles/{attempt_id}/move/e5", headers=_auth(key)
    )
    assert move.status_code == 200

    state2 = _public_state(client, attempt_id)
    assert_puzzle_no_leak(state2)
    assert state2["status"] == "finished"
    assert state2["result"] == "correct"
    assert state2["moves_played"] == 1
    assert state2["submitted_moves"] == ["e5"], "SAN labels are public once played"
    assert state2["opponent_moves"] == ["Nf3"], "the finishing puzzle reply was played"
    assert state2["fen"] != before
    summary = state2.get("agent_summary")
    assert summary and summary["attempts"] == 1 and summary["solves"] == 1

    # A multi-move puzzle stays active after a correct move; solution stays visible.
    start2 = _start(client, key, rating_min=1400, rating_max=1600)
    assert start2["puzzle_id"] == "pz-a"
    aid2 = start2["attempt_id"]
    st2_active = _public_state(client, aid2)
    assert st2_active["solution_moves"] == ["e7e5", "g1f3", "g8f6", "f1c4"]
    assert _public_state(client, aid2)["status"] == "active"
    resp = client.post(f"/api/v1/puzzles/{aid2}/move/e5", headers=_auth(key))
    assert resp.status_code == 200
    st3 = _public_state(client, aid2)
    assert_puzzle_no_leak(st3)
    assert st3["status"] == "active"
    assert st3["moves_played"] == 1
    assert st3["submitted_moves"] == ["e5"]
    assert st3["opponent_moves"] == ["Nf3"], "the puzzle reply is public SAN too"


def test_watch_page_board_media_and_missing(observer_client):
    client, _ = observer_client
    key = _register(client, "page-agent")
    start = _start(client, key, rating_min=1100, rating_max=1300)
    attempt_id = start["attempt_id"]

    page = client.get(f"/p/{attempt_id}")
    assert page.status_code == 200
    assert page.headers["content-type"].startswith("text/html")
    assert "/js/puzzle-watch.js" in page.text
    assert "solution" not in page.text.lower()
    assert "moves-col" in page.text, "P2: moves column mirrors the game spectator"
    assert "attempt chain" in page.text.lower()
    assert "theme-tag" not in page.text, "no theme rendering anywhere"

    img = client.get(f"/p/{attempt_id}/board.png")
    assert img.status_code == 200
    assert img.headers["content-type"] == "image/png"
    assert img.content[:8] == b"\x89PNG\r\n\x1a\n"

    text = client.get(f"/p/{attempt_id}/board.txt")
    assert text.status_code == 200
    record = PuzzleAttemptStore().get(attempt_id)
    board = chess.Board(record["board_fen"])
    header = (
        "h g f e d c b a" if board.turn == chess.BLACK else "a b c d e f g h"
    )
    assert header in text.text
    assert "side_to_move:" in text.text
    assert "solution" not in text.text.lower()

    missing = client.get("/p/does-not-exist")
    assert missing.status_code == 200
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
    assert_puzzle_no_leak(state)
    assert state["status"] == "finished"
    assert state["result"] == "correct"
    assert state["moves_played"] == 2
    assert state["side_to_move"] in ("white", "black")

    replay = client.get(f"/api/v1/puzzles/public/{attempt_id}/replay")
    assert replay.status_code == 200
    rv = replay.json()
    assert rv["result"] == "correct"
    assert rv["side_to_move"] in ("white", "black")
    assert rv["submitted_moves"] == ["e7e5", "g8f6"]
    assert rv["opponent_moves"] == ["g1f3", "f1c4"]
    assert rv["solution_moves"] == ["e7e5", "g1f3", "g8f6", "f1c4"]
    assert "themes" not in rv, "themes are never published on public surfaces"
    assert rv["source_link"] == "https://lichess.org/a"
    assert rv["started_at"] and rv["finished_at"]

    labels = [p["label"] for p in rv["plies"]]
    assert "1. e5" in labels
    assert "1... Nf3" in labels
    assert rv["plies"][0]["fen"] != rv["start_fen"], "first ply advances the board"
    final = rv["plies"][-1]["fen"]
    assert final == state["fen"], "final replay position must match the live board"


def test_illegal_move_replay_records_attempt(observer_client):
    client, _ = observer_client
    key = _register(client, "illegal-replay-agent")
    start = _start(client, key, rating_min=1400, rating_max=1600)
    attempt_id = start["attempt_id"]
    start_fen = _public_state(client, attempt_id)["fen"]

    illegal = client.post(
        f"/api/v1/puzzles/{attempt_id}/move/a9a9", headers=_auth(key)
    )
    assert illegal.status_code == 200
    assert illegal.json()["result"] == "failed"

    state = _public_state(client, attempt_id)
    assert state["status"] == "finished"
    assert state["result"] == "failed"
    assert state["moves_played"] == 1
    assert state["submitted_moves"] == ["a9a9"]
    assert state["fen"] == start_fen, "illegal move must not advance the visible board"
    assert state["failure_reason"] == "illegal_move"
    assert state["first_wrong_move"] == "a9a9"

    replay = client.get(f"/api/v1/puzzles/public/{attempt_id}/replay")
    assert replay.status_code == 200
    rv = replay.json()
    assert rv["result"] == "failed"
    assert rv["failure_reason"] == "illegal_move"
    assert rv["first_wrong_move"] == "a9a9"
    assert rv["submitted_moves"] == ["a9a9"]
    assert rv["plies"], "illegal try must appear in replay plies"
    assert "a9a9" in rv["plies"][0]["label"]
    assert rv["plies"][0]["fen"] == start_fen
    assert rv["plies"][-1]["fen"] == state["fen"]
    assert rv["solution_moves"]
    assert rv["solution_agent_moves"]


def test_well_formed_illegal_uci_public_state(observer_client):
    """Well-formed but illegal UCI must not 500 public state."""
    client, _ = observer_client
    key = _register(client, "illegal-uci-agent")
    start = _start(client, key, rating_min=1400, rating_max=1600)
    attempt_id = start["attempt_id"]
    start_fen = _public_state(client, attempt_id)["fen"]

    illegal = client.post(
        f"/api/v1/puzzles/{attempt_id}/move/b1b4", headers=_auth(key)
    )
    assert illegal.status_code == 200
    assert illegal.json()["result"] == "failed"

    state = _public_state(client, attempt_id)
    assert state["status"] == "finished"
    assert state["result"] == "failed"
    assert state["fen"] == start_fen
    assert state["failure_reason"] == "illegal_move"
    assert state["first_wrong_move"] == "b1b4"

    replay = client.get(f"/api/v1/puzzles/public/{attempt_id}/replay")
    assert replay.status_code == 200
    rv = replay.json()
    assert rv["failure_reason"] == "illegal_move"
    assert rv["plies"][-1]["fen"] == start_fen


def test_wrong_move_replay_shows_failure_only_after_end(observer_client):
    client, _ = observer_client
    key = _register(client, "failing-agent")
    start = _start(client, key, rating_min=1700, rating_max=1900)
    attempt_id = start["attempt_id"]
    start_fen = _public_state(client, attempt_id)["fen"]

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
    assert rv["solution_agent_moves"]
    assert rv["solution_opponent_moves"] is not None
    assert rv["submitted_moves"] == ["a7a6"], "wrong move is now recorded"
    assert rv["plies"][-1]["fen"] == start_fen, "wrong move must not advance replay FEN"

    state = _public_state(client, attempt_id)
    assert_puzzle_no_leak(state)
    assert state["status"] == "finished"
    assert state["result"] == "failed"
    assert state["fen"] == start_fen
    assert state["failure_reason"] == "wrong_move"
    assert state["first_wrong_move"] == "a7a6"


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
    assert gone["attempt_id"] in ids, "abandoned attempts are listed for chain honesty"

    for row in rows:
        assert_puzzle_no_leak(row)
        assert row["watch_url"].startswith("/p/")
        assert row["model_id"]
        assert row["result"] in (None, "correct", "failed")
        assert row["key"], "attempt chain key travels on discovery rows"

    won_row = next(r for r in rows if r["attempt_id"] == won["attempt_id"])
    assert won_row["status"] == "finished"
    assert won_row["result"] == "failed"
    assert "themes" not in won_row, "themes are never user-facing, not even filtered"

    active_only = client.get("/api/v1/puzzles/public/attempts", params={"status": "active"})
    active_ids = {r["attempt_id"] for r in active_only.json()["attempts"]}
    assert active["attempt_id"] in active_ids
    assert won["attempt_id"] not in active_ids

    finished_only = client.get("/api/v1/puzzles/public/attempts", params={"status": "finished"})
    finished_ids = {r["attempt_id"] for r in finished_only.json()["attempts"]}
    assert won["attempt_id"] in finished_ids
    assert active["attempt_id"] not in finished_ids


def test_public_attempt_chain_by_key(observer_client):
    client, _ = observer_client
    key = _register(client, "chain-agent")

    first = _start(client, key, rating_min=1100, rating_max=1300)["attempt_id"]
    client.post(f"/api/v1/puzzles/{first}/move/a7a6", headers=_auth(key))
    second = _start(client, key, rating_min=1400, rating_max=1600)["attempt_id"]

    rows = client.get("/api/v1/puzzles/public/attempts").json()["attempts"]
    chain_key = next(r["key"] for r in rows if r["attempt_id"] == second)
    assert chain_key

    chain = client.get(
        "/api/v1/puzzles/public/attempts", params={"by_key": chain_key}
    ).json()["attempts"]
    ids = [r["attempt_id"] for r in chain]
    assert ids == [second, first], "chain is newest first"
    for row in chain:
        assert row["key"] == chain_key
        assert_puzzle_no_leak(row)

    foreign = client.get(
        "/api/v1/puzzles/public/attempts", params={"by_key": "0" * 16}
    ).json()["attempts"]
    assert foreign == []


def test_by_key_scan_public_rate_limited(observer_client):
    from chess_harness.api_limits import (
        PUBLIC_BY_KEY_LIMIT_PER_IP_PER_HOUR,
    )

    client, _ = observer_client
    key = _register(client, "scanner-agent")
    first = _start(client, key, rating_min=1100, rating_max=1300)["attempt_id"]
    rows = client.get("/api/v1/puzzles/public/attempts").json()["attempts"]
    fingerprint = next(r["key"] for r in rows if r["attempt_id"] == first)
    url = f"/api/v1/puzzles/public/attempts?by_key={fingerprint}"

    ok = 0
    denied = 0
    for _ in range(PUBLIC_BY_KEY_LIMIT_PER_IP_PER_HOUR + 5):
        resp = client.get(url)
        if resp.status_code == 200:
            ok += 1
        else:
            denied += 1
    assert ok == PUBLIC_BY_KEY_LIMIT_PER_IP_PER_HOUR
    assert denied >= 1, "excess by_key scans must be rate-limited"


def test_public_attempt_chain_by_agent_fallback(observer_client):
    client, _ = observer_client
    key = _register(client, "fallback-agent")

    first = _start(client, key, rating_min=1100, rating_max=1300)["attempt_id"]
    client.post(f"/api/v1/puzzles/{first}/move/a7a6", headers=_auth(key))
    second = _start(client, key, rating_min=1400, rating_max=1600)["attempt_id"]

    rows = client.get(
        "/api/v1/puzzles/public/attempts", params={"by_agent": "fallback-agent"}
    ).json()["attempts"]
    ids = [r["attempt_id"] for r in rows]
    assert second in ids, "by_agent returns both attempts"
    assert first in ids
    for row in rows:
        assert row["agent_name"] == "fallback-agent"

    empty = client.get(
        "/api/v1/puzzles/public/attempts", params={"by_agent": "nobody"}
    ).json()["attempts"]
    assert empty == []


def test_observer_legacy_missing_agent_joined_defaults_true():
    import chess

    from chess_harness.puzzle_observer import observer_state

    state = observer_state(
        {
            "attempt_id": "pz-legacy",
            "status": "active",
            "board_fen": chess.STARTING_FEN,
            "start_fen": chess.STARTING_FEN,
            "submitted_moves": [],
            "opponent_moves": [],
            "model_id": "legacy-agent",
            "puzzle_rating": 1200,
        }
    )
    assert state["agent_joined"] is True