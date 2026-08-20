"""Indexed puzzle dataset access for the agent API (/api/v1/puzzles).

Read-only access into the runtime store written by ``puzzle_import``. This
module never publishes hidden puzzle metadata before an attempt completes;
selection returns puzzle records that contain the solution — the API layer is
responsible for keeping those fields private until completion.
"""

from __future__ import annotations

import json
import random
import statistics
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import chess

from .paths import resolve_puzzle_dataset_file, resolve_puzzle_manifest_file

__all__ = ["PuzzleStore"]


class PuzzleStore:
    """Read-only access to the indexed puzzle dataset."""

    def __init__(
        self,
        dataset_path: Optional[Path] = None,
        manifest_path: Optional[Path] = None,
        rng: Optional[random.Random] = None,
    ):
        self.dataset_path = dataset_path or resolve_puzzle_dataset_file()
        self.manifest_path = manifest_path or resolve_puzzle_manifest_file()
        self.rng = rng or random.Random()

    def load(self) -> Dict[str, Dict[str, Any]]:
        """Load {puzzle_id: record} from the indexed dataset file."""
        if not self.dataset_path.exists():
            return {}
        try:
            data = json.loads(self.dataset_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        puzzles = data.get("puzzles") if isinstance(data, dict) else None
        if not isinstance(puzzles, dict):
            return {}
        return puzzles

    def get(self, puzzle_id: str) -> Optional[Dict[str, Any]]:
        return self.load().get(puzzle_id)

    def count(self) -> int:
        return len(self.load())

    def ids(self) -> List[str]:
        return list(self.load().keys())

    def random_puzzle(
        self,
        *,
        rating_min: Optional[int] = None,
        rating_max: Optional[int] = None,
        theme: Optional[str] = None,
        exclusions: Optional[Iterable[str]] = None,
        rng: Optional[random.Random] = None,
    ) -> Optional[Dict[str, Any]]:
        """Pick a random eligible puzzle (optionally filtered).

        ``theme`` matches a substring of the puzzle's themes (e.g. ``mateIn2``,
        ``sacrifice``). ``exclusions`` are puzzle ids to skip (recently
        attempted ones). Uses ``rng`` if given (seeded tests), else the store's
        own RNG.
        """
        choice_rng = rng or self.rng
        puzzles = self.load()
        exclude = set(exclusions or ())
        candidates: List[Dict[str, Any]] = []
        for puzzle_id, record in puzzles.items():
            if puzzle_id in exclude:
                continue
            rating = int(record.get("rating") or 0)
            if rating_min is not None and rating < rating_min:
                continue
            if rating_max is not None and rating > rating_max:
                continue
            if theme:
                themes = " ".join(record.get("themes") or [])
                if theme.lower() not in themes.lower():
                    continue
            candidates.append(record)
        if not candidates:
            return None
        return dict(choice_rng.choice(candidates))

    def filterable_themes(self) -> List[str]:
        """Distinct imported themes (safe for a filter menu)."""
        themes: set[str] = set()
        for record in self.load().values():
            for theme in record.get("themes") or []:
                themes.add(str(theme))
        return sorted(themes)

    def manifest(self) -> Dict[str, Any]:
        if not self.manifest_path.exists():
            return {"version": 1, "dataset_version": "unknown", "counts": {"total": self.count()}}
        try:
            return json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def stats(self) -> Dict[str, Any]:
        puzzles = self.load()
        totals: Dict[str, int] = {}
        ratings: List[int] = []
        buckets = {
            "under_600": 0,
            "600_800": 0,
            "800_1000": 0,
            "1000_1200": 0,
            "1200_1500": 0,
            "1500_plus": 0,
        }
        side_to_move = {"white": 0, "black": 0}
        for record in puzzles.values():
            for theme in record.get("themes") or []:
                totals[str(theme)] = totals.get(str(theme), 0) + 1
            rating = int(record.get("rating") or 0)
            ratings.append(rating)
            if rating < 600:
                buckets["under_600"] += 1
            elif rating < 800:
                buckets["600_800"] += 1
            elif rating < 1000:
                buckets["800_1000"] += 1
            elif rating < 1200:
                buckets["1000_1200"] += 1
            elif rating < 1500:
                buckets["1200_1500"] += 1
            else:
                buckets["1500_plus"] += 1
            fen = str(record.get("display_fen") or "")
            if fen:
                try:
                    turn = chess.Board(fen).turn
                    side_to_move["white" if turn == chess.WHITE else "black"] += 1
                except ValueError:
                    pass
        total = len(puzzles)
        avg = 0.0
        if total:
            avg = sum(ratings) / total
        payload: Dict[str, Any] = {
            "total": total,
            "themes": totals,
            "average_rating": round(avg, 1),
            "rating_min": min(ratings) if ratings else None,
            "rating_max": max(ratings) if ratings else None,
            "rating_mean": round(avg, 1) if total else None,
            "rating_median": round(statistics.median(ratings), 1) if ratings else None,
            "buckets": buckets,
            "side_to_move": side_to_move,
        }
        return payload