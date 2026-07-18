"""
Basic tests for Chess Vision Harness.
"""

import pytest
import tempfile
import shutil
from pathlib import Path
import sys

# Add the src directory to the path so we can import the modules
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from chess_harness.game_manager import GameManager
from chess_harness.board_controller import BoardController
from chess_harness.engine import StockfishAdapter


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files."""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir)


@pytest.fixture
def game_manager(temp_dir):
    """Create a GameManager instance with temporary directory."""
    return GameManager(base_dir=temp_dir)


@pytest.fixture
def engine():
    """Create a StockfishAdapter instance."""
    # This assumes Stockfish is available in PATH or at the default location
    # For testing, you might need to mock this or have Stockfish installed
    try:
        return StockfishAdapter()
    except RuntimeError:
        pytest.skip("Stockfish not available")


@pytest.fixture
def controller(game_manager, engine):
    """Create a BoardController instance."""
    return BoardController(game_manager, engine)


class TestGameManager:
    """Test GameManager functionality."""
    
    def test_validate_game_id_valid(self, game_manager):
        """Test valid game IDs."""
        assert game_manager.validate_game_id("game1") is True
        assert game_manager.validate_game_id("test_game") is True
        assert game_manager.validate_game_id("skill5-game1") is True
        assert game_manager.validate_game_id("default") is True
    
    def test_validate_game_id_invalid(self, game_manager):
        """Test invalid game IDs."""
        assert game_manager.validate_game_id("") is False
        assert game_manager.validate_game_id("game/../../../etc/passwd") is False
        assert game_manager.validate_game_id("game with spaces") is False
        assert game_manager.validate_game_id("a" * 65) is False  # Too long
    
    def test_game_directories(self, game_manager):
        """Test game directory creation and paths."""
        game_id = "test_game"
        game_dir = game_manager.get_game_dir(game_id)
        
        # State file path should be correct (dir created on save, not get)
        state_path = game_manager.get_state_path(game_id)
        assert state_path.name == "state.json"
        assert state_path.parent == game_dir
        
        # Save creates the directory
        game_manager.save_state(game_id, {"test": True})
        assert game_dir.exists()


class TestBoardController:
    """Test BoardController functionality."""
    
    def test_new_game_white(self, controller, game_manager):
        """Test starting a new game with white."""
        result = controller.new_game("test1", "white", 5, model_name="composer-2.5")
        
        assert result["ok"] is True
        assert result["game_id"] == "test1"
        assert result["your_turn"] is True
        assert "board_path" in result
        
        # Check state file was created
        state = game_manager.load_state("test1")
        assert state is not None
        assert state["status"] == "in_progress"
        assert state["agent_color"] == "WHITE"
        
        # Check board image was created
        board_path = game_manager.get_board_path("test1")
        assert board_path.exists()
    
    def test_new_game_black(self, controller, game_manager):
        """Test starting a new game with black (engine moves first)."""
        result = controller.new_game("test2", "black", 5, model_name="composer-2.5")
        
        assert result["ok"] is True
        assert result["game_id"] == "test2"
        assert result["your_turn"] is True
        
        # Check state file was created
        state = game_manager.load_state("test2")
        assert state is not None
        assert state["status"] == "in_progress"
        assert state["agent_color"] == "BLACK"
        assert len(state["moves"]) == 1  # Engine's first move
    
    def test_invalid_game_id(self, controller):
        """Test starting a game with invalid game ID."""
        result = controller.new_game("invalid/id", "white", 5, model_name="composer-2.5")
        assert result["ok"] is False
        assert "Invalid game_id" in result["error"]
    
    def test_invalid_color(self, controller):
        """Test starting a game with invalid color."""
        result = controller.new_game("test3", "red", 5)
        assert result["ok"] is False
        assert "agent_color must be" in result["error"]
    
    def test_invalid_skill(self, controller):
        """Test starting a game with invalid skill level."""
        result = controller.new_game("test4", "white", 25, model_name="composer-2.5")
        assert result["ok"] is False
        assert "20" in result["error"]
    
    def test_make_move_legal(self, controller, game_manager):
        """Test making a legal move."""
        # Start a game
        controller.new_game("test5", "white", 5, model_name="composer-2.5")
        
        # Make a legal move
        result = controller.make_agent_move("test5", "e2e4")
        
        assert result["ok"] is True
        assert result["your_turn"] is True
        assert "board_path" in result
        
        # Check state was updated
        state = game_manager.load_state("test5")
        assert len(state["moves"]) == 2  # Agent's move + engine's move
    
    def test_make_move_illegal(self, controller, game_manager):
        """Test making an illegal move."""
        # Start a game
        controller.new_game("test6", "white", 5, model_name="composer-2.5")
        
        # Try to make an illegal move
        result = controller.make_agent_move("test6", "e2e5")  # e5 is not a valid first move for pawn on e2
        
        assert result["ok"] is False
        assert "Illegal move" in result["error"]
        
        # Check state was not changed
        state = game_manager.load_state("test6")
        assert len(state["moves"]) == 0  # No moves should be recorded
    
    def test_make_move_not_your_turn(self, controller, game_manager):
        """Test making a move when it's not your turn."""
        # Start a game where agent plays white
        controller.new_game("test7", "white", 5, model_name="composer-2.5")
        
        # Corrupt state: set FEN to black's turn
        state = game_manager.load_state("test7")
        # Starting position but with black to move
        state["board_fen"] = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1"
        game_manager.save_state("test7", state)
        
        result = controller.make_agent_move("test7", "e7e5")
        
        assert result["ok"] is False
        assert "Not your turn" in result["error"]
    
    def test_resign(self, controller, game_manager):
        """Test resigning a game."""
        # Start a game
        controller.new_game("test8", "white", 5, model_name="composer-2.5")
        
        # Resign
        result = controller.resign("test8")
        
        assert result["ok"] is True
        assert result["result"] == "0-1"  # Black wins when white resigns
        
        # Check state
        state = game_manager.load_state("test8")
        assert state["status"] == "finished"
        assert state["result"] == "0-1"
    
    def test_export_pgn(self, controller, game_manager):
        """Test PGN export."""
        # Start a game and make a move
        controller.new_game("test9", "white", 5, model_name="composer-2.5")
        controller.make_agent_move("test9", "e2e4")
        
        # Export PGN
        result = controller.export_pgn("test9", allow_in_progress=True)
        
        assert result["ok"] is True
        assert "pgn" in result
        assert "[Event " in result["pgn"]
        
        # Check PGN file was created
        pgn_path = game_manager.get_pgn_path("test9")
        assert pgn_path.exists()


class TestParallelGames:
    """Test parallel game execution."""
    
    def test_two_games_parallel(self, controller, game_manager):
        """Test that two games can run in parallel without corruption."""
        # Start two games
        result1 = controller.new_game("parallel1", "white", 5, model_name="composer-2.5")
        result2 = controller.new_game("parallel2", "black", 5, model_name="composer-2.5")
        
        assert result1["ok"] is True
        assert result2["ok"] is True
        
        # Make moves in both games (both legal — p1 agent is white, p2 agent is black after engine-first)
        move1 = controller.make_agent_move("parallel1", "e2e4")
        move2 = controller.make_agent_move("parallel2", "e7e5")
        
        assert move1["ok"] is True
        assert move2["ok"] is True
        
        # Check that states are independent
        state1 = game_manager.load_state("parallel1")
        state2 = game_manager.load_state("parallel2")
        
        assert state1["agent_color"] == "WHITE"
        assert state2["agent_color"] == "BLACK"
        assert len(state1["moves"]) == 2  # Agent move + engine response
        assert len(state2["moves"]) == 3  # Engine first + agent move + engine response


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
