"""Tests for inscribed model registry."""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from chess_harness import commands
from chess_harness.models import ModelRegistry


def test_resolve_agent_color_explicit():
    assert commands.resolve_agent_color("white") == "white"
    assert commands.resolve_agent_color("black") == "black"
    assert commands.resolve_agent_color("random") in ("white", "black")
    assert commands.resolve_agent_color(None) in ("white", "black")


def test_inscribe_and_list(tmp_path):
    models_file = tmp_path / "models.json"
    registry = ModelRegistry(models_file)
    entry = registry.inscribe("test-model", "Test Model")
    assert entry["id"] == "test-model"
    assert entry["elo"] == 500
    assert len(registry.list_ids()) == 1


def test_resolve_alias():
    registry = ModelRegistry()
    assert registry.resolve("Composer 2.5") == "composer-2.5"
    assert registry.resolve("composer-2.5") == "composer-2.5"


def test_missing_model_raises():
    registry = ModelRegistry()
    with pytest.raises(ValueError, match="inscribed model"):
        registry.resolve(None)


def test_new_game_requires_inscribed_model(tmp_path):
    os.environ.setdefault(
        "STOCKFISH_PATH",
        os.path.join(
            os.path.dirname(__file__), "..", "bin", "stockfish-windows-x86-64.exe"
        ),
    )
    from chess_harness.board_controller import BoardController
    from chess_harness.engine import StockfishAdapter
    from chess_harness.game_manager import GameManager

    gm = GameManager(base_dir=str(tmp_path / "harness"))
    eng = StockfishAdapter()
    ctrl = BoardController(gm, eng)
    try:
        r = ctrl.new_game("x1", "white", 5)
        assert not r["ok"]
        assert "inscribed" in r["error"].lower()
        r2 = ctrl.new_game("x2", "white", 5, model_name="composer-2.5")
        assert r2["ok"]
        assert "board_path" in r2
    finally:
        eng.quit()
