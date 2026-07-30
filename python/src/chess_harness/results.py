"""
Results handling for Chess Vision Harness.
"""

import json
from collections import defaultdict
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

import filelock

from .elo import ELOLadder
from .game_types import GAME_TYPE_AGENT_VS_AGENT, GAME_TYPE_HUMAN_VS_AGENT
from .models import ModelRegistry
from .opponents import get_catalog
from .paths import project_root, resolve_base_dir


class ResultsManager:
    """Manages results.jsonl and provides aggregation."""

    def __init__(self, base_dir: Optional[str] = None):
        self.base_dir = Path(base_dir) if base_dir else resolve_base_dir()
        self.results_file = self.base_dir / "results.jsonl"

    def append_result(self, result: Dict[str, Any]) -> bool:
        try:
            self.base_dir.mkdir(parents=True, exist_ok=True)
            with open(self.results_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(result) + "\n")
            return True
        except OSError:
            return False

    @contextmanager
    def _results_lock(self) -> Iterator[None]:
        lock_path = self.results_file.with_suffix(".jsonl.lock")
        lock = filelock.FileLock(lock_path, timeout=30)
        lock.acquire()
        try:
            yield
        finally:
            if lock.is_locked:
                lock.release()

    def upsert_quality_fields(
        self, game_id: str, model_id: str, fields: Dict[str, Any]
    ) -> bool:
        """Patch quality columns on the results.jsonl row for (game_id, model_name)."""
        try:
            with self._results_lock():
                results = self.load_results()
                updated = False
                for row in results:
                    if row.get("game_id") == game_id and row.get("model_name") == model_id:
                        row.update(fields)
                        updated = True
                if not updated:
                    return False
                self.base_dir.mkdir(parents=True, exist_ok=True)
                with open(self.results_file, "w", encoding="utf-8") as f:
                    for row in results:
                        f.write(json.dumps(row) + "\n")
                return True
        except (OSError, filelock.Timeout):
            return False

    def remove_game_results(self, game_id: str) -> int:
        """Delete all results.jsonl rows for a game_id. Returns number removed."""
        try:
            with self._results_lock():
                results = self.load_results()
                kept = [row for row in results if row.get("game_id") != game_id]
                removed = len(results) - len(kept)
                if removed == 0:
                    return 0
                self.base_dir.mkdir(parents=True, exist_ok=True)
                with open(self.results_file, "w", encoding="utf-8") as f:
                    for row in kept:
                        f.write(json.dumps(row) + "\n")
                return removed
        except (OSError, filelock.Timeout):
            return 0

    def load_results(self) -> List[Dict[str, Any]]:
        results = []
        if not self.results_file.exists():
            return results
        try:
            with open(self.results_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        results.append(json.loads(line))
        except (OSError, json.JSONDecodeError):
            pass
        return results

    def aggregate_by_opponent(self) -> Dict[str, Dict[str, Any]]:
        results = self.load_results()
        stats: Dict[str, Dict[str, Any]] = defaultdict(
            lambda: {"wins": 0, "draws": 0, "losses": 0, "total": 0}
        )
        for result in results:
            key = result.get("opponent_id") or (
                f"stockfish:{result['skill']}" if result.get("skill") is not None else None
            )
            agent_color = result.get("agent_color")
            game_result = result.get("result")
            if key is None or agent_color is None or game_result is None:
                continue
            stats[key]["total"] += 1
            if game_result == "1/2-1/2":
                stats[key]["draws"] += 1
            elif (agent_color == "WHITE" and game_result == "1-0") or (
                agent_color == "BLACK" and game_result == "0-1"
            ):
                stats[key]["wins"] += 1
            else:
                stats[key]["losses"] += 1
        return dict(stats)

    def aggregate_by_skill(self) -> Dict[int, Dict[str, Any]]:
        results = self.load_results()
        skill_stats: Dict[int, Dict[str, Any]] = defaultdict(
            lambda: {"wins": 0, "draws": 0, "losses": 0, "total": 0}
        )
        for result in results:
            skill = result.get("skill")
            agent_color = result.get("agent_color")
            game_result = result.get("result")
            if skill is None or agent_color is None or game_result is None:
                continue
            skill_stats[skill]["total"] += 1
            if game_result == "1/2-1/2":
                skill_stats[skill]["draws"] += 1
            elif (agent_color == "WHITE" and game_result == "1-0") or (
                agent_color == "BLACK" and game_result == "0-1"
            ):
                skill_stats[skill]["wins"] += 1
            else:
                skill_stats[skill]["losses"] += 1
        return dict(skill_stats)

    def _registry(self) -> ModelRegistry:
        return ModelRegistry(self.base_dir / "models.json")

    def count_by_model(self) -> Dict[str, int]:
        """Count finished games per canonical model id (Elo ladder; excludes AvH and *)."""
        counts: Dict[str, int] = defaultdict(int)
        registry = self._registry()
        for result in self.load_results():
            if result.get("game_type") == GAME_TYPE_HUMAN_VS_AGENT:
                continue
            if result.get("result") == "*":
                continue
            model_id = registry.normalize_result_model(result.get("model_name"))
            if model_id:
                counts[model_id] += 1
        return dict(counts)

    def aggregate_quality_by_model(
        self, *, cal_root: Optional[Path] = None
    ) -> Dict[str, Dict[str, Any]]:
        """Per-model quality means from results.jsonl (includes AvH; excludes *; AvA deduped).

        mean_play_rating (Estimated Elo) is est_elo_from_accuracy(mean_accuracy) via the
        current accuracy→Elo map — not an average of stored play_rating fields.
        """
        from .accuracy_elo_map import est_elo_from_accuracy

        if cal_root is None:
            cal_root = project_root() / "elo_calibration" / "results"

        registry = self._registry()
        seen_avaa: set[tuple[str, str]] = set()
        acc_sum: Dict[str, float] = defaultdict(float)
        acc_n: Dict[str, int] = defaultdict(int)
        quality_games: Dict[str, int] = defaultdict(int)

        for row in self.load_results():
            result = row.get("result")
            if result is None or result == "*":
                continue
            model_id = registry.normalize_result_model(row.get("model_name"))
            if not model_id:
                continue
            game_id = row.get("game_id")
            if row.get("game_type") == GAME_TYPE_AGENT_VS_AGENT:
                key = (str(game_id), model_id)
                if key in seen_avaa:
                    continue
                seen_avaa.add(key)

            accuracy = row.get("accuracy")
            if accuracy is None:
                continue
            quality_games[model_id] += 1
            acc_sum[model_id] += float(accuracy)
            acc_n[model_id] += 1

        out: Dict[str, Dict[str, Any]] = {}
        for model_id in quality_games:
            entry: Dict[str, Any] = {"quality_games": quality_games[model_id]}
            if acc_n[model_id]:
                mean_accuracy = round(acc_sum[model_id] / acc_n[model_id], 2)
                entry["mean_accuracy"] = mean_accuracy
                entry["mean_play_rating"] = est_elo_from_accuracy(
                    mean_accuracy, root=cal_root
                )
            out[model_id] = entry
        return out

    def calculate_winrate(self, skill: Optional[int] = None) -> float:
        results = self.load_results()
        if skill is not None:
            results = [r for r in results if r.get("skill") == skill]
        if not results:
            return 0.0
        wins = 0.0
        total = 0
        for result in results:
            agent_color = result.get("agent_color")
            game_result = result.get("result")
            if agent_color is None or game_result is None:
                continue
            total += 1
            if game_result == "1/2-1/2":
                wins += 0.5
            elif (agent_color == "WHITE" and game_result == "1-0") or (
                agent_color == "BLACK" and game_result == "0-1"
            ):
                wins += 1
        return wins / total if total > 0 else 0.0

    def get_summary(self) -> Dict[str, Any]:
        results = self.load_results()
        wins = draws = losses = 0
        for result in results:
            agent_color = result.get("agent_color")
            game_result = result.get("result")
            if agent_color is None or game_result is None:
                continue
            if game_result == "1/2-1/2":
                draws += 1
            elif (agent_color == "WHITE" and game_result == "1-0") or (
                agent_color == "BLACK" and game_result == "0-1"
            ):
                wins += 1
            else:
                losses += 1

        ladder = ELOLadder(base_dir=str(self.base_dir))
        catalog = get_catalog()
        by_opponent = self.aggregate_by_opponent()
        opponent_summary = {}
        for oid, stats in by_opponent.items():
            try:
                opp = catalog.get(oid)
                opponent_summary[oid] = {
                    **stats,
                    "label": opp.format_label(),
                    "elo": opp.elo,
                }
            except ValueError:
                opponent_summary[oid] = {**stats, "label": oid, "elo": None}

        return {
            "total_games": len(results),
            "wins": wins,
            "draws": draws,
            "losses": losses,
            "winrate": round(self.calculate_winrate(), 3),
            "leaderboard": ladder.get_leaderboard(),
            "by_opponent": opponent_summary,
        }
