import sys
import os
import json
import asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
os.environ.setdefault(
    "STOCKFISH_PATH",
    os.path.join(
        os.path.dirname(__file__), "..", "stockfish", "stockfish", "stockfish-windows-x86-64.exe"
    ),
)

from chess_harness.tools_mcp import ChessHarnessMCP

mcp = ChessHarnessMCP()

tools = mcp.get_tools()
print("Tools:", [t.name for t in tools])
assert len(tools) == 7
print("OK: 7 tools registered")


async def test():
    r = await mcp.handle_tool_call(
        "chess_new_game", {"game_id": "mcp1", "agent_color": "white", "skill": 5, "model_id": "composer-2.5"}
    )
    texts = [c.text for c in r if c.type == "text"]
    data = json.loads(texts[0])
    print("\nnew_game:", data["ok"], "| game_id:", data["game_id"])
    assert data["ok"]

    r = await mcp.handle_tool_call("chess_get_board", {"game_id": "mcp1"})
    texts = [c.text for c in r if c.type == "text"]
    data = json.loads(texts[0])
    print("get_board:", data["ok"], "| board_path:", data["board_path"])
    assert data["ok"] and "Board image:" in data["message"]
    has_image = any(c.type == "image" for c in r)
    print("has image content:", has_image)

    r = await mcp.handle_tool_call("chess_make_move", {"game_id": "mcp1", "move": "e2e4"})
    texts = [c.text for c in r if c.type == "text"]
    data = json.loads(texts[0])
    print("make_move:", data["ok"], "| uci:", data["uci"], "| engine:", data["engine_move_san"])
    assert data["ok"] and data["uci"] == "e2e4"

    r = await mcp.handle_tool_call("chess_status", {"game_id": "mcp1"})
    texts = [c.text for c in r if c.type == "text"]
    data = json.loads(texts[0])
    print("status:", data["ok"], "| turn:", data["turn"])

    r = await mcp.handle_tool_call("chess_export_pgn", {"game_id": "mcp1"})
    texts = [c.text for c in r if c.type == "text"]
    data = json.loads(texts[0])
    print("export_pgn:", data["ok"], "| has headers:", "[Event" in data["pgn"])
    assert "[Event" in data["pgn"]

    r = await mcp.handle_tool_call("chess_resign", {"game_id": "mcp1"})
    texts = [c.text for c in r if c.type == "text"]
    data = json.loads(texts[0])
    print("resign:", data["ok"], "| result:", data["result"])
    assert data["ok"]

    print("\nPHASE 6 PASSED")


asyncio.run(test())
mcp.engine.quit()
