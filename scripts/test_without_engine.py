#!/usr/bin/env python3
"""
Test script that doesn't require Stockfish.
"""

import sys
from pathlib import Path

# Add the src directory to the path
src_dir = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_dir))

from chess_harness.game_manager import GameManager
from chess_harness.render_pillow import ChessBoardRenderer
import chess
import chess.pgn


def main():
    """Run tests without Stockfish."""
    print("Chess Vision Harness Tests (without Stockfish)")
    print("=" * 50)
    
    # Test 1: GameManager
    print("\n1. Testing GameManager...")
    game_manager = GameManager()
    
    # Test game_id validation
    assert game_manager.validate_game_id("test1") is True
    assert game_manager.validate_game_id("invalid/id") is False
    print("   [OK] Game ID validation works")
    
    # Test directory creation (created when state is saved)
    game_dir = game_manager.get_game_dir("test-game")
    # Note: directory is created on save_state, not on get_game_dir
    print("   [OK] Game directory path works")
    
    # Test 2: ChessBoardRenderer
    print("\n2. Testing ChessBoardRenderer...")
    renderer = ChessBoardRenderer()
    
    # Create a board
    board = chess.Board()
    output_path = Path("test_board.png")
    
    # Render board
    renderer.render_board(board, output_path, agent_color="white")
    assert output_path.exists()
    print("   [OK] Board rendering works")
    
    # Clean up
    output_path.unlink()
    
    # Test 3: Game state management
    print("\n3. Testing game state management...")
    game_id = "test-state"
    
    # Create a simple state
    state = {
        "game_id": game_id,
        "agent_color": "WHITE",
        "skill": 5,
        "board_fen": chess.STARTING_FEN,
        "last_move_uci": None,
        "status": "in_progress",
        "result": None,
        "pgn_headers": {
            "Event": "Test Game",
            "Site": "Local",
            "Date": "2026.07.10",
            "Round": "1",
            "White": "Test Agent",
            "Black": "Stockfish",
            "Result": "*"
        },
        "moves": []
    }
    
    # Save state
    success = game_manager.save_state(game_id, state)
    assert success is True
    print("   [OK] State saving works")
    
    # Load state
    loaded_state = game_manager.load_state(game_id)
    assert loaded_state is not None
    assert loaded_state["game_id"] == game_id
    print("   [OK] State loading works")
    
    # Test 4: Move validation (without engine)
    print("\n4. Testing move validation...")
    board = chess.Board()
    
    # Test legal move
    legal_move = chess.Move.from_uci("e2e4")
    assert legal_move in board.legal_moves
    print("   [OK] Legal move detection works")
    
    # Test illegal move
    illegal_move = chess.Move.from_uci("e2e5")
    assert illegal_move not in board.legal_moves
    print("   [OK] Illegal move detection works")
    
    # Test SAN parsing
    san_move = board.parse_san("e4")
    assert san_move == legal_move
    print("   [OK] SAN parsing works")
    
    # Test 5: PGN export (basic)
    print("\n5. Testing PGN export...")
    import io
    
    game = chess.pgn.Game()
    game.headers["Event"] = "Test Game"
    game.headers["Site"] = "Local"
    game.headers["Date"] = "2026.07.10"
    game.headers["Round"] = "1"
    game.headers["White"] = "Agent"
    game.headers["Black"] = "Stockfish"
    game.headers["Result"] = "*"
    
    # Add some moves
    board = chess.Board()
    move1 = board.parse_san("e4")
    node1 = game.add_variation(move1)
    board.push(move1)
    
    move2 = board.parse_san("e5")
    node2 = node1.add_variation(move2)
    board.push(move2)
    
    # Convert to string
    pgn_string = str(game)
    assert "[Event " in pgn_string
    assert "1. e4 e5" in pgn_string
    print("   [OK] PGN generation works")
    
    # Clean up test files
    print("\n6. Cleaning up...")
    import shutil
    if game_manager.base_dir.exists():
        shutil.rmtree(game_manager.base_dir)
    print("   [OK] Cleanup completed")
    
    print("\n" + "=" * 50)
    print("All tests passed!")
    print("\nNote: Stockfish is required for actual gameplay.")
    print("Please install Stockfish and ensure it's in your PATH.")
    print("Download from: https://stockfishchess.org/download/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
