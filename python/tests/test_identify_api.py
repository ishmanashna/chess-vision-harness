"""Integration tests for the authenticated board-identification API
(/api/v1/identify/*) and its public watch/replay (/i/, /api/v1/identify/public/*).

Covered: safe start payloads (no FEN/answer/provenance/difficulty leak),
exact answer-schema validation (400 without finishing the attempt), placement
scoring (exact / wrong_type / wrong_color / missing / extra, accuracy,
full-position flag), review unlock, ownership/auth/scoped gates, concurrency
cap, abandon, and observer secrecy (live state vs post-completion replay).
"""

from __future__ import annotations

import json
import shutil
from typing import Any, Dict, List

import pytest
from fastapi.testclient import TestClient

from conftest import FIXTURES

from chess_harness.child_credentials import ChildCredentialStore
from chess_harness.game_manager import GameManager
from chess_harness.puzzle_import import PuzzleImporter

from leak_guards import assert_identify_no_leak


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
def identify_client(tmp_path, monkeypatch):
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
        "/api/v1/identify/start", headers=_auth(api_key), params=params or None
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    return data


def _store_record(harness_dir, attempt_id: str) -> Dict[str, Any]:
    data = json.loads(
        (harness_dir / "identify_attempts.json").read_text(encoding="utf-8")
    )
    return data["attempts"][attempt_id]


def test_start_safe_payload_and_flow(identify_client):
    client, harness_dir = identify_client
    key = _register(client, "identify-agent")

    start = _start(client, key)
    attempt_id = start["attempt_id"]
    assert attempt_id.startswith("bi-")
    assert start["status"] == "active"
    assert start["board_url"] == f"/api/v1/identify/{attempt_id}/board"
    assert start["answer_url"] == f"/api/v1/identify/{attempt_id}/answer"
    assert start["review_url"] == f"/api/v1/identify/{attempt_id}/review"
    assert "identify" in start["agent_brief"].lower()
    assert "identify" in start["agent_brief"].lower()
    brief = start["agent_brief"]
    assert "Continuous loop" in brief
    assert "indefinitely" in brief
    assert "accuracy" in brief
    assert "/api/v1/identify/start" in brief
    assert "Do not skip board.txt" in brief
    assert "confirm every occupied square" in brief
    assert "Prefer the PNG" not in brief
    assert_identify_no_leak(start)

    board = client.get(start["board_url"], headers=_auth(key))
    assert board.status_code == 200
    assert board.headers["content-type"] == "image/png"
    assert board.content[:8] == b"\x89PNG\r\n\x1a\n"

    text = client.get(start["board_text_url"], headers=_auth(key))
    assert text.status_code == 200
    assert "a b c d e f g h" in text.text
    assert "side_to_move:" in text.text
    assert "pieces" not in text.text

    store = harness_dir / "identify_attempts.json"
    assert store.exists()
    assert "correct_pieces" in store.read_text(encoding="utf-8")
    assert "puzzle_id" in store.read_text(encoding="utf-8")


def test_schema_validation_400_without_finishing(identify_client):
    client, _ = identify_client
    key = _register(client, "schema-agent")
    start = _start(client, key, rating_min=1400, rating_max=1600)
    attempt_id = start["attempt_id"]
    url = f"/api/v1/identify/{attempt_id}/answer"

    cases = [
        {},  # no pieces key
        {"pieces": ["a1=wR"]},
        {"pieces": {"z9": "wR"}},
        {"pieces": {"a1": "xK"}},
        {"pieces": {"a1": "wK", "a2": "wK", "a3": "wK"}},  # three white kings
        {"pieces": {"a1": 42}},
    ]
    for body in cases:
        resp = client.post(url, headers=_auth(key), json=body)
        assert resp.status_code == 400, body
        assert resp.json()["ok"] is False
        # schema errors never end the attempt
        assert client.get(
            f"/api/v1/identify/{attempt_id}/review", headers=_auth(key)
        ).status_code == 409

    # a valid answer still works afterwards (schema errors never finish it)
    good = client.post(url, headers=_auth(key), json={"pieces": {"a1": "wR", "e8": "bK"}})
    assert good.status_code == 200
    assert good.json()["status"] == "finished"


