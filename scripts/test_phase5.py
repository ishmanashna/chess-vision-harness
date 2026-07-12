import sys, os, json, threading, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
os.environ['STOCKFISH_PATH'] = os.path.join(os.path.dirname(__file__), '..', 'sf-plain', 'stockfish', 'stockfish-windows-x86-64.exe')

from chess_harness.spectator import app, game_manager, controller
from fastapi.testclient import TestClient

# Ensure a game exists
controller.new_game("spec1", "white", 5)
controller.make_agent_move("spec1", "e2e4")

client = TestClient(app)

# Test /api/games
r = client.get("/api/games")
print("GET /api/games:", r.status_code)
assert r.status_code == 200
games = r.json()
print("  Games:", len(games))
assert len(games) >= 1

# Test /api/games/spec1/state
r = client.get("/api/games/spec1/state")
print("GET /api/games/spec1/state:", r.status_code)
assert r.status_code == 200
state = r.json()
print("  agent_color:", state["agent_color"], "| status:", state["status"], "| moves:", len(state["moves"]))

# Test /api/games/spec1/pgn
r = client.get("/api/games/spec1/pgn")
print("GET /api/games/spec1/pgn:", r.status_code)
assert r.status_code == 200
pgn = r.json()["pgn"]
assert "[Event" in pgn
print("  PGN has headers:", "[Event" in pgn)

# Test /g/spec1/board.png
r = client.get("/g/spec1/board.png")
print("GET /g/spec1/board.png:", r.status_code, "| content-type:", r.headers.get("content-type"))
assert r.status_code == 200
assert r.headers["content-type"] == "image/png"
assert len(r.content) > 1000
print("  Image size:", len(r.content), "bytes")

# Test / (dashboard)
r = client.get("/")
print("GET /:", r.status_code, "| has HTML:", "Chess Vision Harness" in r.text)
assert r.status_code == 200

# Test /g/spec1 (game view)
r = client.get("/g/spec1")
print("GET /g/spec1:", r.status_code, "| has img tag:", "board.png" in r.text)
assert r.status_code == 200

print("\nPHASE 5 PASSED")
