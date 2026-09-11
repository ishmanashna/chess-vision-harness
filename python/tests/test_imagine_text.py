"""Phase 3 — gated text imagine for pack G games."""

from __future__ import annotations

import asyncio
import copy
import json
import shutil
from pathlib import Path

import chess

from conftest import FIXTURES

from chess_harness import commands
from chess_harness.board_controller import MAX_IMAGINE_PLIES
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


def test_imagine_two_plies_pack_g(tmp_path, monkeypatch):
    harness_dir = _harness_setup(tmp_path, monkeypatch)
    game_id = "imagine-g-line"
    assert _new_packed_game("g", game_id)["ok"] is True

    before_state, before_png, before_moves = _snapshot(harness_dir, game_id)
    result = commands.cmd_imagine(game_id, ["e2e4", "e7e5"])
    assert result["ok"] is True
    assert result["game_id"] == game_id
    assert result["applied_count"] == 2
    assert result["side_to_move"] == "white"
    assert result["hypothetical"] is True
    assert "side_to_move: white" in result["text"]
    assert "in_check: no" in result["text"]

    after_state, after_png, after_moves = _snapshot(harness_dir, game_id)
    assert after_state["board_fen"] == before_state["board_fen"]
    assert after_moves == before_moves
    assert after_png == before_png
    assert after_state.get("last_activity") != before_state.get("last_activity")


def test_imagine_rejected_wrong_pack(tmp_path, monkeypatch):
    _harness_setup(tmp_path, monkeypatch)
    for pack_id in ("a", "f"):
        game_id = f"imagine-reject-{pack_id}"
        assert _new_packed_game(pack_id, game_id)["ok"] is True
        result = commands.cmd_imagine(game_id, ["e2e4"])
        assert result["ok"] is False
        assert "not available" in result["error"].lower()


def test_imagine_rejected_untagged(tmp_path, monkeypatch):
    _harness_setup(tmp_path, monkeypatch)
    game_id = "imagine-reject-untagged"
    result = commands.cmd_new(
        game_id,
        "white",
        None,
        model_name="composer-2.5",
        force=True,
        opponent="random",
    )
    assert result["ok"] is True
    imagine = commands.cmd_imagine(game_id, ["e2e4"])
    assert imagine["ok"] is False
    assert "not available" in imagine["error"].lower()


def test_imagine_illegal_mid_line(tmp_path, monkeypatch):
    harness_dir = _harness_setup(tmp_path, monkeypatch)
    game_id = "imagine-g-bad-line"
    assert _new_packed_game("g", game_id)["ok"] is True
    before_state, before_png, before_moves = _snapshot(harness_dir, game_id)

    result = commands.cmd_imagine(game_id, ["e2e4", "e7e5", "e2e4"])
    assert result["ok"] is False
    assert result.get("index") == 2
    assert "error" in result

    after_state, after_png, after_moves = _snapshot(harness_dir, game_id)
    assert after_state["board_fen"] == before_state["board_fen"]
    assert after_moves == before_moves
    assert after_png == before_png


def test_imagine_too_many_plies(tmp_path, monkeypatch):
    _harness_setup(tmp_path, monkeypatch)
    game_id = "imagine-g-cap"
    assert _new_packed_game("g", game_id)["ok"] is True
    result = commands.cmd_imagine(game_id, ["e2e4"] * (MAX_IMAGINE_PLIES + 1))
    assert result["ok"] is False
    assert str(MAX_IMAGINE_PLIES) in result["error"]


def test_imagine_matches_format_board_text(tmp_path, monkeypatch):
    _harness_setup(tmp_path, monkeypatch)
    game_id = "imagine-g-format"
    assert _new_packed_game("g", game_id)["ok"] is True

    board = chess.Board()
    board.push(chess.Move.from_uci("e2e4"))
    board.push(chess.Move.from_uci("e7e5"))
    from chess_harness.board_text import format_board_text

    expected = format_board_text(board, bottom_color="white")
    result = commands.cmd_imagine(game_id, ["e2e4", "e7e5"])
    assert result["ok"] is True
    assert result["text"] == expected


def test_mcp_imagine_board_pack_g(tmp_path, monkeypatch):
    async def run():
        harness_dir = _harness_setup(tmp_path, monkeypatch)
        mcp = ChessHarnessMCP()
        mcp.game_manager = GameManager(str(harness_dir))
        mcp.game_service.game_manager = mcp.game_manager
        mcp.game_service.controller.game_manager = mcp.game_manager

        game_id = "mcp-imagine-g"
        assert _new_packed_game("g", game_id)["ok"] is True

        tools = {t.name for t in mcp.get_tools()}
        assert "chess_imagine_board" in tools

        content = await mcp.handle_tool_call(
            "chess_imagine_board",
            {"game_id": game_id, "moves": ["e2e4", "e7e5"]},
        )
        assert len(content) == 1
        data = json.loads(content[0].text)
        assert data["ok"] is True
        assert data["side_to_move"] == "white"
        assert "text" in data
        assert "side_to_move: white" in data["text"]

        rejected = await mcp.handle_tool_call(
            "chess_imagine_board",
            {"game_id": game_id, "moves": ["e2e4", "e7e5", "e2e4"]},
        )
        rejected_data = json.loads(rejected[0].text)
        assert rejected_data["ok"] is False
        assert rejected_data.get("index") == 2

        mcp.game_service.controller.opponent_mgr.release()

    asyncio.run(run())


def test_mcp_imagine_rejected_pack_a(tmp_path, monkeypatch):
    async def run():
        harness_dir = _harness_setup(tmp_path, monkeypatch)
        mcp = ChessHarnessMCP()
        mcp.game_manager = GameManager(str(harness_dir))
        mcp.game_service.game_manager = mcp.game_manager
        mcp.game_service.controller.game_manager = mcp.game_manager

        game_id = "mcp-imagine-a"
        assert _new_packed_game("a", game_id)["ok"] is True

        content = await mcp.handle_tool_call(
            "chess_imagine_board",
            {"game_id": game_id, "moves": ["e2e4"]},
        )
        data = json.loads(content[0].text)
        assert data["ok"] is False
        assert "not available" in data["error"].lower()

        mcp.game_service.controller.opponent_mgr.release()

    asyncio.run(run())
