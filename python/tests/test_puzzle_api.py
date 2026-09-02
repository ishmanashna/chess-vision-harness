"""Integration tests for the authenticated agent puzzle API (/api/v1/puzzles/*)."""

from __future__ import annotations

import json
import shutil
from typing import Any, Dict, List

import chess
import pytest
from fastapi.testclient import TestClient

from conftest import FIXTURES

from chess_harness.child_credentials import ChildCredentialStore
from chess_harness.game_manager import GameManager
from chess_harness.puzzle_attempt import PuzzleAttemptStore
from chess_harness.puzzle_import import PuzzleImporter
from chess_harness.puzzle_ratings import AGENT_START_RATING
from chess_harness.spectator import app

_HIDDEN_KEYS = frozenset({"fen", "board_fen", "moves", "start_fen", "solution_moves", "puzzle_rating"})


def _assert_no_hidden(obj: Any) -> None:
    if isinstance(obj, dict):
        for key, value in obj.items():
            assert key not in _HIDDEN_KEYS
            _assert_no_hidden(value)
    elif isinstance(obj, list):
        for item in obj:
            _assert_no_hidden(item)


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
def puzzle_api_client(tmp_path, monkeypatch):
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


def _auth(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}"}


def _register(client: TestClient, agent_id: str) -> str:
    resp = client.post("/api/v1/agents", json={"id": agent_id, "name": agent_id})
    assert resp.status_code == 200
    return resp.json()["api_key"]


def _start(client: TestClient, api_key: str, **params) -> Dict[str, Any]:
    resp = client.post("/api/v1/puzzles/start", headers=_auth(api_key), params=params or None)
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    _assert_no_hidden(data)
    return data


def test_start_attempt_safe_payload_and_flow(puzzle_api_client):
    client, harness_dir = puzzle_api_client
    key = _register(client, "puzzle-agent")

    start = _start(client, key)
    attempt_id = start["attempt_id"]
    assert attempt_id.startswith("pz-")
    assert start["status"] == "active"
    assert start["board_url"] == f"/api/v1/puzzles/{attempt_id}/board"
    assert start["board_text_url"] == f"/api/v1/puzzles/{attempt_id}/board.txt"
    assert start["review_url"] == f"/api/v1/puzzles/{attempt_id}/review"
    assert "agent_brief" in start
    assert "puzzle" in start["agent_brief"].lower()

    board = client.get(start["board_url"], headers=_auth(key))
    assert board.status_code == 200
    assert board.headers["content-type"] == "image/png"
    assert board.content[:8] == b"\x89PNG\r\n\x1a\n"

    text = client.get(start["board_text_url"], headers=_auth(key))
    assert text.status_code == 200
    body = text.text
    assert body.splitlines()[0] == "  a b c d e f g h"
    assert "side_to_move:" in body
    assert "solution_moves" not in body

    store_file = harness_dir / "puzzle_attempts.json"
    assert store_file.exists()
    assert "solution_moves" in store_file.read_text(encoding="utf-8")


def test_agent_joined_false_until_board_read(puzzle_api_client):
    client, harness_dir = puzzle_api_client
    key = _register(client, "join-agent")

    start = _start(client, key, rating_min=1200, rating_max=1300)
    attempt_id = start["attempt_id"]

    public = client.get(f"/api/v1/puzzles/public/{attempt_id}").json()
    assert public["agent_joined"] is False

    board = client.get(start["board_url"], headers=_auth(key))
    assert board.status_code == 200
    public_joined = client.get(f"/api/v1/puzzles/public/{attempt_id}").json()
    assert public_joined["agent_joined"] is True

    store = json.loads((harness_dir / "puzzle_attempts.json").read_text(encoding="utf-8"))
    record = store["attempts"][attempt_id]
    assert record["agent_joined"] is True
    assert record["agent_joined_at"]
    joined_at = record["agent_joined_at"]

    client.get(start["board_url"], headers=_auth(key))
    record2 = json.loads((harness_dir / "puzzle_attempts.json").read_text(encoding="utf-8"))[
        "attempts"
    ][attempt_id]
    assert record2["agent_joined_at"] == joined_at


def test_agent_joined_board_text_also_joins(puzzle_api_client):
    client, _ = puzzle_api_client
    key = _register(client, "join-text")

    start = _start(client, key, rating_min=1700, rating_max=1900)
    attempt_id = start["attempt_id"]
    assert client.get(f"/api/v1/puzzles/public/{attempt_id}").json()["agent_joined"] is False

    text = client.get(start["board_text_url"], headers=_auth(key))
    assert text.status_code == 200
    assert client.get(f"/api/v1/puzzles/public/{attempt_id}").json()["agent_joined"] is True