def test_correct_answer_full_position_and_review(identify_client):
    client, harness_dir = identify_client
    key = _register(client, "full-agent")

    start = _start(client, key, rating_min=1400, rating_max=1600)
    attempt_id = start["attempt_id"]
    record = _store_record(harness_dir, attempt_id)
    assert record["puzzle_rating"] == 1500

    correct = record["correct_pieces"]
    n = len(correct)
    assert n > 0

    answer = client.post(
        f"/api/v1/identify/{attempt_id}/answer",
        headers=_auth(key),
        json={"pieces": correct},
    )
    assert answer.status_code == 200
    data = answer.json()
    assert data["status"] == "finished"
    assert data["result"] == "correct"
    assert data["accuracy"] == 1.0
    assert data["score"]["full_position"] is True
    assert data["score"]["exact"] == n

    review = client.get(
        f"/api/v1/identify/{attempt_id}/review", headers=_auth(key)
    ).json()
    assert review["result"] == "correct"
    assert review["correct_pieces"] == correct
    assert review["submitted_pieces"] == correct
    assert review["difficulty"] == 1500
    assert all(row["status"] == "exact" for row in review["per_square"])
    assert "puzzle_id" not in review

    retry = client.post(
        f"/api/v1/identify/{attempt_id}/answer",
        headers=_auth(key),
        json={"pieces": correct},
    )
    assert retry.status_code == 409


def test_wrong_answer_scoring_and_review(identify_client):
    client, harness_dir = identify_client
    key = _register(client, "wrong-agent")

    # Scenario A: one piece misidentified by type on the right square.
    start = _start(client, key, rating_min=1400, rating_max=1600)
    attempt_id = start["attempt_id"]
    record = _store_record(harness_dir, attempt_id)
    wrong = dict(record["correct_pieces"])
    full = len(wrong)
    # Corrupt a pawn in place -> same square, same color, wrong type.
    pawn_sq = next(sq for sq, code in wrong.items() if code == "wP")
    wrong[pawn_sq] = "wQ"
    resp = client.post(
        f"/api/v1/identify/{attempt_id}/answer",
        headers=_auth(key),
        json={"pieces": wrong},
    )
    data = resp.json()
    assert data["result"] == "failed"
    assert data["score"]["exact"] == full - 1
    assert data["score"]["wrong_type"] == 1
    assert data["score"]["misidentified"] == 1
    assert data["score"]["missing"] == 0
    assert data["score"]["extra"] == 0
    assert data["score"]["full_position"] is False
    assert 0 < data["accuracy"] < 1.0

    # Review reveals submitted vs correct; the misidentified square is flagged.
    review = client.get(
        f"/api/v1/identify/{attempt_id}/review", headers=_auth(key)
    ).json()
    assert review["result"] == "failed"
    assert review["failure_reason"] == "placement_mismatch"
    flagged = next(r for r in review["per_square"] if r["square"] == pawn_sq)
    assert flagged["expected"] == "wP"
    assert flagged["submitted"] == "wQ"
    assert flagged["status"] == "wrong_type"

    # Scenario B: one piece omitted + one extra phantom piece.
    start2 = _start(client, key, rating_min=1700, rating_max=1900)
    aid2 = start2["attempt_id"]
    rec2 = _store_record(harness_dir, aid2)
    bad = dict(rec2["correct_pieces"])
    bad.pop("e8", None)  # one missing piece
    filled = set(rec2["correct_pieces"])
    empty_sq = next(
        sq for sq in (f + r for r in "12345678" for f in "abcdefgh") if sq not in filled
    )
    bad[empty_sq] = "wQ"  # one extra phantom piece
    resp2 = client.post(
        f"/api/v1/identify/{aid2}/answer", headers=_auth(key), json={"pieces": bad}
    )
    score2 = resp2.json()["score"]
    assert score2["missing"] == 1
    assert score2["extra"] == 1
    assert score2["full_position"] is False


