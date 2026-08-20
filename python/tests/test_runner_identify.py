"""Tests for identify agent_http loops and runner kind=identify slots."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from chess_harness.agent_http import AgentHttpClient
from chess_harness.runner.adapters.stub import StubAdapter
from chess_harness.runner.config import load_runner_config
from chess_harness.runner.keys import ensure_harness_key
from chess_harness.runner.log import RunnerLog
from chess_harness.runner.loop import run_runner
from chess_harness.runner.quota import QuotaTracker
from chess_harness.runner.slot_worker_identify import play_identify_attempt
from harness_client import testclient_transport
from puzzle_test_data import import_test_puzzles


def _testclient_transport(client):
    return testclient_transport(client)


def _write_runner_config(path: Path, *, observation: str = "text") -> Path:
    payload = {
        "version": 1,
        "max_concurrent_games": 2,
        "harness_base_url": "http://testserver",
        "slots": [
            {
                "inscribed_id": "runner-identify-stub",
                "kind": "identify",
                "provider": "stub",
                "observation": observation,
                "provider_model": "stub",
                "base_url": "",
                "env_key": "",
                "rpm": 60,
                "rpd": 500,
                "identify_rating_min": 1400,
                "identify_rating_max": 1600,
            }
        ],
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


@pytest.fixture
def identify_runner_env(harness_client, tmp_path):
    client, harness_dir = harness_client
    import_test_puzzles()
    config_path = _write_runner_config(tmp_path / "runner_slots.json")
    transport = _testclient_transport(client)
    api_key = ensure_harness_key(
        base_url="http://testserver",
        inscribed_id="runner-identify-stub",
        observation="text",
        transport=transport,
        path=harness_dir / "runner" / "keys.json",
    )
    http = AgentHttpClient(
        "http://testserver",
        api_key,
        model_id="runner-identify-stub",
        transport=transport,
    )
    yield {
        "client": client,
        "harness_dir": harness_dir,
        "config_path": config_path,
        "transport": transport,
        "http": http,
    }


def test_runner_kind_identify_finishes_attempt(identify_runner_env):
    outcomes = run_runner(
        config_path=identify_runner_env["config_path"],
        transport=identify_runner_env["transport"],
        harness_dir=identify_runner_env["harness_dir"],
        once=True,
    )
    assert outcomes
    assert outcomes[0]["ok"] is True
    assert outcomes[0]["attempt_id"]
    assert outcomes[0]["status"] == "finished"
    assert outcomes[0]["result"] in {"correct", "failed"}


def test_play_identify_attempt_text_observation(identify_runner_env):
    slot = load_runner_config(identify_runner_env["config_path"]).slots[0]
    adapter = StubAdapter()
    logger = RunnerLog(identify_runner_env["harness_dir"] / "runner" / "runner.jsonl")
    quota = QuotaTracker(rpm=60, rpd=500)
    outcome = play_identify_attempt(
        identify_runner_env["http"],
        adapter,
        slot,
        quota,
        logger,
    )
    assert outcome["ok"] is True
    assert outcome["status"] == "finished"
    assert outcome["result"] == "correct"
    assert outcome["review"]["result"] == "correct"


def test_play_identify_attempt_vision_observation(identify_runner_env, tmp_path):
    config_path = _write_runner_config(tmp_path / "vision_slots.json", observation="vision")
    slot = load_runner_config(config_path).slots[0]
    reg = identify_runner_env["client"].post(
        "/api/v1/agents",
        json={"id": "vision-identify-agent", "observation": "vision"},
    )
    api_key = reg.json()["api_key"]
    http = AgentHttpClient(
        "http://testserver",
        api_key,
        model_id="vision-identify-agent",
        transport=identify_runner_env["transport"],
    )
    png_seen: list[bytes] = []
    original_fetch = http.fetch_identify_observation

    def track_fetch(attempt_id: str, observation: str):
        payload = original_fetch(attempt_id, observation)
        if payload.get("board_png"):
            png_seen.append(payload["board_png"])
        return payload

    http.fetch_identify_observation = track_fetch  # type: ignore[method-assign]
    adapter = StubAdapter()
    logger = RunnerLog(identify_runner_env["harness_dir"] / "runner" / "vision.jsonl")
    quota = QuotaTracker(rpm=60, rpd=500)
    outcome = play_identify_attempt(http, adapter, slot, quota, logger)
    assert outcome["ok"] is True
    assert outcome["status"] == "finished"
    assert png_seen and png_seen[0][:8] == b"\x89PNG\r\n\x1a\n"