def test_start_and_move_without_board_do_not_join(puzzle_api_client):
    client, harness_dir = puzzle_api_client
    key = _register(client, "no-board-join")

    start = _start(client, key, rating_min=1700, rating_max=1900)
    attempt_id = start["attempt_id"]
    assert client.get(f"/api/v1/puzzles/public/{attempt_id}").json()["agent_joined"] is False

    move = client.post(f"/api/v1/puzzles/{attempt_id}/move/e5", headers=_auth(key))
    assert move.status_code == 200
    assert client.get(f"/api/v1/puzzles/public/{attempt_id}").json()["agent_joined"] is False
    record = json.loads((harness_dir / "puzzle_attempts.json").read_text(encoding="utf-8"))[
        "attempts"
    ][attempt_id]
    assert record.get("agent_joined") is False


def test_full_solve_with_review_unlock(puzzle_api_client):
    client, _ = puzzle_api_client
    key = _register(client, "solver")

    start = _start(client, key, rating_min=1400, rating_max=1600)
    assert start["puzzle_id"] == "pz-a"
    attempt_id = start["attempt_id"]

    move = client.post(
        f"/api/v1/puzzles/{attempt_id}/move/e5", headers=_auth(key)
    )
    assert move.status_code == 200
    data = move.json()
    assert data["ok"] is True
    assert data["status"] == "active"
    assert data["result"] is None
    assert data["moves_played"] == 1
    _assert_no_hidden(data)

    locked = client.get(
        f"/api/v1/puzzles/{attempt_id}/review",
        headers=_auth(key),
    )
    assert locked.status_code == 409

    move2 = client.post(
        f"/api/v1/puzzles/{attempt_id}/move/Nf6", headers=_auth(key)
    )
    assert move2.status_code == 200
    data2 = move2.json()
    assert data2["status"] == "finished"
    assert data2["result"] == "correct"
    assert data2["moves_played"] == 2
    assert "review_url" in data2

    review = client.get(
        f"/api/v1/puzzles/{attempt_id}/review", headers=_auth(key)
    )
    assert review.status_code == 200
    rv = review.json()
    assert rv["result"] == "correct"
    assert rv["submitted_moves"] == ["e7e5", "g8f6"]
    assert rv["opponent_moves"] == ["g1f3", "f1c4"]
    assert rv["solution_moves"] == ["e7e5", "g1f3", "g8f6", "f1c4"]
    assert rv["themes"] == ["opening"]
    assert rv["source_link"] == "https://lichess.org/a"
    assert rv["rating_before"] == AGENT_START_RATING
    assert rv["rating_after"] is not None
    assert rv["rating_after"] > AGENT_START_RATING
    assert rv["rating_change"] > 0
    assert rv["rating_deviation_before"] is not None
    assert rv["puzzle_rating_before"] is not None
    assert rv["content_version"] is not None
    assert rv["elapsed_seconds"] is not None


def test_wrong_move_fails_attempt_no_retry(puzzle_api_client):
    client, _ = puzzle_api_client
    key = _register(client, "wrong-agent")

    start = _start(client, key)
    attempt_id = start["attempt_id"]

    move = client.post(
        f"/api/v1/puzzles/{attempt_id}/move/a7a6", headers=_auth(key)
    )
    assert move.status_code == 200
    data = move.json()
    assert data["status"] == "finished"
    assert data["result"] == "failed"

    retry = client.post(
        f"/api/v1/puzzles/{attempt_id}/move/e7e5", headers=_auth(key)
    )
    assert retry.status_code == 409

    review = client.get(
        f"/api/v1/puzzles/{attempt_id}/review", headers=_auth(key)
    ).json()
    assert review["result"] == "failed"
    assert review["failure_reason"] == "wrong_move"
    assert review["first_wrong_move"] == "a7a6"
    assert review["solution_moves"]


def test_illegal_move_fails_attempt(puzzle_api_client):
    client, _ = puzzle_api_client
    key = _register(client, "illegal-agent")

    start = _start(client, key)
    attempt_id = start["attempt_id"]

    move = client.post(
        f"/api/v1/puzzles/{attempt_id}/move/a9a9", headers=_auth(key)
    )
    assert move.status_code == 200
    data = move.json()
    assert data["status"] == "finished"
    assert data["result"] == "failed"
    assert data["moves_played"] == 1


