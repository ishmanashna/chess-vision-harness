"""Pure python-chess game loop for engine matches."""

from __future__ import annotations

import chess

from .engine_player import EnginePlayer
from .play_config import MatchConfig


def play_game(match: MatchConfig) -> str:
    start_fen = chess.STARTING_FEN if match.start_fen == "startpos" else match.start_fen
    board = chess.Board(start_fen)
    white = EnginePlayer(match.white_id, match.white)
    black = EnginePlayer(match.black_id, match.black)
    try:
        plies = 0
        while not board.is_game_over() and plies < match.max_plies:
            player = white if board.turn == chess.WHITE else black
            move = player.play(board)
            board.push(move)
            plies += 1
        if board.is_game_over():
            return board.result(claim_draw=True) or "1/2-1/2"
        return "1/2-1/2"
    finally:
        white.release()
        black.release()
