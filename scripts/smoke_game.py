#!/usr/bin/env python3
"""
Smoke test script for Chess Vision Harness.
"""

import sys
from pathlib import Path

# Add the src directory to the path
src_dir = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_dir))

from chess_harness.game_manager import GameManager
from chess_harness.board_controller import BoardController
from chess_harness.engine import StockfishAdapter
from chess_harness.results import ResultsManager


def main():
    """Run a simple smoke test."""
    print("Chess Vision Harness Smoke Test")
    print("=" * 40)
    
    # Initialize components
    game_manager = GameManager()
    engine = StockfishAdapter()
    controller = BoardController(game_manager, engine)
    results_manager = ResultsManager()
    
    try:
        # Test 1: Start a new game
        print("\n1. Starting a new game...")
        result = controller.new_game("smoke-test", "white", 5)
        if not result["ok"]:
            print(f"   Failed: {result['error']}")
            return 1
        print(f"   Success: Game started with ID {result['game_id']}")
        
        # Test 2: Get board
        print("\n2. Getting board state...")
        result = controller.get_board("smoke-test")
        if not result["ok"]:
            print(f"   Failed: {result['error']}")
            return 1
        print(f"   Success: Board image at {result['board_path']}")
        
        # Test 3: Make a move
        print("\n3. Making a move (e2e4)...")
        result = controller.make_agent_move("smoke-test", "e2e4")
        if not result["ok"]:
            print(f"   Failed: {result['error']}")
            return 1
        print(f"   Success: Move made, engine responded with {result['engine_move_san']}")
        
        # Test 4: Export PGN
        print("\n4. Exporting PGN...")
        result = controller.export_pgn("smoke-test")
        if not result["ok"]:
            print(f"   Failed: {result['error']}")
            return 1
        print(f"   Success: PGN exported to {result['pgn_path']}")
        
        # Test 5: Check status
        print("\n5. Checking status...")
        result = controller.status("smoke-test")
        if not result["ok"]:
            print(f"   Failed: {result['error']}")
            return 1
        print(f"   Success: Game status: {result['status']}")
        
        # Test 6: Test parallel games
        print("\n6. Testing parallel games...")
        result1 = controller.new_game("parallel-1", "white", 5)
        result2 = controller.new_game("parallel-2", "black", 5)
        
        if not result1["ok"] or not result2["ok"]:
            print("   Failed to start parallel games")
            return 1
        
        # Make moves in both games
        move1 = controller.make_agent_move("parallel-1", "d2d4")
        move2 = controller.make_agent_move("parallel-2", "d7d5")
        
        if not move1["ok"]:
            print(f"   Failed in game 1: {move1['error']}")
            return 1
        
        # Game 2 should fail because it's white's turn (engine already moved)
        if move2["ok"]:
            print("   Failed: Expected game 2 to fail (not black's turn)")
            return 1
        
        print("   Success: Parallel games work correctly")
        
        # Test 7: Test illegal move
        print("\n7. Testing illegal move handling...")
        result = controller.make_agent_move("parallel-1", "e2e5")  # Illegal move
        if result["ok"]:
            print("   Failed: Expected illegal move to be rejected")
            return 1
        print(f"   Success: Illegal move rejected with: {result['error']}")
        
        # Clean up
        print("\n8. Cleaning up...")
        controller.resign("smoke-test")
        controller.resign("parallel-1")
        controller.resign("parallel-2")
        
        print("\n" + "=" * 40)
        print("All smoke tests passed!")
        return 0
        
    except Exception as e:
        print(f"\nError during smoke test: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        engine.quit()


if __name__ == "__main__":
    sys.exit(main())
