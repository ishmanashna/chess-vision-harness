"""
Post-game move-quality analysis (Lichess-inspired, open formula).

Constants (locked for v1):
- WIN_PROB_COEFF (0.00368208): logistic cp → win probability.
- WIN_PROB_CP_CAP (1000): clamp cp before win-prob conversion.
- INITIAL_POSITION_CP (15): starting eval anchor (Lichess Cp.initial).
- ACCURACY_A/B/C + UNCERTAINTY_BONUS (1): per-move accuracy curve.
- SLIDING_WINDOW_MIN/MAX (2/8), VOLATILITY_WEIGHT_MIN/MAX (0.5/12).
- MATE_CP (10000), MATE_MISS_THRESHOLD (6667): mate sentinel handling.
- BLUNDER_WIN_PROB_LOSS (0.30): Lichess blunder threshold (0–1 win chance).
- THIN_MOVES_PER_SIDE (5): fewer plies per side → quality_thin.
- ACPL_NORMALIZER (100): normalized_acpl for Phase 4 Q.
- DEFAULT_QUALITY_DEPTH (8) / env QUALITY_STOCKFISH_DEPTH.

Does not touch ladder Elo, CalibrationLadder, or models.json.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass
from io import StringIO
from typing import Callable, List, Optional, Sequence, Union

import chess
import chess.pgn

from .engine import EvalEngineAdapter

WIN_PROB_COEFF = 0.00368208
WIN_PROB_CP_CAP = 1000
INITIAL_POSITION_CP = 15
ACCURACY_A = 103.1668100711649
ACCURACY_B = -0.04354415386753951
ACCURACY_C = -3.166924740191411
UNCERTAINTY_BONUS = 1.0
SLIDING_WINDOW_MIN = 2
SLIDING_WINDOW_MAX = 8
VOLATILITY_WEIGHT_MIN = 0.5
VOLATILITY_WEIGHT_MAX = 12.0
MATE_CP = 10000
MATE_MISS_THRESHOLD = MATE_CP * 2 // 3
BLUNDER_WIN_PROB_LOSS = 0.30
THIN_MOVES_PER_SIDE = 5
ACPL_NORMALIZER = 100.0
DEFAULT_QUALITY_DEPTH = 8
QUALITY_DEPTH_ENV = "QUALITY_STOCKFISH_DEPTH"

EvalFn = Callable[[chess.Board], Optional[int]]
PgnOrMoves = Union[str, Sequence[str]]


@dataclass
class SideQuality:
    """Per-side metrics; sufficient for Phase 4 play-rating Q."""

    accuracy: Optional[float]
    acpl: Optional[float]
    normalized_acpl: Optional[float]
    blunder_rate: Optional[float]
    move_count: int
    blunder_count: int = 0


@dataclass
class GameQuality:
    quality_depth: int
    quality_thin: bool
    white: SideQuality
    black: SideQuality
    start_color: chess.Color = chess.WHITE


def default_quality_depth() -> int:
    raw = os.environ.get(QUALITY_DEPTH_ENV)
    if raw is None:
        return DEFAULT_QUALITY_DEPTH
    try:
        return max(1, int(raw))
    except ValueError:
        return DEFAULT_QUALITY_DEPTH


def _win_percent(cp: int) -> float:
    c = max(-WIN_PROB_CP_CAP, min(WIN_PROB_CP_CAP, cp))
    return 100.0 / (1.0 + math.exp(-WIN_PROB_COEFF * c))


def _move_accuracy(wp_before: float, wp_after: float) -> float:
    if wp_after >= wp_before:
        return 100.0
    diff = wp_before - wp_after
    raw = ACCURACY_A * math.exp(ACCURACY_B * diff) + ACCURACY_C + UNCERTAINTY_BONUS
    return max(0.0, min(100.0, raw))


def _position_cp(board: chess.Board, eval_fn: EvalFn) -> Optional[int]:
    if board.is_checkmate():
        return -MATE_CP if board.turn == chess.WHITE else MATE_CP
    if board.is_game_over():
        return 0
    return eval_fn(board)


def _parse_moves(pgn_or_moves: PgnOrMoves) -> List[str]:
    if isinstance(pgn_or_moves, str):
        game = chess.pgn.read_game(StringIO(pgn_or_moves))
        if game is None:
            raise ValueError("invalid PGN")
        return [node.move.uci() for node in game.mainline()]
    return list(pgn_or_moves)


def _mean_stats(accuracies: List[float], weights: List[float]) -> Optional[float]:
    if not accuracies:
        return None
    if len(accuracies) == 1:
        return accuracies[0]
    sum_wv, sum_w = 0.0, 0.0
    for i, v in enumerate(accuracies):
        w = weights[i] if i < len(weights) else 1.0
        sum_wv += v * w
        sum_w += w
    wm = sum_wv / sum_w if sum_w > 0 else sum(accuracies) / len(accuracies)
    hm_inv = sum(1.0 / (v if v > 0 else 0.01) for v in accuracies)
    hm = len(accuracies) / hm_inv
    return (wm + hm) / 2.0


def _ply_weights(all_wps: List[float], n_moves: int) -> List[float]:
    if n_moves == 0:
        return []
    wsize = max(SLIDING_WINDOW_MIN, min(SLIDING_WINDOW_MAX, n_moves // 10))
    first = all_wps[:wsize]
    pad = max(0, wsize - 2)
    weights: List[float] = []
    for i in range(n_moves):
        start = 0 if i < pad else i - pad
        window = first if i < pad else all_wps[start:start + wsize]
        if len(window) < 2:
            sd = 0.0
        else:
            mean = sum(window) / len(window)
            sd = math.sqrt(sum((v - mean) ** 2 for v in window) / len(window))
        weights.append(max(VOLATILITY_WEIGHT_MIN, min(VOLATILITY_WEIGHT_MAX, sd)))
    return weights


def _build_side(
    accuracies: List[float],
    weights: List[float],
    cp_losses: List[int],
    blunder_count: int,
) -> SideQuality:
    n = len(cp_losses)
    if n == 0:
        return SideQuality(None, None, None, None, 0, 0)
    acpl = sum(cp_losses) / n
    return SideQuality(
        accuracy=_mean_stats(accuracies, weights),
        acpl=acpl,
        normalized_acpl=acpl / ACPL_NORMALIZER,
        blunder_rate=blunder_count / n,
        move_count=n,
        blunder_count=blunder_count,
    )


def analyse_game(
    pgn_or_moves: PgnOrMoves,
    depth: Optional[int] = None,
    eval_fn: Optional[EvalFn] = None,
) -> GameQuality:
    """Replay a finished game; ``eval_fn`` injects white cp (for tests)."""
    quality_depth = depth if depth is not None else default_quality_depth()
    uci_moves = _parse_moves(pgn_or_moves)
    board = chess.Board()
    owned_engine: Optional[EvalEngineAdapter] = None

    if eval_fn is None:
        owned_engine = EvalEngineAdapter()
        engine = owned_engine
        eval_fn = lambda b: engine.evaluate(b, depth=quality_depth)

    white_acc: List[float] = []
    black_acc: List[float] = []
    white_ply_idxs: List[int] = []
    black_ply_idxs: List[int] = []
    white_losses: List[int] = []
    black_losses: List[int] = []
    white_blunders = 0
    black_blunders = 0
    all_wps: List[float] = [_win_percent(INITIAL_POSITION_CP)]

    try:
        for ply_idx, uci in enumerate(uci_moves):
            mover = board.turn
            cp_white_before = _position_cp(board, eval_fn)
            if cp_white_before is None:
                break
            score_before = cp_white_before if mover == chess.WHITE else -cp_white_before

            board.push(chess.Move.from_uci(uci))

            cp_white_after = _position_cp(board, eval_fn)
            if cp_white_after is None:
                break
            score_after = cp_white_after if mover == chess.WHITE else -cp_white_after

            all_wps.append(
                _win_percent(cp_white_after)
                if mover == chess.WHITE
                else 100.0 - _win_percent(-cp_white_after)
            )

            wp_before = _win_percent(score_before)
            wp_after = _win_percent(score_after)
            is_blunder = (wp_before - wp_after) / 100.0 > BLUNDER_WIN_PROB_LOSS
            cp_loss = max(0, score_before - score_after)
            skip_accuracy = cp_loss >= MATE_MISS_THRESHOLD

            if mover == chess.WHITE:
                white_losses.append(cp_loss)
                if is_blunder:
                    white_blunders += 1
                if not skip_accuracy:
                    white_acc.append(_move_accuracy(wp_before, wp_after))
                    white_ply_idxs.append(ply_idx)
            else:
                black_losses.append(cp_loss)
                if is_blunder:
                    black_blunders += 1
                if not skip_accuracy:
                    black_acc.append(_move_accuracy(wp_before, wp_after))
                    black_ply_idxs.append(ply_idx)

        ply_weights = _ply_weights(all_wps, len(uci_moves))
        white_weights = [ply_weights[i] for i in white_ply_idxs if i < len(ply_weights)]
        black_weights = [ply_weights[i] for i in black_ply_idxs if i < len(ply_weights)]
        white_moves = (len(uci_moves) + 1) // 2
        black_moves = len(uci_moves) // 2

        return GameQuality(
            quality_depth=quality_depth,
            quality_thin=white_moves < THIN_MOVES_PER_SIDE or black_moves < THIN_MOVES_PER_SIDE,
            white=_build_side(white_acc, white_weights, white_losses, white_blunders),
            black=_build_side(black_acc, black_weights, black_losses, black_blunders),
        )
    finally:
        if owned_engine is not None:
            owned_engine.quit()
