"""
Tournament management for Chess Vision Harness.
"""

import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

import chess

from .board_controller import BoardController
from .game_manager import GameManager
from .paths import resolve_base_dir
from .results import ResultsManager


class TournamentManager:
    """Manages tournaments and parallel game execution."""

    def __init__(self, base_dir: Optional[str] = None):
        base = str(base_dir) if base_dir else str(resolve_base_dir())
        self.game_manager = GameManager(base)
        self.results_manager = ResultsManager(base)
        self.controller = BoardController(self.game_manager)

    def create_tournament_matrix(
        self,
        opponents: List[str],
        games_per_cell: int = 1,
        agent_colors: List[str] | None = None,
        prefix: str = "tour",
    ) -> Dict[str, Any]:
        if agent_colors is None:
            agent_colors = ["white", "black"]

        manifest = {
            "created_at": datetime.now().isoformat(),
            "opponents": opponents,
            "games_per_cell": games_per_cell,
            "agent_colors": agent_colors,
            "games": [],
        }

        for opponent_id in opponents:
            for color in agent_colors:
                for i in range(games_per_cell):
                    safe = opponent_id.replace(":", "-")
                    game_id = f"{prefix}-{safe}-{color[0]}{i + 1}"
                    manifest["games"].append(
                        {
                            "game_id": game_id,
                            "opponent_id": opponent_id,
                            "agent_color": color,
                            "status": "pending",
                        }
                    )

        manifest_path = self.game_manager.base_dir / "tournament_manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        return manifest

    def load_manifest(self) -> Optional[Dict[str, Any]]:
        manifest_path = self.game_manager.base_dir / "tournament_manifest.json"
        if not manifest_path.exists():
            return None
        try:
            return json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def start_game(self, game_id: str, opponent_id: str, agent_color: str) -> Dict[str, Any]:
        return self.controller.new_game(
            game_id, agent_color, opponent_id=opponent_id, force=True
        )

    def play_random_vs_engine(self, game_id: str, max_moves: int = 100) -> Dict[str, Any]:
        moves_played = 0
        while moves_played < max_moves:
            state = self.game_manager.load_state(game_id)
            if not state or state["status"] != "in_progress":
                break

            board = chess.Board(state["board_fen"])
            if board.is_game_over():
                break

            agent_color = chess.WHITE if state["agent_color"] == "WHITE" else chess.BLACK
            if board.turn != agent_color:
                break

            import random

            legal_moves = list(board.legal_moves)
            if not legal_moves:
                break

            agent_move = random.choice(legal_moves)
            result = self.controller.make_agent_move(game_id, agent_move.uci())
            if not result["ok"]:
                return result
            moves_played += 1

        return self.controller.status(game_id)

    def run_smoke_test(
        self,
        num_games: int = 5,
        opponents: List[str] | None = None,
        max_moves: int = 50,
    ) -> Dict[str, Any]:
        if opponents is None:
            opponents = ["stockfish:5"]
        results = []
        for i in range(num_games):
            opponent_id = opponents[i % len(opponents)]
            game_id = f"smoke-{uuid.uuid4().hex[:8]}"
            start_result = self.start_game(game_id, opponent_id, "white")
            if not start_result["ok"]:
                results.append({"game_id": game_id, "error": start_result["error"]})
                continue
            self.play_random_vs_engine(game_id, max_moves)
            status = self.controller.status(game_id)
            results.append(
                {
                    "game_id": game_id,
                    "opponent_id": opponent_id,
                    "status": status.get("status"),
                    "result": status.get("result"),
                    "moves": status.get("move_count"),
                }
            )
        return {"smoke_test": True, "games_played": len(results), "results": results}

    def aggregate_results(self) -> Dict[str, Any]:
        return self.results_manager.get_summary()