@pytest.fixture
def capped_identify(identify_client, monkeypatch):
    monkeypatch.setenv("CHESS_HARNESS_MAX_IDENTIFY_ATTEMPTS_PER_KEY", "2")
    return identify_client


def test_abandon_and_cap(capped_identify):
    client, _ = capped_identify
    key = _register(client, "cap-agent")

    first = _start(client, key, rating_min=1100, rating_max=1300)
    second = _start(client, key, rating_min=1400, rating_max=1600)

    blocked = client.post(
        "/api/v1/identify/start", headers=_auth(key), params={"rating_min": 1700, "rating_max": 1900}
    )
    assert blocked.status_code == 429

    abandoned = client.post(
        f"/api/v1/identify/{second['attempt_id']}/abandon", headers=_auth(key)
    )
    assert abandoned.status_code == 200
    assert abandoned.json()["status"] == "abandoned"
    assert abandoned.json()["message"] == "Attempt abandoned"

    allowed = _start(client, key, rating_min=1700, rating_max=1900)
    assert allowed["status"] == "active"

    review = client.get(
        f"/api/v1/identify/{second['attempt_id']}/review", headers=_auth(key)
    ).json()
    assert review["status"] == "abandoned"
    assert "correct_pieces" not in review


def test_ownership_auth_scoped(identify_client):
    client, _ = identify_client
    key_a = _register(client, "owner")
    key_b = _register(client, "intruder")

    start = _start(client, key_a, rating_min=1400, rating_max=1600)
    attempt_id = start["attempt_id"]

    stolen = client.get(
        f"/api/v1/identify/{attempt_id}/board", headers=_auth(key_b)
    )
    assert stolen.status_code == 404

    no_auth = client.get(f"/api/v1/identify/{attempt_id}/board")
    assert no_auth.status_code == 401

    missing = client.get("/api/v1/identify/bi-none/board", headers=_auth(key_a))
    assert missing.status_code == 404

    minted = ChildCredentialStore().mint("game-child-ident", "WHITE", "owner")
    denied = client.post("/api/v1/identify/start", headers=_auth(minted["key"]))
    assert denied.status_code == 403


