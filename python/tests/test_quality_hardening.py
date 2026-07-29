"""Phase 7 hardening: quality path never touches ladder Elo."""

from __future__ import annotations

import ast
import importlib
import importlib.util
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from chess_harness.commands import cmd_analyse_quality
from chess_harness.game_manager import GameManager
from chess_harness.game_quality import GameQuality, SideQuality
from chess_harness.game_types import GAME_TYPE_HUMAN_VS_AGENT
from chess_harness.quality_finish import run_game_quality

_QUALITY_MODULES = (
    "chess_harness.game_quality",
    "chess_harness.play_rating",
    "chess_harness.quality_finish",
)

_BANNED_IMPORT_ROOTS = frozenset(
    {
        "chess_harness.elo",
        "chess_harness.models",
        "calibration.ratings",
    }
)


def _module_top_level_imports(module_name: str) -> set[str]:
    spec = importlib.util.find_spec(module_name.split(".", 1)[0])
    if spec is None or spec.origin is None:
        pytest.skip(f"cannot locate {module_name}")
    root = Path(spec.origin).resolve().parent
    rel = module_name.split(".", 1)[1]
    path = root / rel.replace(".", "/")
    path = path.with_suffix(".py")
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_quality_modules_avoid_elo_import_roots():
    for module_name in _QUALITY_MODULES:
        imports = _module_top_level_imports(module_name)
        hits = sorted(i for i in imports if i in _BANNED_IMPORT_ROOTS)
        assert hits == [], f"{module_name} top-level imports banned roots: {hits}"


def _side(accuracy: float) -> SideQuality:
    return SideQuality(
        accuracy=accuracy,
        acpl=10.0,
        normalized_acpl=0.1,
        blunder_rate=0.0,
        move_count=6,
    )


def _stub_quality() -> GameQuality:
    return GameQuality(
        quality_depth=8,
        quality_thin=False,
        white=_side(88.0),
        black=_side(90.0),
    )


def _write_finished_game(tmp_path, game_id: str = "ave-q") -> tuple[GameManager, str]:
    base = tmp_path / "harness"
    gm = GameManager(base_dir=str(base))
    state = {
        "game_id": game_id,
        "game_type": GAME_TYPE_HUMAN_VS_AGENT,
        "status": "finished",
        "result": "1-0",
        "model_name": "agent-a",
        "agent_color": "WHITE",
        "moves": ["e2e4"],
        "pgn_headers": {"Result": "1-0"},
        "board_fen": "start",
    }
    gm.save_state(game_id, state)
    game_dir = gm.get_game_dir(game_id)
    game_dir.mkdir(parents=True, exist_ok=True)
    pgn = (
        '[Event "Test"]\n[White "A"]\n[Black "B"]\n[Result "1-0"]\n\n'
        "1. e2e4 e7e5 2. g1f3 1-0"
    )
    gm.get_pgn_path(game_id).write_text(pgn, encoding="utf-8")
    models_file = base / "models.json"
    models_file.write_text(
        json.dumps({"models": [{"id": "agent-a", "name": "Agent A", "elo": 555.0}]}),
        encoding="utf-8",
    )
    return gm, str(base)


@patch("chess_harness.elo.ELOLadder.record_game")
@patch("chess_harness.quality_finish.analyse_game")
def test_run_game_quality_never_records_elo(mock_analyse, mock_record, tmp_path):
    mock_analyse.return_value = _stub_quality()
    gm, base = _write_finished_game(tmp_path)
    game_id = "ave-q"

    assert run_game_quality(game_id, base_dir=base) is True
    mock_record.assert_not_called()
    models = json.loads((Path(base) / "models.json").read_text(encoding="utf-8"))
    assert models["models"][0]["elo"] == 555.0


@patch("chess_harness.quality_finish.analyse_game")
def test_cmd_analyse_quality_backfill_one_game(mock_analyse, tmp_path, monkeypatch):
    mock_analyse.return_value = _stub_quality()
    gm, base = _write_finished_game(tmp_path, "backfill-1")
    monkeypatch.setenv("CHESS_HARNESS_BASE", str(Path(base).parent))

    from chess_harness.game_manager import GameManager as GM

    monkeypatch.setattr(
        "chess_harness.commands._game_manager",
        lambda: GM(base_dir=base),
    )

    rc = cmd_analyse_quality(game_id="backfill-1")
    assert rc == 0
    saved = gm.load_state("backfill-1")
    assert saved["quality_at"]
    assert saved["agent_accuracy"] == 88.0


@patch("chess_harness.quality_finish.analyse_game")
def test_cmd_analyse_quality_force_redo(mock_analyse, tmp_path, monkeypatch):
    first = _stub_quality()
    second = GameQuality(
        quality_depth=8,
        quality_thin=False,
        white=_side(70.0),
        black=_side(72.0),
    )
    mock_analyse.side_effect = [first, second]
    gm, base = _write_finished_game(tmp_path, "backfill-2")
    monkeypatch.setattr(
        "chess_harness.commands._game_manager",
        lambda: GameManager(base_dir=base),
    )

    assert cmd_analyse_quality(game_id="backfill-2") == 0
    assert gm.load_state("backfill-2")["agent_accuracy"] == 88.0

    assert cmd_analyse_quality(game_id="backfill-2", force=True) == 0
    assert gm.load_state("backfill-2")["agent_accuracy"] == 70.0
