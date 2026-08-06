"""Persistent Glicko-2 puzzle ratings (agents and runtime puzzle difficulty).

Rated attempts are "games" between the solver and the puzzle: a correct
finish is an agent win and a puzzle loss; a wrong/illegal answer is a puzzle
win and an agent loss; abandon and technical failures never change ratings.

``$CHESS_HARNESS_DIR/puzzle_ratings.json`` holds:

- ``agents``: per-model puzzle ratings (keyed by model id). This store owns
  the agent's puzzle rating independently of ``models.json`` — ``inscribe``
  and ``reset_all_elo`` never touch it.
- ``puzzles``: runtime puzzle difficulty (keyed by puzzle id), seeded from
  the imported Rating / RatingDeviation and updated as attempts accumulate.
  Imported values are only starting estimates.

The attempt lifecycle (``puzzle_attempt``) records outcome and move detail;
this module only calculates and persists ratings, and returns the rating
fields that the API stamps back onto the attempt for replay.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import filelock

from .glicko2 import (
    DEFAULT_DEVIATION,
    DEFAULT_RATING,
    DEFAULT_VOLATILITY,
    GlickoRating,
    update_rating,
)
from .paths import resolve_puzzle_ratings_file
from .puzzle_store import PuzzleStore

__all__ = ["PuzzleRatingStore", "rating_fields_for_attempt"]

DATA_VERSION = 1


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def rating_fields_for_attempt(
    agent_before: GlickoRating,
    rating_after: GlickoRating,
    puzzle_before: GlickoRating,
    puzzle_after: GlickoRating,
    elapsed_seconds: Optional[float],
) -> Dict[str, Any]:
    """Stamping payload to merge back onto an attempt record (before/after)."""
    return {
        "rating_before": round(agent_before.rating, 1),
        "rating_after": round(rating_after.rating, 1),
        "rating_change": round(rating_after.rating - agent_before.rating, 1),
        "rating_deviation_before": round(agent_before.deviation, 1),
        "rating_deviation_after": round(rating_after.deviation, 1),
        "puzzle_rating_before": round(puzzle_before.rating, 1),
        "puzzle_rating_after": round(puzzle_after.rating, 1),
        "puzzle_rating_change": round(
            puzzle_after.rating - puzzle_before.rating, 1
        ),
        "elapsed_seconds": round(elapsed_seconds, 1) if elapsed_seconds is not None else None,
    }


class PuzzleRatingStore:
    """Atomic JSON store for Glicko-2 puzzle ratings (agents + puzzles)."""

    def __init__(self, path: Optional[Path] = None):
        self.path = path or resolve_puzzle_ratings_file()
        self._lock = filelock.FileLock(str(self.path) + ".lock", timeout=30)

    def _load(self) -> Dict[str, Any]:
        if not self.path.exists():
            return {"version": DATA_VERSION, "agents": {}, "puzzles": {}}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"version": DATA_VERSION, "agents": {}, "puzzles": {}}
        if not isinstance(data, dict):
            return {"version": DATA_VERSION, "agents": {}, "puzzles": {}}
        data.setdefault("agents", {})
        data.setdefault("puzzles", {})
        return data

    def _save(self, data: Dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(
            prefix=f"{self.path.name}.", dir=self.path.parent
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(data, stream, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp_name, self.path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)

    def _agent_record(self, data: Dict[str, Any], model_id: str) -> Dict[str, Any]:
        record = data["agents"].get(model_id)
        if record is None:
            return {
                "rating": DEFAULT_RATING,
                "deviation": DEFAULT_DEVIATION,
                "volatility": DEFAULT_VOLATILITY,
                "games": 0,
                "solves": 0,
                "updated_at": _now(),
            }
        return dict(record)

    def _puzzle_record(
        self, data: Dict[str, Any], puzzle_id: str
    ) -> Dict[str, Any]:
        record = data["puzzles"].get(puzzle_id)
        if record is not None:
            return dict(record)
        puzzle = PuzzleStore().get(puzzle_id) or {}
        return {
            "rating": float(puzzle.get("rating") or DEFAULT_RATING),
            "deviation": float(puzzle.get("rating_deviation") or DEFAULT_DEVIATION),
            "volatility": DEFAULT_VOLATILITY,
            "games": 0,
            "solves": 0,
            "updated_at": _now(),
        }

    def agent_rating(self, model_id: str) -> Dict[str, Any]:
        data = self._load()
        record = self._agent_record(data, model_id)
        return {
            "rating": round(record["rating"], 1),
            "deviation": round(record["deviation"], 1),
            "volatility": round(record["volatility"], 6),
            "games": record["games"],
            "solves": record["solves"],
        }

    def puzzle_rating(self, puzzle_id: str) -> Dict[str, Any]:
        data = self._load()
        record = self._puzzle_record(data, puzzle_id)
        return {
            "rating": round(record["rating"], 1),
            "deviation": round(record["deviation"], 1),
            "volatility": round(record["volatility"], 6),
            "games": record["games"],
            "solves": record["solves"],
        }

    def record_attempt(self, record: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Rate one finished puzzle attempt against its puzzle.

        Only ``correct`` and ``failed`` finishes rate (abandon / technical
        failures never change ratings). Idempotent: an attempt already stamped
        with ``rating_after`` is never re-rated. Mutates nothing but the
        ratings file; returns the fields to stamp onto the attempt record.
        """
        if record.get("status") != "finished":
            return None
        if record.get("result") not in ("correct", "failed"):
            return None
        if record.get("rating_after") is not None:
            return None

        model_id = str(record.get("model_id") or "")
        puzzle_id = str(record.get("puzzle_id") or "")
        score = 1.0 if record.get("result") == "correct" else 0.0

        with self._lock:
            data = self._load()
            agent = self._agent_record(data, model_id)
            puzzle = self._puzzle_record(data, puzzle_id)

            agent_before = GlickoRating(
                rating=agent["rating"],
                deviation=agent["deviation"],
                volatility=agent["volatility"],
            )
            puzzle_before = GlickoRating(
                rating=puzzle["rating"],
                deviation=puzzle["deviation"],
                volatility=puzzle["volatility"],
            )

            agent_after = update_rating(
                agent_before,
                puzzle_before.rating,
                puzzle_before.deviation,
                score,
            )
            puzzle_after = update_rating(
                puzzle_before,
                agent_before.rating,
                agent_before.deviation,
                1.0 - score,
            )

            agent["rating"] = agent_after.rating
            agent["deviation"] = agent_after.deviation
            agent["volatility"] = agent_after.volatility
            agent["games"] += 1
            agent["solves"] += 1 if score == 1.0 else 0
            agent["updated_at"] = _now()

            puzzle["rating"] = puzzle_after.rating
            puzzle["deviation"] = puzzle_after.deviation
            puzzle["volatility"] = puzzle_after.volatility
            puzzle["games"] += 1
            puzzle["solves"] += 1 if score == 1.0 else 0
            puzzle["updated_at"] = _now()

            data["agents"][model_id] = agent
            data["puzzles"][puzzle_id] = puzzle
            self._save(data)

        elapsed: Optional[float] = None
        try:
            start = datetime.fromisoformat(record.get("started_at") or "")
            done = datetime.fromisoformat(record.get("finished_at") or "")
            elapsed = (done - start).total_seconds()
        except (ValueError, TypeError):
            elapsed = None

        return rating_fields_for_attempt(
            agent_before, agent_after, puzzle_before, puzzle_after, elapsed
        )

    def snapshot(self) -> Dict[str, Any]:
        """Readable ratings summary (agents and puzzles), rounded."""
        data = self._load()
        agents = {
            model_id: {
                "rating": round(rec["rating"], 1),
                "deviation": round(rec["deviation"], 1),
                "games": rec["games"],
                "solves": rec["solves"],
            }
            for model_id, rec in data["agents"].items()
        }
        puzzles = {
            puzzle_id: {
                "rating": round(rec["rating"], 1),
                "deviation": round(rec["deviation"], 1),
                "games": rec["games"],
                "solves": rec["solves"],
            }
            for puzzle_id, rec in data["puzzles"].items()
        }
        return {"version": DATA_VERSION, "agents": agents, "puzzles": puzzles}