def test_observer_secrecy_live_and_replay_gate(identify_client):
    client, harness_dir = identify_client
    key = _register(client, "watch-agent")

    active = _start(client, key, rating_min=1400, rating_max=1600)
    attempt_id = active["attempt_id"]

    state = client.get(f"/api/v1/identify/public/{attempt_id}").json()
    assert_identify_no_leak(state)
    assert state["status"] == "active"
    assert state["result"] is None
    assert state["submitted_count"] == 0
    assert state["watch_url"] == f"/i/{attempt_id}"
    assert "accuracy" not in state
    assert "difficulty" not in state

    replay = client.get(f"/api/v1/identify/public/{attempt_id}/replay")
    assert replay.status_code == 409
    assert client.get(f"/i/{attempt_id}/answer.png").status_code == 409

    record = _store_record(harness_dir, attempt_id)
    wrong = dict(record["correct_pieces"])
    wrong["e2"] = "wQ"
    resp = client.post(
        f"/api/v1/identify/{attempt_id}/answer", headers=_auth(key), json={"pieces": wrong}
    )
    assert resp.status_code == 200

    state2 = client.get(f"/api/v1/identify/public/{attempt_id}").json()
    assert_identify_no_leak(state2)
    assert state2["status"] == "finished"
    assert state2["result"] == "failed"
    assert state2["accuracy"] is not None
    assert state2["score"]["full_position"] is False
    assert "difficulty" in state2
    assert "per_square" not in state2

    replay2 = client.get(f"/api/v1/identify/public/{attempt_id}/replay")
    assert replay2.status_code == 200
    rv = replay2.json()
    assert rv["submitted_pieces"] == wrong
    assert rv["correct_pieces"] == record["correct_pieces"]
    assert rv["result"] == "failed"

    answer_png = client.get(f"/i/{attempt_id}/answer.png")
    assert answer_png.status_code == 200
    assert answer_png.headers["content-type"] == "image/png"
    assert answer_png.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_watch_pages_browse_and_media(identify_client):
    client, harness_dir = identify_client
    key = _register(client, "page-agent")

    active = _start(client, key, rating_min=1400, rating_max=1600)
    attempt_id = active["attempt_id"]

    page = client.get(f"/i/{attempt_id}")
    assert page.status_code == 200
    assert page.headers["content-type"].startswith("text/html")
    assert "/js/identify-watch.js" in page.text
    assert "pieces" not in page.text.lower()
    assert 'id="moves-col"' in page.text, "watch page uses the 3-column spectator layout"
    assert "Attempt chain" in page.text
    assert 'id="chain"' in page.text
    assert "Placement review" in page.text

    img = client.get(f"/i/{attempt_id}/board.png")
    assert img.status_code == 200
    assert img.content[:8] == b"\x89PNG\r\n\x1a\n"

    text = client.get(f"/i/{attempt_id}/board.txt")
    assert text.status_code == 200
    assert "side_to_move:" in text.text

    assert client.get("/i/does-not-exist").status_code == 200
    assert client.get("/i/does-not-exist/board.png").status_code == 404

    # Browse: active finished listed, abandoned included for chain honesty, leak-free.
    record = _store_record(harness_dir, attempt_id)
    finished = client.post(
        f"/api/v1/identify/{attempt_id}/answer",
        headers=_auth(key),
        json={"pieces": record["correct_pieces"]},
    )
    assert finished.status_code == 200

    gone = _start(client, key, rating_min=1100, rating_max=1300)
    client.post(f"/api/v1/identify/{gone['attempt_id']}/abandon", headers=_auth(key))

    resp = client.get("/api/v1/identify/public/attempts")
    assert resp.status_code == 200
    rows = resp.json()["attempts"]
    ids = {row["attempt_id"] for row in rows}
    assert attempt_id in ids
    assert gone["attempt_id"] in ids, "abandoned attempts are listed for chain honesty"
    for row in rows:
        assert_identify_no_leak(row)
        assert row["watch_url"].startswith("/i/")
        assert row["model_id"]

    finished_row = next(r for r in rows if r["attempt_id"] == attempt_id)
    assert finished_row["status"] == "finished"
    assert finished_row["result"] == "correct"
    assert finished_row["accuracy"] == 1.0
    assert finished_row["key"]
    assert finished_row["full_position"] is True
    assert finished_row["total_pieces"] > 0
    assert finished_row["difficulty"] == 1500

    active_only = client.get(
        "/api/v1/identify/public/attempts", params={"status": "active"}
    ).json()
    assert all(r["status"] == "active" for r in active_only["attempts"])


def test_public_identify_chain_by_key(identify_client):
    client, _ = identify_client
    key = _register(client, "id-chain-agent")

    first = _start(client, key, rating_min=1100, rating_max=1300)["attempt_id"]
    second = _start(client, key, rating_min=1400, rating_max=1600)["attempt_id"]

    rows = client.get("/api/v1/identify/public/attempts").json()["attempts"]
    chain_key = next(r["key"] for r in rows if r["attempt_id"] == second)
    assert chain_key

    chain = client.get(
        "/api/v1/identify/public/attempts", params={"by_key": chain_key}
    ).json()["attempts"]
    ids = [r["attempt_id"] for r in chain]
    assert ids == [second, first], "chain is newest first"
    for row in chain:
        assert row["key"] == chain_key
        assert_identify_no_leak(row)

    foreign = client.get(
        "/api/v1/identify/public/attempts", params={"by_key": "0" * 16}
    ).json()["attempts"]
    assert foreign == []


def test_identify_by_key_scan_public_rate_limited(identify_client):
    from chess_harness.api_limits import (
        PUBLIC_BY_KEY_LIMIT_PER_IP_PER_HOUR,
    )

    client, _ = identify_client
    key = _register(client, "id-scanner-agent")
    first = _start(client, key, rating_min=1100, rating_max=1300)["attempt_id"]
    rows = client.get("/api/v1/identify/public/attempts").json()["attempts"]
    fingerprint = next(r["key"] for r in rows if r["attempt_id"] == first)
    url = f"/api/v1/identify/public/attempts?by_key={fingerprint}"

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