def test_abandon_ends_attempt_without_review(puzzle_api_client):
    client, _ = puzzle_api_client
    key = _register(client, "abandoner")

    start = _start(client, key)
    attempt_id = start["attempt_id"]

    abandoned = client.post(
        f"/api/v1/puzzles/{attempt_id}/abandon", headers=_auth(key)
    )
    assert abandoned.status_code == 200
    assert abandoned.json()["status"] == "abandoned"

    move = client.post(
        f"/api/v1/puzzles/{attempt_id}/move/e5", headers=_auth(key)
    )
    assert move.status_code == 409

    review = client.get(
        f"/api/v1/puzzles/{attempt_id}/review", headers=_auth(key)
    ).json()
    assert review["status"] == "abandoned"
    assert "solution_moves" not in review


def test_session_exclusion_and_empty_pool(puzzle_api_client):
    client, _ = puzzle_api_client
    key = _register(client, "exclusion-agent")

    ids: set[str] = set()
    for _ in range(3):
        start = _start(client, key)
        assert start["puzzle_id"] not in ids
        ids.add(start["puzzle_id"])
        client.post(
            f"/api/v1/puzzles/{start['attempt_id']}/abandon",
            headers=_auth(key),
        )
    assert ids == {"pz-a", "pz-b", "pz-c"}

    empty = client.post("/api/v1/puzzles/start", headers=_auth(key))
    assert empty.status_code == 404
    assert "No eligible puzzle" in empty.json()["error"]


def test_bare_start_prefers_easy_band(puzzle_api_client):
    from chess_harness.puzzle_store import PuzzleStore

    client, _ = puzzle_api_client
    key = _register(client, "easy-band-agent")

    start = _start(client, key)
    record = PuzzleStore().get(start["puzzle_id"])
    assert record is not None
    assert start["puzzle_id"] == "pz-b"
    assert int(record["rating"]) <= 1200


def test_auto_band_widens_when_tight_band_empty(tmp_path, monkeypatch):
    harness_dir = tmp_path / "harness"
    harness_dir.mkdir()
    shutil.copy(FIXTURES / "models.json", harness_dir / "models.json")
    monkeypatch.setenv("CHESS_HARNESS_DIR", str(harness_dir))
    monkeypatch.setenv("MODELS_FILE", str(harness_dir / "models.json"))

    PuzzleImporter().import_rows(
        [
            _row("pz-hard", ["e2e4", "e7e5"], rating=1800),
            _row("pz-easy", ["d2d4", "d7d5"], rating=900),
        ]
    )

    import chess_harness.api_limits as api_limits
    import chess_harness.spectator as spec

    api_limits.get_limit_enforcer().reset_counters()
    spec._base = str(harness_dir)
    spec.game_manager = GameManager(str(harness_dir))
    spec._controller = None
    spec._game_service = None

    client = TestClient(app)
    key = _register(client, "widen-agent")
    start = _start(client, key)
    assert start["puzzle_id"] == "pz-easy"


def test_filters_rating_band_and_theme(puzzle_api_client):
    client, _ = puzzle_api_client
    key = _register(client, "filter-agent")

    start = _start(client, key, theme="mateIn2")
    assert start["puzzle_id"] == "pz-c"

    start = _start(client, key, rating_min=1100, rating_max=1300)
    assert start["puzzle_id"] == "pz-b"

    none = client.post(
        "/api/v1/puzzles/start",
        headers=_auth(key),
        params={"rating_min": 900, "rating_max": 1000},
    )
    assert none.status_code == 404


@pytest.fixture
def capped_env(puzzle_api_client, monkeypatch):
    monkeypatch.setenv("CHESS_HARNESS_MAX_PUZZLE_ATTEMPTS_PER_KEY", "2")
    return puzzle_api_client


def test_concurrency_cap_operator_tunable(capped_env):
    client, _ = capped_env
    key = _register(client, "capped-agent")

    _start(client, key, rating_min=1100, rating_max=1300)
    attempt_id = _start(client, key, rating_min=1700, rating_max=1900)["attempt_id"]
    assert attempt_id

    blocked = client.post("/api/v1/puzzles/start", headers=_auth(key))
    assert blocked.status_code == 429

    client.post(f"/api/v1/puzzles/{attempt_id}/abandon", headers=_auth(key))
    assert client.post("/api/v1/puzzles/start", headers=_auth(key)).status_code == 200


