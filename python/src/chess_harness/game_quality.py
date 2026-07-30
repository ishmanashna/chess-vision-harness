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
COMPOSITE_Q_ALPHA = 8.0
COMPOSITE_Q_BETA = 25.0
TRIM_PLY_FRACTION = 0.10
MIN_PLY_AFTER_TRIM = 3
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
    q_midgame: Optional[float] = None
    q_trimmed: Optional[float] = None


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


def composite_q_value(
    accuracy: Optional[float],
    normalized_acpl: Optional[float],
    blunder_rate: Optional[float],
) -> Optional[float]:
    """Q = accuracy − α·normalized_acpl − β·blunder_rate."""
    if accuracy is None or normalized_acpl is None or blunder_rate is None:
        return None
    return (
        accuracy
        - COMPOSITE_Q_ALPHA * normalized_acpl
        - COMPOSITE_Q_BETA * blunder_rate
    )


def _material_factor(board: chess.Board) -> float:
    """Down-weight quiet low-material endings (1.0 early, ~0.25 in bare endings)."""
    piece_count = len(board.piece_map())
    if piece_count >= 24:
        return 1.0
    if piece_count <= 8:
        return 0.25
    return 0.25 + (piece_count - 8) * (0.75 / 16.0)


def _weighted_mean(values: Sequence[float], weights: Sequence[float]) -> float:
    total_w = sum(weights)
    if total_w <= 0:
        return sum(values) / len(values)
    return sum(v * w for v, w in zip(values, weights)) / total_w


def _trim_drop_indices(n: int, swings: Sequence[float]) -> set[int]:
    if n <= MIN_PLY_AFTER_TRIM:
        return set()
    n_drop = max(1, int(n * TRIM_PLY_FRACTION))
    n_drop = min(n_drop, n - MIN_PLY_AFTER_TRIM)
    ranked = sorted(range(n), key=lambda i: swings[i], reverse=True)
    return set(ranked[:n_drop])


@dataclass
class _SidePlyData:
    """Per-side ply records in move order (one entry per move by this side)."""

    cp_losses: List[int]
    swings: List[float]
    blunder_flags: List[bool]
    material_weights: List[float]
    accuracies: List[Optional[float]]
    ply_idxs: List[int]
    vol_weights: List[float]


def _side_from_ply_data(
    data: _SidePlyData,
    *,
    cp_weights: Optional[Sequence[float]] = None,
    drop_indices: Optional[set[int]] = None,
) -> SideQuality:
    n = len(data.cp_losses)
    if n == 0:
        return SideQuality(None, None, None, None, 0, 0)

    drop = drop_indices or set()
    kept = [i for i in range(n) if i not in drop]
    if not kept:
        return SideQuality(None, None, None, None, 0, 0)

    ply_w = list(cp_weights) if cp_weights is not None else [1.0] * n
    kept_losses = [float(data.cp_losses[i]) for i in kept]
    kept_ply_w = [ply_w[i] for i in kept]
    acpl = _weighted_mean(kept_losses, kept_ply_w)
    blunder_count = sum(1 for i in kept if data.blunder_flags[i])
    blunder_rate = blunder_count / len(kept)

    kept_acc: List[float] = []
    kept_acc_w: List[float] = []
    for cp_i in kept:
        acc = data.accuracies[cp_i]
        if acc is None:
            continue
        kept_acc.append(acc)
        vol_w = data.vol_weights[cp_i] if cp_i < len(data.vol_weights) else 1.0
        kept_acc_w.append(vol_w * ply_w[cp_i])

    accuracy = _mean_stats(kept_acc, kept_acc_w) if kept_acc else None
    normalized_acpl = acpl / ACPL_NORMALIZER
    return SideQuality(
        accuracy=accuracy,
        acpl=acpl,
        normalized_acpl=normalized_acpl,
        blunder_rate=blunder_rate,
        move_count=len(kept),
        blunder_count=blunder_count,
    )


def _finalize_side(data: _SidePlyData) -> SideQuality:
    standard = _side_from_ply_data(data)
    mid_cp_w = [
        vol * mat for vol, mat in zip(data.vol_weights, data.material_weights)
    ]
    midgame = _side_from_ply_data(data, cp_weights=mid_cp_w)
    trimmed = _side_from_ply_data(
        data, drop_indices=_trim_drop_indices(len(data.cp_losses), data.swings)
    )
    standard.q_midgame = composite_q_value(
        midgame.accuracy, midgame.normalized_acpl, midgame.blunder_rate
    )
    standard.q_trimmed = composite_q_value(
        trimmed.accuracy, trimmed.normalized_acpl, trimmed.blunder_rate
    )
    return standard


def _empty_side_data() -> _SidePlyData:
    return _SidePlyData([], [], [], [], [], [], [])


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

    white_data = _empty_side_data()
    black_data = _empty_side_data()
    all_wps: List[float] = [_win_percent(INITIAL_POSITION_CP)]

    try:
        for ply_idx, uci in enumerate(uci_moves):
            mover = board.turn
            material = _material_factor(board)
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
            swing = max(0.0, wp_before - wp_after)
            is_blunder = swing / 100.0 > BLUNDER_WIN_PROB_LOSS
            cp_loss = max(0, score_before - score_after)
            skip_accuracy = cp_loss >= MATE_MISS_THRESHOLD
            accuracy = None if skip_accuracy else _move_accuracy(wp_before, wp_after)

            target = white_data if mover == chess.WHITE else black_data
            target.cp_losses.append(cp_loss)
            target.swings.append(swing)
            target.blunder_flags.append(is_blunder)
            target.material_weights.append(material)
            target.accuracies.append(accuracy)
            target.ply_idxs.append(ply_idx)

        ply_weights = _ply_weights(all_wps, len(uci_moves))
        for data in (white_data, black_data):
            data.vol_weights = [
                ply_weights[i] if i < len(ply_weights) else 1.0 for i in data.ply_idxs
            ]

        white_moves = (len(uci_moves) + 1) // 2
        black_moves = len(uci_moves) // 2

        return GameQuality(
            quality_depth=quality_depth,
            quality_thin=white_moves < THIN_MOVES_PER_SIDE or black_moves < THIN_MOVES_PER_SIDE,
            white=_finalize_side(white_data),
            black=_finalize_side(black_data),
        )
    finally:
        if owned_engine is not None:
            owned_engine.quit()
