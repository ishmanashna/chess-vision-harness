"""Puzzle and board-identification leaderboard builders (Phase 9).

These views aggregate the puzzle attempt / identification stores and the
Glicko-2 puzzle ratings into two dedicated snapshot shapes. They stay
independent of game Elo, Play rating, and human browser credentials; they
never touch ``results.jsonl``, ``models.json`` Elo, or the finished-games
database.

- ``build_puzzle_leaderboard``: per-agent puzzle rating, deviation, attempts,
  solves and solve rate, plus a puzzle content view (difficulty, solve rate,
  themes, popularity, source, latest replay watch url) in an observer/
  replay scope.
- ``build_identify_leaderboard``: per-agent mean placement accuracy, finished
  attempts, and full-position solve rate (identification has no rating yet).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .identify_attempt import IdentifyAttemptStore
from .models import ModelRegistry
from .puzzle_attempt import PuzzleAttemptStore
from .puzzle_ratings import PuzzleRatingStore
from .puzzle_store import PuzzleStore

__all__ = ["build_puzzle_leaderboard", "build_identify_leaderboard"]

DATA_VERSION = 1

# Cap for the puzzle content view (most-attempted puzzles first).
PUZZLE_CONTENT_LIMIT = 25


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _finished(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [
        record
        for record in records
        if record.get("status") == "finished"
        and record.get("result") in ("correct", "failed")
    ]


def _agent_names(
    model_ids: set, registry: Optional[ModelRegistry]
) -> Dict[str, str]:
    """Display names from the model registry; fall back to the model id."""
    names: Dict[str, str] = {mid: mid for mid in model_ids if mid}
    if registry is None:
        return names
    try:
        for model in registry.list_models():
            mid = str(model.get("id") or "")
            if mid:
                names[mid] = str(model.get("name") or mid)
    except Exception:
        pass
    return names


def _row_rate(solves: int, attempts: int) -> Optional[float]:
    return round(solves / attempts, 4) if attempts else None


def build_puzzle_leaderboard(
    *,
    ratings: Optional[PuzzleRatingStore] = None,
    attempts: Optional[PuzzleAttemptStore] = None,
    puzzles: Optional[PuzzleStore] = None,
    registry: Optional[ModelRegistry] = None,
) -> Dict[str, Any]:
    """Puzzle leaderboard: rated agents + attempted-puzzle content view."""
    rating_store = ratings or PuzzleRatingStore()
    attempt_store = attempts or PuzzleAttemptStore()
    puzzle_store = puzzles or PuzzleStore()
    snap = rating_store.snapshot()
    agent_ratings = snap.get("agents", {})

    finished = _finished(attempt_store.list_records())

    by_model: Dict[str, Dict[str, int]] = {}
    by_puzzle: Dict[str, Dict[str, int]] = {}
    latest_attempt: Dict[str, str] = {}
    latest_started: Dict[str, str] = {}
    for record in finished:
        model_id = str(record.get("model_id") or "")
        if model_id:
            entry = by_model.setdefault(model_id, {"attempts": 0, "solves": 0})
            entry["attempts"] += 1
            if record.get("result") == "correct":
                entry["solves"] += 1
        puzzle_id = str(record.get("puzzle_id") or "")
        if puzzle_id:
            entry = by_puzzle.setdefault(puzzle_id, {"attempts": 0, "solves": 0})
            entry["attempts"] += 1
            if record.get("result") == "correct":
                entry["solves"] += 1
            started = str(record.get("started_at") or "")
            if started > latest_started.get(puzzle_id, ""):
                latest_started[puzzle_id] = started
                latest_attempt[puzzle_id] = str(record.get("attempt_id") or "")

    model_ids = set(agent_ratings) | set(by_model)
    names = _agent_names(model_ids, registry)

    agents: List[Dict[str, Any]] = []
    for model_id in sorted(model_ids):
        rating = agent_ratings.get(model_id) or {}
        stats = by_model.get(model_id, {"attempts": 0, "solves": 0})
        agents.append(
            {
                "id": model_id,
                "name": names.get(model_id, model_id),
                "rating": rating.get("rating"),
                "deviation": rating.get("deviation"),
                "attempts": stats["attempts"],
                "solves": stats["solves"],
                "solve_rate": _row_rate(stats["solves"], stats["attempts"]),
            }
        )
    agents.sort(
        key=lambda a: (
            a["rating"] is None,
            -(a["rating"] or 0),
            str(a["name"]).lower(),
        )
    )

    puzzle_rows: List[Dict[str, Any]] = []
    for puzzle_id, stats in by_puzzle.items():
        content = puzzle_store.get(puzzle_id) or {}
        # Difficulty is frozen at the imported Lichess estimate (Phase B):
        # agents are rated against it, but the puzzle side never moves.
        difficulty = float(content.get("rating") or 0) or None
        puzzle_rows.append(
            {
                "id": puzzle_id,
                "rating": difficulty,
                "deviation": float(content.get("rating_deviation") or 0) or None,
                "attempts": stats["attempts"],
                "solves": stats["solves"],
                "solve_rate": _row_rate(stats["solves"], stats["attempts"]),
                "themes": list(content.get("themes") or []),
                "popularity": content.get("popularity"),
                "nb_plays": content.get("nb_plays"),
                "source": content.get("game_url") or "",
                "watch_url": (
                    f"/p/{latest_attempt[puzzle_id]}"
                    if latest_attempt.get(puzzle_id)
                    else None
                ),
            }
        )
    puzzle_rows.sort(
        key=lambda p: (
            -p["attempts"],
            -float(p["rating"] or 0),
            str(p["id"]),
        )
    )
    puzzle_rows = puzzle_rows[:PUZZLE_CONTENT_LIMIT]

    return {
        "version": DATA_VERSION,
        "generated_at": _now(),
        "agents": agents,
        "puzzles": puzzle_rows,
    }


def build_identify_leaderboard(
    *,
    attempts: Optional[IdentifyAttemptStore] = None,
    registry: Optional[ModelRegistry] = None,
) -> Dict[str, Any]:
    """Board-identification leaderboard (mean accuracy, attempts, full-position)."""
    store = attempts or IdentifyAttemptStore()
    scored: Dict[str, Dict[str, Any]] = {}
    for record in store.list_records():
        if record.get("status") != "finished":
            continue
        score = record.get("score")
        if not isinstance(score, dict) or score.get("accuracy") is None:
            continue
        model_id = str(record.get("model_id") or "")
        if not model_id:
            continue
        entry = scored.setdefault(
            model_id, {"attempts": 0, "acc_sum": 0.0, "full": 0}
        )
        entry["attempts"] += 1
        entry["acc_sum"] += float(score["accuracy"])
        if score.get("full_position"):
            entry["full"] += 1

    names = _agent_names(set(scored), registry)
    agents: List[Dict[str, Any]] = []
    for model_id, entry in scored.items():
        attempts = entry["attempts"]
        agents.append(
            {
                "id": model_id,
                "name": names.get(model_id, model_id),
                "attempts": attempts,
                "mean_accuracy": round(entry["acc_sum"] / attempts, 4),
                "full_position_rate": round(entry["full"] / attempts, 4),
            }
        )
    agents.sort(
        key=lambda a: (
            -a["mean_accuracy"],
            -a["attempts"],
            str(a["name"]).lower(),
        )
    )
    return {
        "version": DATA_VERSION,
        "generated_at": _now(),
        "agents": agents,
    }