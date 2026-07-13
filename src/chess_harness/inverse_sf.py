"""Stockfish inverse opponents: pick deliberately bad moves by eval ranking."""

from __future__ import annotations

import random
from typing import Any, Dict, List, Optional, Tuple

import chess
import chess.engine

INVERSE_MODES = frozenset(
    {
        "exclude_top1",
        "exclude_top2",
        "exclude_top3",
        "second_worst",
        "third_worst",
        "worst",
        "bottom3",
        "bottom5",
        "bottom_half",
    }
)


def _score_cp(score: chess.engine.Score) -> float:
    """Centipawns from the perspective of the side that just moved (parent position)."""
    cp = score.relative.score(mate_score=100_000)
    if cp is None:
        mate = score.relative.mate()
        if mate is None:
            return 0.0
        return 100_000.0 if mate > 0 else -100_000.0
    return float(cp)


def rank_legal_moves(
    engine: chess.engine.SimpleEngine,
    board: chess.Board,
    *,
    depth: int,
    movetime_ms: int = 100,
) -> List[Tuple[chess.Move, float]]:
    """Rank legal moves best-first (highest eval for side to move)."""
    legal = list(board.legal_moves)
    if not legal:
        raise chess.engine.EngineError("No legal moves")

    time_limit = max(movetime_ms / 1000.0, 0.01)
    per_move_time = max(time_limit / max(len(legal), 1), 0.005)
    ranked: List[Tuple[chess.Move, float]] = []

    for move in legal:
        board.push(move)
        try:
            info = engine.analyse(
                board,
                chess.engine.Limit(depth=depth, time=per_move_time),
            )
            ranked.append((move, -_score_cp(info["score"])))
        finally:
            board.pop()

    ranked.sort(key=lambda item: item[1], reverse=True)
    return ranked


def pick_inverse_move(
    ranked: List[Tuple[chess.Move, float]],
    mode: str,
) -> chess.Move:
    """Select a move from a best-first ranked list using an inverse mode."""
    if mode not in INVERSE_MODES:
        raise ValueError(f"Unknown inverse mode: {mode}")

    n = len(ranked)
    if n == 1:
        return ranked[0][0]

    if mode == "exclude_top1":
        pool = [m for m, _ in ranked[1:]]
        return random.choice(pool)
    if mode == "exclude_top2":
        pool = [m for m, _ in ranked[2:]] if n > 2 else [ranked[-1][0]]
        return random.choice(pool)
    if mode == "exclude_top3":
        pool = [m for m, _ in ranked[3:]] if n > 3 else [ranked[-1][0]]
        return random.choice(pool)
    if mode == "second_worst":
        return ranked[-2][0] if n >= 2 else ranked[-1][0]
    if mode == "third_worst":
        return ranked[-3][0] if n >= 3 else ranked[-1][0]
    if mode == "worst":
        return ranked[-1][0]
    if mode == "bottom3":
        pool = [m for m, _ in ranked[-min(3, n) :]]
        return random.choice(pool)
    if mode == "bottom5":
        pool = [m for m, _ in ranked[-min(5, n) :]]
        return random.choice(pool)
    if mode == "bottom_half":
        start = n // 2
        pool = [m for m, _ in ranked[start:]]
        return random.choice(pool)

    return ranked[-1][0]


def play_inverse_sf_move(
    engine: chess.engine.SimpleEngine,
    board: chess.Board,
    inverse: Optional[Dict[str, Any]],
) -> chess.Move:
    cfg = inverse or {}
    mode = str(cfg.get("mode", "worst"))
    depth = int(cfg.get("depth", 10))
    movetime_ms = int(cfg.get("movetime_ms", 100))
    ranked = rank_legal_moves(engine, board, depth=depth, movetime_ms=movetime_ms)
    return pick_inverse_move(ranked, mode)
