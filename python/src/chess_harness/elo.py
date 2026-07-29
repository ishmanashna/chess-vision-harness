"""
ELO ladder system for Chess Vision Harness.

Agent ELO is stored on each inscribed model in models.json and updated from game results.
Opponent ELO comes from CCRL (tiny engines) or Stockfish UCI_Elo (1320+).
Only the agent's ELO changes.
"""

import json
import math
from pathlib import Path
from typing import Dict, List, Optional

from .rating_math import k_factor, update_elo as rating_update_elo

from .models import AGENT_START_ELO, ModelRegistry
from .paths import resolve_base_dir
from .game_types import GAME_TYPE_HUMAN_VS_AGENT

# Re-export for backward compatibility
__all__ = ["AGENT_START_ELO", "ELOLadder", "ENGINE_DISPLAY_NAME", "K_FACTOR", "LEGACY_SKILL_ELO"]

# Legacy skill -> ELO (for rebuilding old results.jsonl rows only)
LEGACY_SKILL_ELO = {
    -5: 600,
    -4: 770,
    -3: 940,
    -2: 1110,
    -1: 1200,
    0: 1250,
    1: 1350,
    2: 1450,
    3: 1600,
    4: 1750,
    5: 1900,
    6: 2000,
    7: 2150,
    8: 2250,
    9: 2350,
    10: 2450,
    11: 2550,
    12: 2600,
    13: 2700,
    14: 2750,
    15: 2800,
    16: 2850,
    17: 2900,
    18: 2950,
    19: 3000,
    20: 3100,
}

ENGINE_DISPLAY_NAME = "Stockfish 17.1"

K_FACTOR = 48


def format_stockfish_label(skill: int, engine_name: str = ENGINE_DISPLAY_NAME) -> str:
    """Legacy label for old games that stored skill without opponent catalog."""
    return f"{engine_name} (Skill {skill})"


def format_skill_label(skill: int) -> str:
    return f"Skill {skill}"


def expected_score(agent_elo: float, opponent_elo: float) -> float:
    return 1.0 / (1.0 + math.pow(10, (opponent_elo - agent_elo) / 400.0))


def update_elo(agent_elo: float, opponent_elo: float, score: float, *, games_played: int = 32) -> float:
    return rating_update_elo(agent_elo, opponent_elo, score, games_played=games_played)


def _score_from_result(result: str, agent_color: str) -> float:
    if result == "1/2-1/2":
        return 0.5
    if (agent_color == "WHITE" and result == "1-0") or (
        agent_color == "BLACK" and result == "0-1"
    ):
        return 1.0
    return 0.0


