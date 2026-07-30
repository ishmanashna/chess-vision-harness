import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from chess_harness.elo import ELOLadder
from chess_harness.results import ResultsManager


def test_elo_change_for_game_replay(tmp_path, monkeypatch):
    base = tmp_path / "chess_harness"
    base.mkdir()
    models_file = tmp_path / "models.json"
    models_file.write_text(
        (
            '{"models":[{"id":"composer-2.5","name":"C","inscribed":"x","elo":500}]}\n'
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("chess_harness.models.resolve_models_file", lambda: models_file)
    results = base / "results.jsonl"
    results.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "game_id": "g1",
                        "model_name": "composer-2.5",
                        "skill": -3,
                        "agent_color": "WHITE",
                        "result": "0-1",
                    }
                ),
                json.dumps(
                    {
                        "game_id": "g2",
                        "model_name": "composer-2.5",
                        "skill": -3,
                        "agent_color": "WHITE",
                        "result": "0-1",
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    ladder = ELOLadder(base_dir=str(base))
    d1 = ladder.elo_change_for_game("g1")
    d2 = ladder.elo_change_for_game("g2")
    assert d1 is not None
    assert d2 is not None
    assert d1["elo_before"] == 500
    assert d2["elo_before"] == d1["elo_after"]


def test_count_by_model(tmp_path, monkeypatch):
    base = tmp_path / "chess_harness"
    base.mkdir()
    models_file = tmp_path / "models.json"
    models_file.write_text(
        json.dumps(
            {
                "models": [
                    {"id": "composer-2.5", "name": "C", "inscribed": "x", "elo": 500},
                    {"id": "mimo-v2.5", "name": "M", "inscribed": "x", "elo": 500},
                ]
            }
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("chess_harness.models.resolve_models_file", lambda: models_file)

    results = base / "results.jsonl"
    results.write_text(
        json.dumps(
            {
                "game_id": "g1",
                "model_name": "composer-2.5",
                "skill": 1,
                "agent_color": "WHITE",
                "result": "0-1",
            }
        )
        + "\n"
        + json.dumps(
            {
                "game_id": "g2",
                "model_name": "mimo-v2.5",
                "skill": 1,
                "agent_color": "WHITE",
                "result": "1-0",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    counts = ResultsManager(base_dir=str(base)).count_by_model()
    assert counts["composer-2.5"] == 1
    assert counts["mimo-v2.5"] == 1


def test_count_by_model_skips_no_result(tmp_path, monkeypatch):
    base = tmp_path / "chess_harness"
    base.mkdir()
    models_file = base / "models.json"
    models_file.write_text(
        json.dumps(
            {
                "models": [
                    {"id": "agent-a", "name": "A", "inscribed": "x", "elo": 500},
                ]
            }
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("chess_harness.models.resolve_models_file", lambda: models_file)

    results = base / "results.jsonl"
    results.write_text(
        json.dumps(
            {
                "game_id": "rated",
                "model_name": "agent-a",
                "skill": 1,
                "agent_color": "WHITE",
                "result": "1-0",
            }
        )
        + "\n"
        + json.dumps(
            {
                "game_id": "idle",
                "model_name": "agent-a",
                "skill": 1,
                "agent_color": "WHITE",
                "result": "*",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    counts = ResultsManager(base_dir=str(base)).count_by_model()
    assert counts["agent-a"] == 1