def test_public_identify_chain_by_agent_fallback(identify_client):
    client, _ = identify_client
    key = _register(client, "id-fallback-agent")

    first = _start(client, key, rating_min=1100, rating_max=1300)["attempt_id"]
    second = _start(client, key, rating_min=1400, rating_max=1600)["attempt_id"]

    rows = client.get(
        "/api/v1/identify/public/attempts", params={"by_agent": "id-fallback-agent"}
    ).json()["attempts"]
    ids = [r["attempt_id"] for r in rows]
    assert second in ids, "by_agent returns both attempts"
    assert first in ids
    for row in rows:
        assert row["agent_name"] == "id-fallback-agent"

    empty = client.get(
        "/api/v1/identify/public/attempts", params={"by_agent": "nobody"}
    ).json()["attempts"]
    assert empty == []


def test_identify_attempts_never_write_results_jsonl(identify_client):
    client, harness_dir = identify_client
    key = _register(client, "id-no-results-agent")
    results_path = harness_dir / "results.jsonl"

    start = _start(client, key)
    attempt_id = start["attempt_id"]
    record = _store_record(harness_dir, attempt_id)
    finished = client.post(
        f"/api/v1/identify/{attempt_id}/answer",
        headers=_auth(key),
        json={"pieces": record["correct_pieces"]},
    )
    assert finished.status_code == 200
    assert finished.json()["status"] == "finished"

    second = _start(client, key)
    abandoned = client.post(
        f"/api/v1/identify/{second['attempt_id']}/abandon", headers=_auth(key)
    )
    assert abandoned.status_code == 200
    assert abandoned.json()["status"] == "abandoned"

    assert not results_path.exists(), "identify attempts must never write results.jsonl"
    assert (harness_dir / "identify_attempts.json").exists()


def test_identify_has_no_move_route(identify_client):
    client, _ = identify_client
    key = _register(client, "id-no-moves-agent")
    start = _start(client, key)
    attempt_id = start["attempt_id"]
    move = client.post(
        f"/api/v1/identify/{attempt_id}/move/e2e4", headers=_auth(key)
    )
    assert move.status_code == 404


def test_prune_idle_active_abandons_stale_attempt(tmp_path):
    import json
    from datetime import datetime, timedelta, timezone

    from chess_harness.identify_attempt import IdentifyAttemptStore

    path = tmp_path / "identify.json"
    stale = (datetime.now(timezone.utc) - timedelta(seconds=4000)).isoformat()
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "attempts": {
                    "bi-stale": {
                        "attempt_id": "bi-stale",
                        "status": "active",
                        "updated_at": stale,
                        "started_at": stale,
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    store = IdentifyAttemptStore(path)
    abandoned = store.prune_idle_active(1800.0)
    assert abandoned == ["bi-stale"]
    record = store.get("bi-stale")
    assert record is not None
    assert record["status"] == "abandoned"


def _stale_identify_attempt(harness_dir, attempt_id: str) -> None:
    from datetime import datetime, timedelta, timezone

    path = harness_dir / "identify_attempts.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    stale = (datetime.now(timezone.utc) - timedelta(seconds=4000)).isoformat()
    record = data["attempts"][attempt_id]
    record["updated_at"] = stale
    record["started_at"] = stale
    path.write_text(json.dumps(data), encoding="utf-8")


def test_identify_board_abandons_idle_attempt_on_read(identify_client):
    from chess_harness.identify_attempt import IdentifyAttemptStore

    client, harness_dir = identify_client
    key = _register(client, "idle-identify-agent")
    start = _start(client, key)
    attempt_id = start["attempt_id"]

    _stale_identify_attempt(harness_dir, attempt_id)

    board = client.get(start["board_url"], headers=_auth(key))
    assert board.status_code == 200

    record = IdentifyAttemptStore().get(attempt_id)
    assert record is not None
    assert record["status"] == "abandoned"

    review = client.get(start["review_url"], headers=_auth(key))
    assert review.status_code == 200
    assert review.json()["status"] == "abandoned"