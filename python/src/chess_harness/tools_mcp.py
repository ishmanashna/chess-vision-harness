"""
MCP tools for Chess Vision Harness.
"""

import base64
import json
from typing import Any, Dict, List

from mcp import Tool
from mcp.types import ImageContent, TextContent

from .board_controller import BoardController
from .commands import resolve_agent_color
from .game_manager import GameManager
from .models import ModelRegistry
from .opponents import get_catalog


class ChessHarnessMCP:
    """MCP server for Chess Vision Harness."""

    def __init__(self):
        self.game_manager = GameManager()
        self.controller = BoardController(self.game_manager)
        self.registry = ModelRegistry()

    def get_tools(self) -> List[Tool]:
        model_ids = self.registry.list_ids()
        model_schema: Dict[str, Any] = {
            "type": "string",
            "description": "Inscribed model id (required). List: chess-harness models list",
        }
        if model_ids:
            model_schema["enum"] = model_ids

        opponent_ids = [
            o.id for o in get_catalog().list_eligible_opponents()
        ]
        opponent_schema: Dict[str, Any] = {
            "type": "string",
            "description": (
                "Catalog opponent id (e.g. stockfish-handicap:noise17, stockfish:5). "
                "Omit for ELO-weighted random opponent."
            ),
        }
        if opponent_ids:
            opponent_schema["enum"] = opponent_ids

        return [
            Tool(
                name="chess_new_game",
                description=(
                    "Start a new chess game. Agent plays against a catalog opponent. "
                    "model_id must be an inscribed model — run models list first. "
                    "Omit opponent for similar-ELO match. Unless the operator specifies a color, "
                    "omit agent_color or use 'random'."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "game_id": {"type": "string", "description": "Unique game identifier"},
                        "agent_color": {
                            "type": "string",
                            "enum": ["random", "white", "black"],
                            "default": "random",
                            "description": (
                                "Color the agent plays. Default random unless operator says otherwise."
                            ),
                        },
                        "opponent": opponent_schema,
                        "skill": {
                            "type": "integer",
                            "minimum": 0,
                            "maximum": 20,
                            "description": "Deprecated alias for stockfish:N opponent",
                        },
                        "model_id": model_schema,
                        "force": {
                            "type": "boolean",
                            "description": "Overwrite existing game_id if true",
                        },
                    },
                    "required": ["model_id"],
                },
            ),
            Tool(
                name="chess_list_models",
                description="List inscribed models available for play.",
                inputSchema={"type": "object", "properties": {}},
            ),
            Tool(
                name="chess_get_board",
                description=(
                    "Returns board image path and embedded PNG. "
                    "Do not infer position from JSON — read the image only."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "game_id": {"type": "string"},
                    },
                },
            ),
            Tool(
                name="chess_make_move",
                description="Submit a move chosen from the board image (UCI e2e4 or SAN Nf3).",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "game_id": {"type": "string"},
                        "move": {"type": "string"},
                    },
                    "required": ["move"],
                },
            ),
            Tool(
                name="chess_resign",
                description="Resign the current game.",
                inputSchema={"type": "object", "properties": {"game_id": {"type": "string"}}},
            ),
            Tool(
                name="chess_export_pgn",
                description="Export PGN after the game ends (not while in progress).",
                inputSchema={"type": "object", "properties": {"game_id": {"type": "string"}}},
            ),
            Tool(
                name="chess_status",
                description="Turn metadata only (your_turn, move_count). No board position.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "game_id": {"type": "string"},
                    },
                },
            ),
        ]

    async def handle_tool_call(self, tool_name: str, arguments: Dict[str, Any]) -> List:
        game_id = arguments.get("game_id", "default")

        if tool_name == "chess_list_models":
            models = self.registry.list_models()
            return [TextContent(type="text", text=json.dumps({"models": models}, indent=2))]

        if tool_name == "chess_new_game":
            model_id = arguments.get("model_id") or arguments.get("model_name")
            opponent = arguments.get("opponent")
            skill = arguments.get("skill")
            result = self.controller.new_game(
                game_id,
                resolve_agent_color(arguments.get("agent_color")),
                model_name=model_id,
                force=arguments.get("force", False),
                opponent_id=opponent,
                skill=skill,
            )
        elif tool_name == "chess_get_board":
            result = self.controller.get_board(game_id)
        elif tool_name == "chess_make_move":
            result = self.controller.make_agent_move(game_id, arguments["move"])
        elif tool_name == "chess_resign":
            result = self.controller.resign(game_id)
        elif tool_name == "chess_export_pgn":
            result = self.controller.export_pgn(game_id)
        elif tool_name == "chess_status":
            result = self.controller.status(game_id)
        else:
            return [TextContent(type="text", text=f"Unknown tool: {tool_name}")]

        content: List = [TextContent(type="text", text=json.dumps(result, indent=2))]

        if result.get("ok") and "board_path" in result:
            board_path = result["board_path"]
            try:
                image_data = open(board_path, "rb").read()
                content.append(
                    ImageContent(
                        type="image",
                        data=base64.b64encode(image_data).decode("ascii"),
                        mimeType="image/png",
                    )
                )
            except OSError:
                pass

        return content


_mcp_instance = None


def get_mcp_instance() -> ChessHarnessMCP:
    global _mcp_instance
    if _mcp_instance is None:
        _mcp_instance = ChessHarnessMCP()
    return _mcp_instance
