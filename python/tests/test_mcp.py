"""Tests for MCP tool responses."""

import asyncio
import base64
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
os.environ.setdefault(
    "STOCKFISH_PATH",
    os.path.join(
        os.path.dirname(__file__), "..", "bin", "stockfish-windows-x86-64.exe"
    ),
)

from chess_harness.tools_mcp import ChessHarnessMCP


@pytest.fixture(scope="module")
def mcp():
    instance = ChessHarnessMCP()
    yield instance
    instance.game_service.controller.opponent_mgr.release()
    if instance.game_service.controller._eval_engine is not None:
        instance.game_service.controller._eval_engine.quit()


def test_mcp_new_game_and_image_base64(mcp, tmp_path, monkeypatch):
    async def run():
        monkeypatch.setenv("CHESS_HARNESS_DIR", str(tmp_path / "harness"))
        from chess_harness.game_manager import GameManager
        from chess_harness.game_service import GameService

        mcp.game_manager = GameManager(str(tmp_path / "harness"))
        mcp.game_service = GameService(mcp.game_manager)

        result = await mcp.handle_tool_call(
            "chess_new_game",
            {
                "game_id": "mcp-t1",
                "agent_color": "white",
                "opponent": "stockfish:5",
                "model_id": "composer-2.5",
            },
        )
        texts = [c for c in result if c.type == "text"]
        data = json.loads(texts[0].text)
        assert data["ok"]

        images = [c for c in result if c.type == "image"]
        assert images
        assert isinstance(images[0].data, str)
        decoded = base64.b64decode(images[0].data)
        assert decoded[:8] == b"\x89PNG\r\n\x1a\n"

    asyncio.run(run())


def test_mcp_schemas_no_include_fen(mcp):
    tools = {t.name: t for t in mcp.get_tools()}
    for name in ("chess_status", "chess_get_board"):
        props = tools[name].inputSchema.get("properties", {})
        assert "include_fen" not in props
    new_props = tools["chess_new_game"].inputSchema.get("properties", {})
    assert "fen" not in new_props


def test_mcp_idle_prune_and_release_parity(mcp, tmp_path, monkeypatch):
    async def run():
        monkeypatch.setenv("CHESS_HARNESS_DIR", str(tmp_path / "harness"))
        from chess_harness.game_manager import GameManager
        from chess_harness.game_service import GameService

        mcp.game_manager = GameManager(str(tmp_path / "harness"))
        mcp.game_service = GameService(mcp.game_manager)

        prune_calls = []
        release_calls = []

        original_prune = mcp.game_service.controller.check_idle_games
        original_release = mcp.game_service.controller.opponent_mgr.release

        def track_prune():
            prune_calls.append(True)
            return original_prune()

        def track_release():
            release_calls.append(True)
            return original_release()

        mcp.game_service.controller.check_idle_games = track_prune
        mcp.game_service.controller.opponent_mgr.release = track_release

        game_id = "mcp-release"
        await mcp.handle_tool_call(
            "chess_new_game",
            {
                "game_id": game_id,
                "agent_color": "white",
                "opponent": "stockfish:5",
                "model_id": "composer-2.5",
            },
        )
        assert prune_calls
        assert release_calls

        prune_calls.clear()
        release_calls.clear()
        await mcp.handle_tool_call(
            "chess_make_move",
            {"game_id": game_id, "move": "e2e4"},
        )
        assert prune_calls
        assert release_calls

        prune_calls.clear()
        release_calls.clear()
        await mcp.handle_tool_call("chess_status", {"game_id": game_id})
        assert not prune_calls
        assert not release_calls

        prune_calls.clear()
        release_calls.clear()
        await mcp.handle_tool_call("chess_resign", {"game_id": game_id})
        assert prune_calls
        assert not release_calls

    asyncio.run(run())
