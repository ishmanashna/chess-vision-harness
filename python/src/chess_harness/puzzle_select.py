"""Puzzle and identify position selection tuned to agent skill.

When the client omits ``rating_min`` and ``rating_max``, puzzles band around
the agent's puzzle Glicko (new agents start at 800). Identify bands around the
easy end of the corpus until the model has enough finished attempts. Empty bands
widen until the corpus yields a hit — a non-empty store never 404s solely
because the initial band was tight.
"""

from __future__ import annotations

from typing import Iterable, Optional

from .identify_attempt import IdentifyAttemptStore
from .puzzle_ratings import AGENT_START_RATING, PuzzleRatingStore
from .puzzle_store import PuzzleStore

__all__ = [
    "select_identify_position",
    "select_puzzle_for_agent",
]

HALF_WINDOW = 200
RD_PROVISIONAL_THRESHOLD = 200
WIDEN_STEP = 200
IDENTIFY_NOVICE_ATTEMPTS = 10
IDENTIFY_SATURATED_HALF = 400


def _rating_bounds(store: PuzzleStore) -> tuple[int, int]:
    ratings = [int(record.get("rating") or 0) for record in store.load().values()]
    if not ratings:
        return 0, -1
    return min(ratings), max(ratings)


def _agent_auto_band(agent_rating: float, agent_rd: float) -> tuple[int, int]:
    extra_down = max(0.0, agent_rd - RD_PROVISIONAL_THRESHOLD)
    rating_min = int(agent_rating - HALF_WINDOW - extra_down)
    rating_max = int(agent_rating + HALF_WINDOW)
    return rating_min, rating_max


def _identify_auto_band(store: PuzzleStore, finished_attempts: int) -> tuple[int, int]:
    corpus_min, corpus_max = _rating_bounds(store)
    if corpus_max < corpus_min:
        return 0, -1

    if finished_attempts < IDENTIFY_NOVICE_ATTEMPTS:
        # Prefer the easy end; allow slightly harder puzzles as experience grows.
        growth = min(finished_attempts * 30, HALF_WINDOW)
        return corpus_min, corpus_min + HALF_WINDOW + growth

    puzzles = store.load().values()
    avg = sum(int(record.get("rating") or 0) for record in puzzles) / len(puzzles)
    return int(avg - IDENTIFY_SATURATED_HALF), int(avg + IDENTIFY_SATURATED_HALF)


def _select_with_widen(
    store: PuzzleStore,
    rating_min: int,
    rating_max: int,
    *,
    theme: Optional[str] = None,
    exclusions: Optional[Iterable[str]] = None,
) -> Optional[dict]:
    corpus_min, corpus_max = _rating_bounds(store)
    if corpus_max < corpus_min:
        return None

    lo, hi = rating_min, rating_max
    while True:
        record = store.random_puzzle(
            rating_min=lo,
            rating_max=hi,
            theme=theme or None,
            exclusions=exclusions,
        )
        if record is not None:
            return record
        if lo <= corpus_min and hi >= corpus_max:
            return None
        lo -= WIDEN_STEP
        hi += WIDEN_STEP


def _client_pinned_band(
    rating_min: Optional[int], rating_max: Optional[int]
) -> bool:
    return rating_min is not None or rating_max is not None


def select_puzzle_for_agent(
    *,
    model_id: str,
    rating_min: Optional[int] = None,
    rating_max: Optional[int] = None,
    theme: Optional[str] = None,
    exclusions: Optional[Iterable[str]] = None,
    puzzle_store: Optional[PuzzleStore] = None,
    rating_store: Optional[PuzzleRatingStore] = None,
) -> Optional[dict]:
    """Pick a puzzle for ``POST /puzzles/start``."""
    store = puzzle_store or PuzzleStore()
    if _client_pinned_band(rating_min, rating_max):
        return store.random_puzzle(
            rating_min=rating_min,
            rating_max=rating_max,
            theme=theme or None,
            exclusions=exclusions,
        )

    agent = (rating_store or PuzzleRatingStore()).agent_rating(model_id)
    band_min, band_max = _agent_auto_band(
        float(agent.get("rating") or AGENT_START_RATING),
        float(agent.get("deviation") or 350),
    )
    return _select_with_widen(
        store,
        band_min,
        band_max,
        theme=theme or None,
        exclusions=exclusions,
    )


def select_identify_position(
    *,
    model_id: str,
    rating_min: Optional[int] = None,
    rating_max: Optional[int] = None,
    exclusions: Optional[Iterable[str]] = None,
    puzzle_store: Optional[PuzzleStore] = None,
    identify_store: Optional[IdentifyAttemptStore] = None,
) -> Optional[dict]:
    """Pick a corpus position for ``POST /identify/start``."""
    store = puzzle_store or PuzzleStore()
    if _client_pinned_band(rating_min, rating_max):
        return store.random_puzzle(
            rating_min=rating_min,
            rating_max=rating_max,
            exclusions=exclusions,
        )

    finished = (identify_store or IdentifyAttemptStore()).finished_count(model_id)
    band_min, band_max = _identify_auto_band(store, finished)
    return _select_with_widen(
        store,
        band_min,
        band_max,
        exclusions=exclusions,
    )
