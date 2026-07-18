"""Tests for unified model/ELO storage and operator maintenance commands."""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from chess_harness.elo import AGENT_START_ELO, ELOLadder
from chess_harness.harness_reset import harness_reset
from chess_harness.models import ModelRegistry


def test_inscribe_sets_elo_on_model_entry(tmp_path):
    models_file = tmp_path / "models.json"
    registry = ModelRegistry(models_file)
    entry = registry.inscribe("agent-a", "Agent A")
    assert entry["elo"] == AGENT_START_ELO

    saved = json.loads(models_file.read_text(encoding="utf-8"))
    assert saved["models"][0]["elo"] == AGENT_START_ELO


def test_record_game_updates_models_json(tmp_path):
    models_file = tmp_path / "models.json"
    base = tmp_path / "harness"
    base.mkdir()
    registry = ModelRegistry(models_file)
    registry.inscribe("agent-a", "Agent A")

    ladder = ELOLadder(base_dir=str(base), registry=registry)
    delta = ladder.record_game("agent-a", 800, "0-1", "WHITE")
    assert delta is not None
    assert delta["elo_before"] == AGENT_START_ELO
    assert registry.get_elo("agent-a") != AGENT_START_ELO

    saved = json.loads(models_file.read_text(encoding="utf-8"))
    assert saved["models"][0]["elo"] == registry.get_elo("agent-a")


def test_migrate_legacy_elo_json_into_models(tmp_path, monkeypatch):
    base = tmp_path / "harness"
    base.mkdir()
    models_file = tmp_path / "models.json"
    models_file.write_text(
        json.dumps(
            {
                "models": [
                    {"id": "agent-a", "name": "Agent A", "inscribed": "2026-07-11"}
                ]
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (base / "elo.json").write_text(json.dumps({"agent-a": 777}), encoding="utf-8")

    monkeypatch.setattr("chess_harness.models.resolve_models_file", lambda: models_file)
    monkeypatch.setattr("chess_harness.models.resolve_base_dir", lambda: base)

    registry = ModelRegistry(models_file)
    assert registry.get_elo("agent-a") == 777.0


def test_uninscribe_removes_model(tmp_path):
    models_file = tmp_path / "models.json"
    registry = ModelRegistry(models_file)
    registry.inscribe("agent-a", "Agent A")
    removed = registry.uninscribe("agent-a")
    assert removed["id"] == "agent-a"
    assert registry.list_ids() == []


def test_harness_reset_wipes_runtime_data(tmp_path, monkeypatch):
    base = tmp_path / "harness"
    games = base / "games" / "g1"
    games.mkdir(parents=True)
    (games / "state.json").write_text('{"status": "in_progress"}', encoding="utf-8")
    (base / "results.jsonl").write_text('{"game_id":"g1"}\n', encoding="utf-8")
    (base / "elo.json").write_text('{"agent-a": 900}', encoding="utf-8")

    models_file = tmp_path / "models.json"
    models_file.write_text(
        json.dumps({"models": [{"id": "agent-a", "name": "A", "inscribed": "x", "elo": 500}]})
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr("chess_harness.harness_reset.resolve_base_dir", lambda: base)
    monkeypatch.setattr("chess_harness.paths.resolve_base_dir", lambda: base)
    monkeypatch.setattr("chess_harness.game_manager.resolve_base_dir", lambda: base)
    monkeypatch.setattr("chess_harness.models.resolve_models_file", lambda: models_file)

    assert harness_reset(confirm=False) == 1
    assert (base / "games" / "g1").exists()
    assert models_file.exists()

    assert harness_reset(confirm=True) == 0
    assert not (base / "games" / "g1").exists()
    assert (base / "results.jsonl").read_text(encoding="utf-8") == ""
    assert not (base / "elo.json").exists()
    assert json.loads(models_file.read_text(encoding="utf-8"))["models"] == []


def test_process_results_file_resets_model_elo_from_scratch(tmp_path):
    models_file = tmp_path / "models.json"
    base = tmp_path / "harness"
    base.mkdir()
    registry = ModelRegistry(models_file)
    registry.inscribe("agent-a", "Agent A")
    registry.set_elo("agent-a", 999)

    results = base / "results.jsonl"
    results.write_text(
        json.dumps(
            {
                "game_id": "g1",
                "model_name": "agent-a",
                "opponent_elo": 800,
                "agent_color": "WHITE",
                "result": "1-0",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    ladder = ELOLadder(base_dir=str(base), registry=registry)
    ladder.process_results_file()
    assert registry.get_elo("agent-a") > AGENT_START_ELO
    assert registry.get_elo("agent-a") != 999
