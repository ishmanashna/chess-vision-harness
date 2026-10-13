"""Conservative engine-verified ! / !! detection; candidate lines stay private.

Concepts: Chess.com's published Great/Brilliant definitions. Exact thresholds below
are this benchmark's own fixed policy, never adjusted by an agent's mapped rating.
"""
from __future__ import annotations

import math

import chess
import chess.engine

VERSION = "critical-sound-sacrifice-v1"
PROFILE = {"version": VERSION, "passes": [{"depth": 18, "seconds": .2, "minimum_depth": 14},
                                           {"depth": 22, "seconds": .8, "minimum_depth": 18}],
           "multipv": 2, "critical_gap_pp": 10, "minimum_chance": .45,
           "alternative_winning_chance": .85, "sacrifice_min_cp": 150}
VALUES = {chess.PAWN: 100, chess.KNIGHT: 300, chess.BISHOP: 300,
          chess.ROOK: 500, chess.QUEEN: 900, chess.KING: 20000}


def _chance(score):
    cp = score.score(mate_score=10000)
    return 1 / (1 + math.exp(-.00368208 * max(-1000, min(1000, cp))))


def _exchange_gain(board, square, budget, depth=10):
    """Legal capture-tree material gain; unknown if the bounded tree is exhausted."""
    captures = [move for move in board.legal_moves if move.to_square == square and board.is_capture(move)]
    if not captures:
        return 0
    if depth <= 0:
        return None
    best = 0  # A side may decline the exchange.
    for move in captures:
        budget[0] -= 1
        if budget[0] < 0:
            return None
        piece = board.piece_at(square)
        captured = VALUES[piece.piece_type] if piece else 100  # en passant
        promoted = VALUES.get(move.promotion, 100) - 100 if move.promotion else 0
        board.push(move)
        try:
            reply = _exchange_gain(board, square, budget, depth - 1)
        finally:
            board.pop()
        if reply is None:
            return None
        best = max(best, captured + promoted - reply)
    return best


def sacrifice_cost(board: chess.Board, move: chess.Move):
    piece = board.piece_at(move.from_square)
    if not piece or piece.piece_type in {chess.PAWN, chess.KING}:
        return 0
    captured = board.piece_at(move.to_square)
    gain = VALUES[captured.piece_type] if captured else (100 if board.is_en_passant(move) else 0)
    after = board.copy(stack=True)
    after.push(move)
    if after.is_game_over():
        return 0
    exchange = _exchange_gain(after, move.to_square, [256])
    return None if exchange is None else max(0, exchange - gain)


def classify_exceptional(board: chess.Board, move: chess.Move, engine) -> dict | None:
    if engine is None or not getattr(engine, "engine", None) or board.legal_moves.count() < 2:
        return None
    evidence = []
    sacrifice = sacrifice_cost(board, move)
    try:
        for settings in PROFILE["passes"]:
            lines = engine.engine.analyse(board, chess.engine.Limit(depth=settings["depth"], time=settings["seconds"]), multipv=2)
            if len(lines) < 2 or any(line.get("depth", 0) < settings["minimum_depth"] or not line.get("pv") or line.get("upperbound") or line.get("lowerbound") for line in lines[:2]):
                return None
            if lines[0]["pv"][0] == lines[1]["pv"][0]:
                return None
            if lines[0]["pv"][0] != move:
                return None
            best, second = [_chance(line["score"].pov(board.turn)) for line in lines[:2]]
            if best < PROFILE["minimum_chance"] or second >= PROFILE["alternative_winning_chance"]:
                return None
            brilliant = sacrifice is not None and sacrifice >= PROFILE["sacrifice_min_cp"]
            great = (best - second) * 100 >= PROFILE["critical_gap_pp"] and second < .70
            if not brilliant and not great:
                return None
            evidence.append({"depth": min(line["depth"] for line in lines[:2]),
                             "best_chance": round(best, 4), "second_chance": round(second, 4),
                             "label": "brilliant" if brilliant else "great"})
        if evidence[0]["label"] != evidence[1]["label"]:
            return None
        return {"label": evidence[-1]["label"], "evidence": {"version": VERSION, "passes": evidence, "sacrifice_cp": sacrifice}}
    except (chess.engine.EngineError, chess.engine.EngineTerminatedError, KeyError, TypeError, ValueError, AttributeError, TimeoutError, OSError):
        return None
