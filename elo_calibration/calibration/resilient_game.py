"""Calibration games with move retries and skipped games on persistent timeout."""

from __future__ import annotations

from typing import List, Optional, Tuple

import chess
import chess.engine

from .engine_player import EnginePlayer, release_all_engines
from .play_config import MatchConfig

CALIBRATION_UCI_TIMEOUT = 45.0
MAX_MOVE_RETRIES = 3
MOVE_ERRORS = (TimeoutError, chess.engine.EngineError, chess.engine.EngineTerminatedError)


def play_game_resilient(
    match: MatchConfig,
    *,
    uci_timeout: float = CALIBRATION_UCI_TIMEOUT,
    max_move_retries: int = MAX_MOVE_RETRIES,
) -> Tuple[Optional[str], List[str]]:
    """
    Play a calibration game. Returns (result, uci_moves); result is None if abandoned.
    On move timeout, retries with a fresh engine subprocess; never records a forfeit.
    """
    start_fen = chess.STARTING_FEN if match.start_fen == "startpos" else match.start_fen
    board = chess.Board(start_fen)
    white = EnginePlayer(match.white_id, match.white, uci_timeout=uci_timeout)
    black = EnginePlayer(match.black_id, match.black, uci_timeout=uci_timeout)
    uci_moves: List[str] = []
    try:
        plies = 0
        while not board.is_game_over() and plies < match.max_plies:
            if board.turn == chess.WHITE:
                move, white = _play_move_resilient(white, board, uci_timeout, max_move_retries)
            else:
                move, black = _play_move_resilient(black, board, uci_timeout, max_move_retries)
            if move is None:
                return None, uci_moves
            uci_moves.append(move.uci())
            board.push(move)
            plies += 1
        if board.is_game_over():
            return board.result(claim_draw=True) or "1/2-1/2", uci_moves
        return "1/2-1/2", uci_moves
    finally:
        release_all_engines()


def _play_move_resilient(
    player: EnginePlayer,
    board: chess.Board,
    uci_timeout: float,
    max_move_retries: int,
) -> Tuple[Optional[chess.Move], EnginePlayer]:
    """Reuse one engine subprocess per side; only respawn after communication errors."""
    current = player
    for attempt in range(max_move_retries):
        try:
            return current.play(board), current
        except MOVE_ERRORS:
            release_all_engines()
            if attempt + 1 >= max_move_retries:
                return None, current
            current = EnginePlayer(current.opponent_id, current.config, uci_timeout=uci_timeout)
    return None, current