def test_ownership_and_auth_gates(puzzle_api_client):
    client, _ = puzzle_api_client
    key_a = _register(client, "owner")
    key_b = _register(client, "intruder")

    start = _start(client, key_a)
    attempt_id = start["attempt_id"]

    stolen = client.get(
        f"/api/v1/puzzles/{attempt_id}/board", headers=_auth(key_b)
    )
    assert stolen.status_code == 404

    stolen_move = client.post(
        f"/api/v1/puzzles/{attempt_id}/move/e5", headers=_auth(key_b)
    )
    assert stolen_move.status_code == 404

    no_auth = client.get(f"/api/v1/puzzles/{attempt_id}/board")
    assert no_auth.status_code == 401

    missing = client.get("/api/v1/puzzles/pz-none/board", headers=_auth(key_a))
    assert missing.status_code == 404


def test_scoped_child_credential_rejected(puzzle_api_client):
    client, _ = puzzle_api_client
    key = _register(client, "parent-model")

    minted = ChildCredentialStore().mint(
        "game-child-test", "WHITE", "parent-model"
    )
    denied = client.post("/api/v1/puzzles/start", headers=_auth(minted["key"]))
    assert denied.status_code == 403

    start = _start(client, key)
    attempt_id = start["attempt_id"]
    denied_board = client.get(
        f"/api/v1/puzzles/{attempt_id}/board", headers=_auth(minted["key"])
    )
    assert denied_board.status_code in (403, 404)


def test_move_json_body_legacy(puzzle_api_client):
    client, _ = puzzle_api_client
    key = _register(client, "body-agent")

    start = _start(client, key, rating_min=1400, rating_max=1600)
    assert start["puzzle_id"] == "pz-a"
    attempt_id = start["attempt_id"]

    move = client.post(
        f"/api/v1/puzzles/{attempt_id}/move",
        headers=_auth(key),
        json={"move": "e5"},
    )
    assert move.status_code == 200
    assert move.json()["moves_played"] == 1


def test_start_brief_covers_perpetual_loop(puzzle_api_client):
    client, _ = puzzle_api_client
    key = _register(client, "loop-agent")
    start = _start(client, key)
    brief = start["agent_brief"]
    assert "Continuous loop" in brief
    assert "puzzle Glicko" in brief
    assert "800" in brief
    assert "indefinitely" in brief
    assert "rating delta" in brief
    assert "/api/v1/puzzles/start" in brief
    assert "30 minutes" in brief
    assert "Do not skip board.txt" in brief
    assert "confirm every occupied square" in brief
    assert "side to move at the bottom" not in brief.lower()
    assert "h through a" not in brief.lower()
    assert "white at the bottom" in brief.lower() or "white at bottom" in brief.lower()
    assert "a1 is bottom-left" in brief.lower()
    assert "Prefer the PNG" not in brief
    assert "Prefer UCI" in brief


def test_board_text_black_to_move_header(puzzle_api_client):
    client, _ = puzzle_api_client
    key = _register(client, "black-bottom-agent")
    start = _start(client, key, rating_min=1490, rating_max=1510)
    record = PuzzleAttemptStore().get(start["attempt_id"])
    board = chess.Board(record["board_fen"])
    assert board.turn == chess.BLACK, "pz-a setup leaves Black to move"

    text = client.get(start["board_text_url"], headers=_auth(key))
    assert text.status_code == 200
    assert text.text.splitlines()[0] == "  a b c d e f g h"
    assert "side_to_move: black" in text.text


def test_agent_white_bottom_spectator_flipped_for_black_to_move(puzzle_api_client):
    client, _ = puzzle_api_client
    key = _register(client, "orient-split-agent")
    start = _start(client, key, rating_min=1490, rating_max=1510)
    attempt_id = start["attempt_id"]
    record = PuzzleAttemptStore().get(attempt_id)
    board = chess.Board(record["board_fen"])
    assert board.turn == chess.BLACK, "pz-a setup leaves Black to move"

    agent_txt = client.get(start["board_text_url"], headers=_auth(key))
    assert agent_txt.status_code == 200
    assert agent_txt.text.splitlines()[0] == "  a b c d e f g h"

    spectator_txt = client.get(f"/p/{attempt_id}/board.txt")
    assert spectator_txt.status_code == 200
    assert spectator_txt.text.splitlines()[0] == "  h g f e d c b a"

    agent_png = client.get(start["board_url"], headers=_auth(key))
    spectator_png = client.get(f"/p/{attempt_id}/board.png")
    assert agent_png.status_code == 200
    assert spectator_png.status_code == 200
    assert agent_png.content[:8] == b"\x89PNG\r\n\x1a\n"
    assert spectator_png.content[:8] == b"\x89PNG\r\n\x1a\n"
    assert agent_png.content != spectator_png.content


