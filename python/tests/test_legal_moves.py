"""Phase 2 — gated legal-move list for pack F games."""

from __future__ import annotations

import asyncio
import copy
import json
import shutil
from pathlib import Path

import chess

from conftest import FIXTURES

from chess_harness import commands
from chess_harness.game_manager import GameManager
from chess_harness.tools_mcp import ChessHarnessMCP


def _harness_setup(tmp_path, monkeypatch) -> Path:
    harness_dir = tmp_path / "harness"
    harness_dir.mkdir()
    shutil.copy(FIXTURES / "models.json", harness_dir / "models.json")
    monkeypatch.setenv("CHESS_HARNESS_DIR", str(harness_dir))
    monkeypatch.setenv("MODELS_FILE", str(harness_dir / "models.json"))
    return harness_dir


def _new_packed_game(pack_id: str, game_id: str) -> dict:
    return commands.cmd_new(
        game_id,
        "white",
        None,
        model_name="composer-2.5",
        force=True,
        opponent="random",
        prompt_pack=pack_id,
    )


def _snapshot(harness_dir: Path, game_id: str) -> tuple[dict, bytes, list]:
    gm = GameManager(str(harness_dir))
    state = gm.load_state(game_id)
    assert state is not None
    board_bytes = gm.get_board_path(game_id).read_bytes()
    return copy.deepcopy(state), board_bytes, list(state.get("moves") or [])


def test_legal_starting_position_pack_f(tmp_path, monkeypatch):
    harness_dir = _harness_setup(tmp_path, monkeypatch)
    game_id = "legal-f-start"
    assert _new_packed_game("f", game_id)["ok"] is True

    result = commands.cmd_legal(game_id)
    assert result["ok"] is True
    assert result["game_id"] == game_id
    assert result["side_to_move"] == "white"
    assert result["count"] == 20
    assert set(result["legal_moves_uci"]) == {m.uci() for m in chess.Board().legal_moves}


def test_legal_updates_after_move(tmp_path, monkeypatch):
    harness_dir = _harness_setup(tmp_path, monkeypatch)
    game_id = "legal-f-after-move"
    assert _new_packed_game("f", game_id)["ok"] is True

    before = commands.cmd_legal(game_id)
    assert before["ok"] is True
    assert before["count"] == 20

    move_result = commands.cmd_move(game_id, "e2e4")
    assert move_result["ok"] is True

    state = GameManager(str(harness_dir)).load_state(game_id)
    board = chess.Board(state["board_fen"])

    result = commands.cmd_legal(game_id)
    assert result["ok"] is True
    assert result["count"] != before["count"]
    assert set(result["legal_moves_uci"]) == {m.uci() for m in board.legal_moves}
    expected_side = "white" if board.turn == chess.WHITE else "black"
    assert result["side_to_move"] == expected_side


def test_legal_rejected_wrong_pack(tmp_path, monkeypatch):
    _harness_setup(tmp_path, monkeypatch)
    for pack_id in ("a", "g"):
        game_id = f"legal-reject-{pack_id}"
        assert _new_packed_game(pack_id, game_id)["ok"] is True
        result = commands.cmd_legal(game_id)
        assert result["ok"] is False
        assert "not available" in result["error"].lower()


def test_legal_rejected_untagged(tmp_path, monkeypatch):
    _harness_setup(tmp_path, monkeypatch)
    game_id = "legal-reject-untagged"
    result = commands.cmd_new(
        game_id,
        "white",
        None,
        model_name="composer-2.5",
        force=True,
        opponent="random",
    )
    assert result["ok"] is True
    legal = commands.cmd_legal(game_id)
    assert legal["ok"] is False
    assert "not available" in legal["error"].lower()


def test_legal_does_not_mutate_position(tmp_path, monkeypatch):
    harness_dir = _harness_setup(tmp_path, monkeypatch)
    game_id = "legal-f-readonly"
    assert _new_packed_game("f", game_id)["ok"] is True
    before_state, before_png, before_moves = _snapshot(harness_dir, game_id)

    result = commands.cmd_legal(game_id)
    assert result["ok"] is True

    after_state, after_png, after_moves = _snapshot(harness_dir, game_id)
    assert after_state["board_fen"] == before_state["board_fen"]
    assert after_moves == before_moves
    assert after_png == before_png
    assert after_state.get("move_audit") == before_state.get("move_audit")
    assert after_state.get("last_activity") != before_state.get("last_activity")


def test_mcp_legal_moves_pack_f(tmp_path, monkeypatch):
    async def run():
        harness_dir = _harness_setup(tmp_path, monkeypatch)
        mcp = ChessHarnessMCP()
        mcp.game_manager = GameManager(str(harness_dir))
        mcp.game_service.game_manager = mcp.game_manager
        mcp.game_service.controller.game_manager = mcp.game_manager

        game_id = "mcp-legal-f"
        assert _new_packed_game("f", game_id)["ok"] is True

        tools = {t.name for t in mcp.get_tools()}
        assert "chess_legal_moves" in tools

        content = await mcp.handle_tool_call("chess_legal_moves", {"game_id": game_id})
        data = json.loads(content[0].text)
        assert data["ok"] is True
        assert data["count"] == 20
        assert "legal_moves_uci" in data

        rejected = await mcp.handle_tool_call("chess_legal_moves", {"game_id": "missing"})
        rejected_data = json.loads(rejected[0].text)
        assert rejected_data["ok"] is False

        mcp.game_service.controller.opponent_mgr.release()

    asyncio.run(run())


def test_mcp_legal_rejected_pack_a(tmp_path, monkeypatch):
    async def run():
        harness_dir = _harness_setup(tmp_path, monkeypatch)
        mcp = ChessHarnessMCP()
        mcp.game_manager = GameManager(str(harness_dir))
        mcp.game_service.game_manager = mcp.game_manager
        mcp.game_service.controller.game_manager = mcp.game_manager

        game_id = "mcp-legal-a"
        assert _new_packed_game("a", game_id)["ok"] is True

        content = await mcp.handle_tool_call("chess_legal_moves", {"game_id": game_id})
        data = json.loads(content[0].text)
        assert data["ok"] is False
        assert "not available" in data["error"].lower()

        mcp.game_service.controller.opponent_mgr.release()

    asyncio.run(run())
