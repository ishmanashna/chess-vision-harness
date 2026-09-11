"""Tests for prompt-test start (Phase 3)."""

from __future__ import annotations

import shutil
from pathlib import Path

from chess_harness.game_manager import GameManager
from chess_harness.paths import project_root
from chess_harness.prompt_test import cmd_prompt_test_start

from conftest import FIXTURES


def _harness_setup(tmp_path, monkeypatch) -> Path:
    harness_dir = tmp_path / "harness"
    harness_dir.mkdir()
    shutil.copy(FIXTURES / "models.json", harness_dir / "models.json")
    monkeypatch.setenv("CHESS_HARNESS_DIR", str(harness_dir))
    monkeypatch.setenv("MODELS_FILE", str(harness_dir / "models.json"))
    return harness_dir


def _packed_game_count(harness_dir: Path) -> int:
    count = 0
    for entry in GameManager(str(harness_dir)).list_games():
        if entry["state"].get("prompt_pack"):
            count += 1
    return count


def _rules_snippet() -> str:
    return (project_root() / "config" / "prompt_packs" / "_rules.txt").read_text(
        encoding="utf-8"
    ).splitlines()[0]


PACK_MARKERS = {
    "a": "Each turn",
    "b": "Where is every piece",
    "c": "Play real chess",
    "d": "sounds like chess",
    "f": "chess-harness legal",
    "g": "chess-harness imagine",
}


def _assert_brief_ok(game: dict, model_id: str) -> None:
    brief = game["brief"]
    pack_id = game["prompt_pack"]
    if pack_id in ("a", "b", "c", "d"):
        assert _rules_snippet() in brief
    assert PACK_MARKERS[pack_id] in brief
    assert game["game_id"] in brief
    assert game["board_path"] in brief
    assert model_id in brief
    assert game["prompt_pack"] in brief
    assert "{game_id}" not in brief
    assert "{board_path}" not in brief
    assert "{model_id}" not in brief
    assert "{prompt_pack}" not in brief
    assert game["kind"] == "overlay"
    assert game["model"] == model_id
    assert game["agent_color"] == "WHITE"


def test_prompt_test_start_abcd(tmp_path, monkeypatch):
    harness_dir = _harness_setup(tmp_path, monkeypatch)
    model_id = "composer-2.5"
    before = _packed_game_count(harness_dir)

    result = cmd_prompt_test_start(
        model_id,
        ["a", "b", "c", "d"],
        opponent="random",
    )

    assert result["ok"] is True
    assert len(result["games"]) == 4
    assert [g["prompt_pack"] for g in result["games"]] == ["a", "b", "c", "d"]
    game_ids = {g["game_id"] for g in result["games"]}
    assert len(game_ids) == 4
    for game in result["games"]:
        _assert_brief_ok(game, model_id)
    assert _packed_game_count(harness_dir) == before + 4
    opponents = {g["opponent_id"] for g in result["games"]}
    assert opponents == {"random"}


def test_prompt_test_start_same_opponent_all_white(tmp_path, monkeypatch):
    harness_dir = _harness_setup(tmp_path, monkeypatch)
    model_id = "composer-2.5"

    result = cmd_prompt_test_start(model_id, ["a", "b", "e"])

    assert result["ok"] is True
    assert len(result["games"]) == 3
    opponent_ids = {g["opponent_id"] for g in result["games"]}
    assert len(opponent_ids) == 1
    assert result["opponent_id"] in opponent_ids
    for game in result["games"]:
        assert game["agent_color"] == "WHITE"
        state = GameManager(str(harness_dir)).load_state(game["game_id"])
        assert state["agent_color"] == "WHITE"
        assert state["opponent_id"] == result["opponent_id"]


def test_prompt_test_start_afg(tmp_path, monkeypatch):
    harness_dir = _harness_setup(tmp_path, monkeypatch)
    model_id = "composer-2.5"
    before = _packed_game_count(harness_dir)

    result = cmd_prompt_test_start(model_id, ["a", "f", "g"], opponent="random")

    assert result["ok"] is True
    assert len(result["games"]) == 3
    assert [g["prompt_pack"] for g in result["games"]] == ["a", "f", "g"]
    briefs = {g["prompt_pack"]: g["brief"] for g in result["games"]}
    game_id_f = next(g["game_id"] for g in result["games"] if g["prompt_pack"] == "f")
    game_id_g = next(g["game_id"] for g in result["games"] if g["prompt_pack"] == "g")
    assert f"chess-harness legal {game_id_f}" in briefs["f"]
    assert f"chess-harness imagine {game_id_f}" not in briefs["f"]
    assert f"chess-harness imagine {game_id_g}" in briefs["g"]
    assert f"chess-harness legal {game_id_g}" not in briefs["g"]
    assert "Never chess-harness imagine" in briefs["a"]
    assert "list legal moves" in briefs["a"]
    for game in result["games"]:
        _assert_brief_ok(game, model_id)
    assert _packed_game_count(harness_dir) == before + 3


def test_prompt_test_start_ac(tmp_path, monkeypatch):
    harness_dir = _harness_setup(tmp_path, monkeypatch)
    model_id = "composer-2.5"
    before = _packed_game_count(harness_dir)

    result = cmd_prompt_test_start(model_id, ["a", "c"], opponent="random")

    assert result["ok"] is True
    assert len(result["games"]) == 2
    assert [g["prompt_pack"] for g in result["games"]] == ["a", "c"]
    for game in result["games"]:
        _assert_brief_ok(game, model_id)
    assert _packed_game_count(harness_dir) == before + 2


def test_prompt_test_start_committee_only(tmp_path, monkeypatch):
    harness_dir = _harness_setup(tmp_path, monkeypatch)
    model_id = "composer-2.5"
    before = _packed_game_count(harness_dir)

    result = cmd_prompt_test_start("composer-2.5", ["e"], opponent="random")

    assert result["ok"] is True
    assert len(result["games"]) == 1
    game = result["games"][0]
    assert game["prompt_pack"] == "e"
    assert game["kind"] == "committee"
    assert len(game["seats"]) == 3
    seats = {entry["seat"]: entry["brief"] for entry in game["seats"]}
    assert "Where is every piece" in seats[1]
    assert "Play real chess" in seats[2]
    assert "sounds like chess" in seats[3]
    for seat_entry in game["seats"]:
        brief = seat_entry["brief"]
        assert seat_entry["seat"] in (1, 2, 3)
        assert "never send chess-harness move" in brief.lower()
        assert "prompt-test vote" in brief
        assert str(seat_entry["seat"]) in brief
    assert _packed_game_count(harness_dir) == before + 1


def test_prompt_test_start_mixed_overlay_and_committee(tmp_path, monkeypatch):
    harness_dir = _harness_setup(tmp_path, monkeypatch)
    before = _packed_game_count(harness_dir)

    result = cmd_prompt_test_start("composer-2.5", ["a", "e"], opponent="random")

    assert result["ok"] is True
    assert len(result["games"]) == 2
    assert result["games"][0]["prompt_pack"] == "a"
    assert result["games"][0]["kind"] == "overlay"
    assert "brief" in result["games"][0]
    assert result["games"][1]["prompt_pack"] == "e"
    assert result["games"][1]["kind"] == "committee"
    assert len(result["games"][1]["seats"]) == 3
    assert _packed_game_count(harness_dir) == before + 2
