"""Tests for chess_harness.agent_http and Phase 2 reconnect plumbing."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from conftest import LOW_OPPONENT

from chess_harness.agent_http import AgentHttpClient, AgentHttpError, DEFAULT_USER_AGENT
from chess_harness.agent_http.transport import request_with_retries
from chess_harness.game_manager import GameManager
from harness_client import auth_headers, testclient_transport
from leak_guards import assert_game_api_no_leaks


def _testclient_transport(client):
    return testclient_transport(client)


@pytest.fixture
def agent_http_env(harness_client):
    client, harness_dir = harness_client
    reg = client.post("/api/v1/agents", json={"id": "http-agent", "name": "HTTP Agent"})
    assert reg.status_code == 200
    api_key = reg.json()["api_key"]
    queue_path = harness_dir / "runner" / "queue.json"
    http = AgentHttpClient(
        "http://testserver",
        api_key,
        model_id="http-agent",
        transport=_testclient_transport(client),
        queue_path=queue_path,
    )
    yield http, client, harness_dir, api_key


def test_agent_http_resume_after_restart(agent_http_env):
    http, client, harness_dir, api_key = agent_http_env

    created = http.create_game(opponent=LOW_OPPONENT, agent_color="white")
    game_id = created["game_id"]
    assert game_id
    assert (harness_dir / "runner" / "queue.json").is_file()

    obs = http.fetch_observation(game_id, created.get("observation") or "vision")
    assert "board_text" in obs
    assert obs["board_png"][:8] == b"\x89PNG\r\n\x1a\n"

    first = http.move(game_id, "e2e4")
    assert first["ok"] is True

    restarted = AgentHttpClient(
        "http://testserver",
        api_key,
        model_id="http-agent",
        transport=_testclient_transport(client),
        queue_path=harness_dir / "runner" / "queue.json",
    )
    entries = restarted.resume_entries()
    assert len(entries) == 1
    assert entries[0].game_id == game_id

    second = restarted.move(game_id, "g1f3")
    assert second["ok"] is True
    assert second.get("your_turn") is True


def test_agent_http_user_agent_not_urllib(agent_http_env):
    http, client, _harness_dir, _api_key = agent_http_env
    seen = {}

    def capture_transport(method, url, headers, body=None):
        seen["user_agent"] = headers.get("User-Agent")
        return _testclient_transport(client)(method, url, headers, body)

    http._transport = capture_transport
    http.list_games()
    assert seen["user_agent"] == DEFAULT_USER_AGENT
    assert "Python-urllib" not in seen["user_agent"]


def test_agent_http_retries_429(monkeypatch):
    calls = {"count": 0}

    def flaky_transport(method, url, headers, body=None):
        calls["count"] += 1
        if calls["count"] == 1:
            return 429, {}, b'{"ok": false, "error": "slow down"}'
        return 200, {}, b'{"ok": true, "games": []}'

    sleeps = []
    monkeypatch.setattr("chess_harness.agent_http.transport.time.sleep", sleeps.append)

    status, _headers, content = request_with_retries(
        flaky_transport, "GET", "http://example/api/v1/games", {"User-Agent": "test"}
    )
    assert status == 200
    assert json.loads(content.decode())["ok"] is True
    assert calls["count"] == 2
    assert sleeps == [1.0]


def test_prune_idle_on_status_get(api_client, monkeypatch):
    client, harness_dir = api_client
    monkeypatch.setenv("CHESS_HARNESS_IDLE_TIMEOUT_SEC", "60")

    reg = client.post("/api/v1/agents", json={"id": "idle-prune-agent"})
    api_key = reg.json()["api_key"]
    create = client.post(
        "/api/v1/games",
        headers=auth_headers(api_key),
        json={"opponent": LOW_OPPONENT, "agent_color": "white"},
    )
    game_id = create.json()["game_id"]

    gm = GameManager(str(harness_dir))
    state = gm.load_state(game_id)
    stale = datetime.now(timezone.utc) - timedelta(seconds=120)
    state["last_activity"] = stale.isoformat()
    gm.save_state(game_id, state)

    status = client.get(f"/api/v1/games/{game_id}/status", headers=auth_headers(api_key))
    assert status.status_code == 200
    data = status.json()
    assert data["game_over"] is True
    assert data["result"] == "*"
    assert gm.load_state(game_id)["status"] == "finished"


def test_prune_idle_on_board_get(api_client, monkeypatch):
    client, harness_dir = api_client
    monkeypatch.setenv("CHESS_HARNESS_IDLE_TIMEOUT_SEC", "60")

    reg = client.post("/api/v1/agents", json={"id": "idle-board-agent"})
    api_key = reg.json()["api_key"]
    create = client.post(
        "/api/v1/games",
        headers=auth_headers(api_key),
        json={"opponent": LOW_OPPONENT, "agent_color": "white"},
    )
    game_id = create.json()["game_id"]

    gm = GameManager(str(harness_dir))
    state = gm.load_state(game_id)
    stale = datetime.now(timezone.utc) - timedelta(seconds=120)
    state["last_activity"] = stale.isoformat()
    gm.save_state(game_id, state)

    board = client.get(f"/api/v1/games/{game_id}/board.txt", headers=auth_headers(api_key))
    assert board.status_code == 200
    assert gm.load_state(game_id)["result"] == "*"


def test_api_v1_list_games_for_key(api_client):
    client, _harness_dir = api_client
    reg = client.post(
        "/api/v1/agents",
        json={"id": "list-agent", "observation": "text"},
    )
    api_key = reg.json()["api_key"]
    other = client.post("/api/v1/agents", json={"id": "list-other"})
    other_key = other.json()["api_key"]

    create = client.post(
        "/api/v1/games",
        headers=auth_headers(api_key),
        json={"opponent": LOW_OPPONENT, "agent_color": "white"},
    )
    game_id = create.json()["game_id"]

    listed = client.get("/api/v1/games", headers=auth_headers(api_key))
    assert listed.status_code == 200
    payload = listed.json()
    assert payload["ok"] is True
    assert len(payload["games"]) == 1
    row = payload["games"][0]
    assert row["game_id"] == game_id
    assert row["observation"] == "text"
    assert row["your_turn"] is True
    assert row["game_over"] is False
    assert_game_api_no_leaks(payload)

    denied = client.get("/api/v1/games", headers=auth_headers(other_key))
    assert denied.status_code == 200
    assert denied.json()["games"] == []

    finished = client.post(
        f"/api/v1/games/{game_id}/resign",
        headers=auth_headers(api_key),
    )
    assert finished.status_code == 200

    in_progress_only = client.get("/api/v1/games", headers=auth_headers(api_key))
    assert in_progress_only.json()["games"] == []

    with_finished = client.get(
        "/api/v1/games?include_finished=1",
        headers=auth_headers(api_key),
    )
    assert with_finished.status_code == 200
    done = with_finished.json()["games"]
    assert len(done) == 1
    assert done[0]["game_over"] is True
    assert done[0]["your_turn"] is False


def _import_puzzle_corpus():
    from puzzle_test_data import import_test_puzzles

    import_test_puzzles()


def _play_puzzle_with_client(http: AgentHttpClient, moves: list[str], observation: str) -> dict:
    from chess_harness.runner.adapters.stub import StubAdapter
    from chess_harness.runner.config import SlotConfig
    from chess_harness.runner.log import RunnerLog
    from chess_harness.runner.quota import QuotaTracker
    from chess_harness.runner.slot_worker_puzzles import play_puzzle_attempt

    slot = SlotConfig(
        inscribed_id=http.model_id,
        provider="stub",
        observation=observation,
        provider_model="stub",
        base_url="",
        env_key="",
        rpm=60,
        rpd=500,
        kind="puzzles",
        puzzle_rating_min=1400,
        puzzle_rating_max=1600,
    )
    adapter = StubAdapter(moves=moves)
    logger = RunnerLog(http.queue_path.parent / "puzzle-agent.jsonl")
    quota = QuotaTracker(rpm=60, rpd=500)
    return play_puzzle_attempt(http, adapter, slot, quota, logger)


def test_agent_http_puzzle_text_attempt_completes(agent_http_env):
    http, client, harness_dir, _api_key = agent_http_env
    _import_puzzle_corpus()
    outcome = _play_puzzle_with_client(http, ["e7e5", "g8f6"], "text")
    assert outcome["ok"] is True
    assert outcome["status"] == "finished"
    assert outcome["result"] == "correct"


def test_agent_http_puzzle_vision_attempt_completes(agent_http_env):
    http, client, harness_dir, api_key = agent_http_env
    _import_puzzle_corpus()
    reg = client.post(
        "/api/v1/agents",
        json={"id": "vision-puzzle-http", "observation": "vision"},
    )
    vision_key = reg.json()["api_key"]
    vision_http = AgentHttpClient(
        "http://testserver",
        vision_key,
        model_id="vision-puzzle-http",
        transport=http._transport,
        queue_path=harness_dir / "runner" / "vision-queue.json",
    )
    png_seen: list[bytes] = []
    original_fetch = vision_http.fetch_puzzle_observation

    def track_fetch(attempt_id: str, observation: str):
        payload = original_fetch(attempt_id, observation)
        if payload.get("board_png"):
            png_seen.append(payload["board_png"])
        return payload

    vision_http.fetch_puzzle_observation = track_fetch  # type: ignore[method-assign]
    outcome = _play_puzzle_with_client(vision_http, ["e7e5", "g8f6"], "vision")
    assert outcome["ok"] is True
    assert outcome["status"] == "finished"
    assert png_seen and png_seen[0][:8] == b"\x89PNG\r\n\x1a\n"


def test_agent_http_puzzle_wrong_move_ends_attempt(agent_http_env):
    http, _client, _harness_dir, _api_key = agent_http_env
    _import_puzzle_corpus()
    outcome = _play_puzzle_with_client(http, ["a7a6"], "text")
    assert outcome["ok"] is True
    assert outcome["status"] == "finished"
    assert outcome["result"] == "failed"
    assert outcome["review"]["failure_reason"] == "wrong_move"


def test_agent_http_puzzle_review_not_used_before_finish(agent_http_env):
    http, _client, harness_dir, _api_key = agent_http_env
    _import_puzzle_corpus()
    review_calls: list[str] = []
    original_review = http.puzzle_review

    def tracked_review(attempt_id: str):
        review_calls.append(attempt_id)
        return original_review(attempt_id)

    http.puzzle_review = tracked_review  # type: ignore[method-assign]

    started = http.start_puzzle(rating_min=1400, rating_max=1600)
    attempt_id = started["attempt_id"]
    obs = http.fetch_puzzle_observation(attempt_id, "text")
    assert review_calls == []

    move1 = http.puzzle_move(attempt_id, "e7e5")
    assert move1["status"] == "active"
    assert review_calls == []

    move2 = http.puzzle_move(attempt_id, "g8f6")
    assert move2["status"] == "finished"
    assert review_calls == []

    review = http.puzzle_review(attempt_id)
    assert review_calls == [attempt_id]
    assert review["result"] == "correct"