class ELOLadder:
    """Manages agent ELO ratings based on game results (backed by models.json)."""

    def __init__(self, base_dir: Optional[str] = None, registry: Optional[ModelRegistry] = None):
        self.base_dir = Path(base_dir) if base_dir else resolve_base_dir()
        self.registry = registry or ModelRegistry()

    def get_rating(self, model_name: str) -> float:
        canonical = self.registry.normalize_result_model(model_name)
        if not canonical:
            return float(AGENT_START_ELO)
        return self.registry.get_elo(canonical)

    def record_game(
        self,
        model_name: str,
        opponent_elo: int,
        result: str,
        agent_color: str,
        *,
        opponent_id: Optional[str] = None,
        skill: Optional[int] = None,
    ) -> Optional[Dict[str, int]]:
        """
        Record a game result and update ELO.

        Prefer opponent_elo. skill is legacy-only for old call sites.
        """
        from .opponents import opponent_elo_from_result

        canonical = self.registry.normalize_result_model(model_name)
        if not canonical:
            return None

        if opponent_elo is None and skill is not None:
            row = {"skill": skill, "opponent_id": opponent_id}
            resolved = opponent_elo_from_result(row)
            if resolved is None:
                return None
            opponent_elo = resolved

        agent_elo = self.registry.get_elo(canonical)
        elo_before = round(agent_elo)
        score = _score_from_result(result, agent_color)
        from .results import ResultsManager

        games_before = ResultsManager(base_dir=str(self.base_dir)).count_by_model().get(canonical, 0)
        # Result row is usually appended before record_game; don't count current game twice.
        if games_before > 0:
            games_before -= 1
        new_elo = update_elo(agent_elo, opponent_elo, score, games_played=games_before)
        elo_after = round(new_elo)
        self.registry.set_elo(canonical, round(new_elo, 1))
        return {
            "elo_before": elo_before,
            "elo_after": elo_after,
            "elo_delta": elo_after - elo_before,
        }

    def record_game_legacy_skill(
        self, model_name: str, skill: int, result: str, agent_color: str
    ) -> Optional[Dict[str, int]]:
        """Backward-compatible entry point for skill-based results."""
        from .opponents import opponent_elo_from_result

        opponent_elo = opponent_elo_from_result({"skill": skill})
        if opponent_elo is None:
            return None
        return self.record_game(
            model_name, opponent_elo, result, agent_color, skill=skill
        )

    def elo_change_for_game(self, game_id: str) -> Optional[Dict[str, int]]:
        from .opponents import opponent_elo_from_result

        results_file = self.base_dir / "results.jsonl"
        if not results_file.exists():
            return None

        ratings: Dict[str, float] = {}
        game_counts: Dict[str, int] = {}
        try:
            with open(results_file, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    game = json.loads(line)
                    model = game.get("model_name")
                    result = game.get("result")
                    color = game.get("agent_color")
                    canonical = self.registry.normalize_result_model(model)
                    opponent_elo = opponent_elo_from_result(game)
                    if not canonical or opponent_elo is None or not result or not color:
                        continue
                    if result == "*":
                        continue

                    agent_elo = ratings.get(canonical, float(AGENT_START_ELO))
                    elo_before = round(agent_elo)
                    score = _score_from_result(result, color)
                    games_before = game_counts.get(canonical, 0)
                    new_elo = update_elo(agent_elo, opponent_elo, score, games_played=games_before)
                    elo_after = round(new_elo)
                    ratings[canonical] = round(new_elo, 1)
                    game_counts[canonical] = games_before + 1

                    if game.get("game_id") == game_id:
                        return {
                            "elo_before": elo_before,
                            "elo_after": elo_after,
                            "elo_delta": elo_after - elo_before,
                        }
        except (OSError, json.JSONDecodeError):
            pass
        return None

    def get_leaderboard(self) -> List[Dict]:
        from .results import ResultsManager

        results = ResultsManager(base_dir=str(self.base_dir))
        game_counts = results.count_by_model()
        quality_stats = results.aggregate_quality_by_model()
        board = []
        for model in self.registry.list_models():
            model_id = model["id"]
            qs = quality_stats.get(model_id, {})
            board.append(
                {
                    "model": model_id,
                    "name": model.get("name", model_id),
                    "elo": round(model.get("elo", AGENT_START_ELO)),
                    "games": game_counts.get(model_id, 0),
                    "enabled": model.get("enabled", True),
                    "mean_accuracy": qs.get("mean_accuracy"),
                    "mean_play_rating": qs.get("mean_play_rating"),
                    "quality_games": int(qs.get("quality_games", 0)),
                }
            )
        board.sort(key=lambda x: -x["elo"])
        return board

    def get_stats(self, model_name: str) -> Dict:
        model_id = self.registry.resolve(model_name)
        elo = self.registry.get_elo(model_id)
        leaderboard = self.get_leaderboard()
        rank = next((i for i, e in enumerate(leaderboard, 1) if e["model"] == model_id), len(leaderboard))
        return {
            "model": model_id,
            "name": self.registry.display_name(model_id),
            "elo": round(elo),
            "rank": rank,
            "total_agents": len(leaderboard),
        }

    def process_results_file(self) -> None:
        from .opponents import opponent_elo_from_result

        results_file = self.base_dir / "results.jsonl"
        if not results_file.exists():
            return

        self.registry.reset_all_elo()
        try:
            with open(results_file, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    game = json.loads(line)
                    if game.get("game_type") == GAME_TYPE_HUMAN_VS_AGENT:
                        continue
                    model = game.get("model_name", "LLM Agent")
                    result = game.get("result")
                    color = game.get("agent_color")
                    opponent_elo = opponent_elo_from_result(game)
                    if model and opponent_elo is not None and result and color and result != "*":
                        self.record_game(model, opponent_elo, result, color)
        except (OSError, json.JSONDecodeError):
            pass
