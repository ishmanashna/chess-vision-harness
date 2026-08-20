"""Tests for chess_harness.runner (Phase 3)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from conftest import LOW_OPPONENT

from chess_harness.agent_http import AgentHttpClient
from chess_harness.results import ResultsManager
from chess_harness.runner.activation import slot_is_active
from chess_harness.runner.config import SlotConfig, load_runner_config
from chess_harness.runner.loop import SlotRunner, run_runner
from chess_harness.runner.probe import run_probe
from chess_harness.runner.probe_state import load_probe_status
from harness_client import auth_headers, testclient_transport


def _testclient_transport(client):
    return testclient_transport(client)


def _write_runner_config(path: Path, *, slots: list[dict], opponent: str | None = LOW_OPPONENT) -> Path:
    slot_rows = []
    for slot in slots:
        row = dict(slot)
        if opponent is not None and "opponent" not in row:
            row["opponent"] = opponent
        if "agent_color" not in row:
            row["agent_color"] = "white"
        slot_rows.append(row)
    payload = {
        "version": 1,
        "max_concurrent_games": 2,
        "harness_base_url": "http://testserver",
        "slots": slot_rows,
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


@pytest.fixture
def runner_env(harness_client, tmp_path):
    client, harness_dir = harness_client
    config_path = tmp_path / "runner_slots.json"
    _write_runner_config(
        config_path,
        slots=[
            {
                "inscribed_id": "runner-stub",
                "provider": "stub",
                "observation": "vision",
                "provider_model": "stub",
                "base_url": "",
                "env_key": "",
                "rpm": 60,
                "rpd": 500,
            }
        ],
    )
    transport = _testclient_transport(client)
    yield {
        "client": client,
        "harness_dir": harness_dir,
        "config_path": config_path,
        "transport": transport,
    }


def test_stub_dry_run_writes_results_row(runner_env):
    outcomes = run_runner(
        config_path=runner_env["config_path"],
        transport=runner_env["transport"],
        harness_dir=runner_env["harness_dir"],
        once=True,
        max_agent_plies=1,
    )
    assert outcomes
    assert outcomes[0]["ok"] is True
    game_id = outcomes[0]["game_id"]
    results = ResultsManager(str(runner_env["harness_dir"])).load_results()
    assert results, "expected results.jsonl row"
    row = results[-1]
    assert row["game_id"] == game_id
    assert row.get("observation") == "vision"
    assert row.get("result") in {"0-1", "1-0", "1/2-1/2", "*"}


def test_runner_probe_without_vendor_env(runner_env, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    config_path = runner_env["config_path"]
    _write_runner_config(
        config_path,
        slots=[
            {
                "inscribed_id": "runner-stub",
                "provider": "stub",
                "observation": "text",
                "provider_model": "stub",
                "base_url": "",
                "env_key": "",
                "rpm": 60,
                "rpd": 500,
            },
            {
                "inscribed_id": "runner-openai",
                "provider": "openai",
                "observation": "text",
                "provider_model": "gpt-test",
                "base_url": "https://example.invalid/v1",
                "env_key": "OPENAI_API_KEY",
                "rpm": 30,
                "rpd": 200,
            },
        ],
    )
    results = run_probe(
        config_path=config_path,
        transport=runner_env["transport"],
        harness_dir=runner_env["harness_dir"],
    )
    by_id = {row["inscribed_id"]: row for row in results}
    assert by_id["runner-stub"]["ok"] is True
    assert by_id["runner-openai"]["ok"] is False

    config = load_runner_config(config_path)
    probe_status = load_probe_status(runner_env["harness_dir"] / "runner" / "probe_status.json")
    stub_slot = config.slots[0]
    openai_slot = config.slots[1]
    assert slot_is_active(stub_slot, probe_status) is True
    assert slot_is_active(openai_slot, probe_status) is False


def test_runner_kill_restart_continues(runner_env):
    transport = runner_env["transport"]
    harness_dir = runner_env["harness_dir"]
    config_path = runner_env["config_path"]
    config = load_runner_config(config_path)
    slot = config.slots[0]

    from chess_harness.runner.keys import ensure_harness_key
    from chess_harness.runner.slot_worker import play_game
    from chess_harness.runner.adapters.stub import StubAdapter
    from chess_harness.runner.quota import QuotaTracker
    from chess_harness.runner.log import RunnerLog

    api_key = ensure_harness_key(
        base_url="http://testserver",
        inscribed_id=slot.inscribed_id,
        observation=slot.observation,
        transport=transport,
        path=harness_dir / "runner" / "keys.json",
    )
    http = AgentHttpClient(
        "http://testserver",
        api_key,
        model_id=slot.inscribed_id,
        transport=transport,
        queue_path=harness_dir / "runner" / "queue.json",
    )
    created = http.create_game(opponent=LOW_OPPONENT, agent_color="white")
    game_id = created["game_id"]
    http.move(game_id, "e2e4")
    assert (harness_dir / "runner" / "queue.json").is_file()

    restarted = SlotRunner(
        config,
        transport=transport,
        harness_dir=harness_dir,
        max_agent_plies=1,
    )
    restarted.reconcile_all()
    adapter = StubAdapter(moves=["g1f3"])
    logger = RunnerLog(harness_dir / "runner" / "runner.jsonl")
    quota = QuotaTracker(rpm=slot.rpm, rpd=slot.rpd)
    client = restarted._client_for(slot)
    outcome = play_game(
        client,
        adapter,
        slot,
        quota,
        logger,
        game_id=game_id,
        max_agent_plies=1,
    )
    assert outcome["game_id"] == game_id
    assert outcome["ok"] is True


def test_runner_rpd_stops_without_live_game(runner_env):
    config_path = runner_env["config_path"]
    _write_runner_config(
        config_path,
        slots=[
            {
                "inscribed_id": "runner-stub-rpd",
                "provider": "stub",
                "observation": "text",
                "provider_model": "stub",
                "base_url": "",
                "env_key": "",
                "rpm": 60,
                "rpd": 1,
            }
        ],
    )
    transport = runner_env["transport"]
    harness_dir = runner_env["harness_dir"]
    runner = SlotRunner(
        load_runner_config(config_path),
        transport=transport,
        harness_dir=harness_dir,
        max_agent_plies=1,
    )

    first = runner.run_once()
    assert first[0]["ok"] is True

    listed = runner_env["client"].get(
        "/api/v1/games",
        headers=auth_headers(
            json.loads((harness_dir / "runner" / "keys.json").read_text())["runner-stub-rpd"]
        ),
    )
    assert listed.json()["games"] == []

    second = runner.run_once()
    assert second[0]["reason"] == "quota"


def test_illegal_model_output_logged_and_next_game(runner_env):
    from chess_harness.runner.adapters.stub import StubAdapter
    from chess_harness.runner.config import load_runner_config
    from chess_harness.runner.keys import ensure_harness_key
    from chess_harness.runner.log import RunnerLog
    from chess_harness.runner.quota import QuotaTracker
    from chess_harness.runner.slot_worker import play_game

    config = load_runner_config(runner_env["config_path"])
    slot = config.slots[0]
    api_key = ensure_harness_key(
        base_url="http://testserver",
        inscribed_id=slot.inscribed_id,
        observation=slot.observation,
        transport=runner_env["transport"],
        path=runner_env["harness_dir"] / "runner" / "keys.json",
    )
    http = AgentHttpClient(
        "http://testserver",
        api_key,
        model_id=slot.inscribed_id,
        transport=runner_env["transport"],
        queue_path=runner_env["harness_dir"] / "runner" / "queue.json",
    )
    logger = RunnerLog(runner_env["harness_dir"] / "runner" / "runner.jsonl")
    quota = QuotaTracker(rpm=60, rpd=500)
    illegal = StubAdapter(moves=["xxxx"])
    outcome = play_game(http, illegal, slot, quota, logger)
    assert outcome["reason"] == "illegal_move"
    assert (runner_env["harness_dir"] / "runner" / "runner.jsonl").is_file()

    legal = StubAdapter(moves=["e2e4"])
    outcome2 = play_game(http, legal, slot, quota, logger, max_agent_plies=1)
    assert outcome2["ok"] is True