def test_attempts_never_write_results_jsonl(puzzle_api_client):
    client, harness_dir = puzzle_api_client
    key = _register(client, "no-results-agent")
    results_path = harness_dir / "results.jsonl"

    start = _start(client, key, rating_min=1400, rating_max=1600)
    attempt_id = start["attempt_id"]
    solved = client.post(f"/api/v1/puzzles/{attempt_id}/move/e5", headers=_auth(key))
    assert solved.status_code == 200
    solved2 = client.post(f"/api/v1/puzzles/{attempt_id}/move/Nf6", headers=_auth(key))
    assert solved2.status_code == 200
    assert solved2.json()["result"] == "correct"

    failed = _start(client, key)
    wrong = client.post(
        f"/api/v1/puzzles/{failed['attempt_id']}/move/a7a6", headers=_auth(key)
    )
    assert wrong.status_code == 200
    assert wrong.json()["status"] == "finished"

    abandoned_attempt = _start(client, key)
    abandoned = client.post(
        f"/api/v1/puzzles/{abandoned_attempt['attempt_id']}/abandon", headers=_auth(key)
    )
    assert abandoned.status_code == 200
    assert abandoned.json()["status"] == "abandoned"

    assert not results_path.exists(), "puzzle attempts must never write results.jsonl"
    assert (harness_dir / "puzzle_attempts.json").exists()


def test_prune_idle_active_abandons_stale_puzzle_attempt(tmp_path):
    import json
    from datetime import datetime, timedelta, timezone

    from chess_harness.puzzle_attempt import PuzzleAttemptStore

    path = tmp_path / "puzzles.json"
    stale = (datetime.now(timezone.utc) - timedelta(seconds=4000)).isoformat()
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "attempts": {
                    "pz-stale": {
                        "attempt_id": "pz-stale",
                        "status": "active",
                        "updated_at": stale,
                        "started_at": stale,
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    store = PuzzleAttemptStore(path)
    abandoned = store.prune_idle_active(1800.0)
    assert abandoned == ["pz-stale"]
    record = store.get("pz-stale")
    assert record is not None
    assert record["status"] == "abandoned"


def _stale_puzzle_attempt(harness_dir, attempt_id: str) -> None:
    import json
    from datetime import datetime, timedelta, timezone

    path = harness_dir / "puzzle_attempts.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    stale = (datetime.now(timezone.utc) - timedelta(seconds=4000)).isoformat()
    record = data["attempts"][attempt_id]
    record["updated_at"] = stale
    record["started_at"] = stale
    path.write_text(json.dumps(data), encoding="utf-8")


def test_puzzle_board_abandons_idle_attempt_on_read(puzzle_api_client):
    client, harness_dir = puzzle_api_client
    key = _register(client, "idle-puzzle-agent")
    start = _start(client, key)
    attempt_id = start["attempt_id"]

    _stale_puzzle_attempt(harness_dir, attempt_id)

    board = client.get(start["board_url"], headers=_auth(key))
    assert board.status_code == 200

    from chess_harness.puzzle_attempt import PuzzleAttemptStore

    record = PuzzleAttemptStore().get(attempt_id)
    assert record is not None
    assert record["status"] == "abandoned"

    review = client.get(start["review_url"], headers=_auth(key))
    assert review.status_code == 200
    assert review.json()["status"] == "abandoned"


def test_puzzle_idle_abandon_frees_concurrency_slot(puzzle_api_client, monkeypatch):
    import chess_harness.api_limits as api_limits
    from chess_harness.limits import HarnessLimits

    client, harness_dir = puzzle_api_client
    key = _register(client, "idle-cap-agent")

    monkeypatch.setattr(
        api_limits.get_limit_enforcer(),
        "_limits",
        HarnessLimits(max_puzzle_attempts_per_key=1),
    )

    start = _start(client, key)
    _stale_puzzle_attempt(harness_dir, start["attempt_id"])
    client.get(start["board_url"], headers=_auth(key))

    second = client.post("/api/v1/puzzles/start", headers=_auth(key))
    assert second.status_code == 200
    assert second.json()["status"] == "active"
