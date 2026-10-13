"""Add display context for a resignation that follows an unclaimed draw.

This records a claimable draw as context for the final move. It does not
rewrite the engine's position score, move label, game result, or quality
metrics: the assessment remains available as the engine's theoretical view.
"""
from __future__ import annotations

import chess


_DECISIVE_RESULTS = {"1-0": chess.WHITE, "0-1": chess.BLACK}


def apply_terminal_context(state: dict, artifact: dict) -> dict:
    """Attach a draw-claim note to a qualifying final move, if one exists.

    The marker is only for finished resignation games where the final mover
    won, the saved final post-move score is exactly zero, and replaying the
    game's move history shows that the opponent could claim a threefold
    repetition or fifty-move draw. Engine scores, labels, and game metrics are
    deliberately left intact.
    """
    if not isinstance(artifact, dict):
        return artifact

    plies = artifact.get("plies")
    if not isinstance(plies, list):
        return artifact

    # This field is derived solely from current state and move history. Clear
    # any previous projection before recomputing so repeated calls are safe.
    for row in plies:
        if isinstance(row, dict):
            row.pop("terminal_context", None)

    if not isinstance(state, dict):
        return artifact
    if state.get("status") != "finished" or str(state.get("end_reason", "")).lower() != "resignation":
        return artifact
    winner = _DECISIVE_RESULTS.get(state.get("result"))
    moves = state.get("moves")
    if winner is None or not isinstance(moves, list) or not moves or len(plies) != len(moves):
        return artifact

    last_row = plies[-1]
    if not isinstance(last_row, dict) or last_row.get("uci") != moves[-1]:
        return artifact
    after = last_row.get("after")
    if not isinstance(after, dict) or after.get("cp") != 0 or after.get("mate") is not None:
        return artifact

    try:
        board = chess.Board(state.get("start_fen") or chess.STARTING_FEN)
        last_mover = None
        for index, uci in enumerate(moves):
            move = chess.Move.from_uci(uci)
            if move not in board.legal_moves:
                return artifact
            if index == len(moves) - 1:
                last_mover = board.turn
                color = "white" if last_mover else "black"
                if last_row.get("color") != color:
                    return artifact
            board.push(move)

        # Automatic endings aren't "unclaimed" draw context. The final
        # position must be ongoing, with a draw claim available to the side to
        # move after the winner's last move.
        if board.is_game_over() or last_mover != winner:
            return artifact
        if board.can_claim_threefold_repetition():
            reason = "threefold repetition"
        elif board.can_claim_fifty_moves():
            reason = "fifty-move rule"
        else:
            return artifact
    except (ValueError, TypeError, IndexError, AssertionError):
        return artifact

    last_row["terminal_context"] = {
        "kind": "unclaimed_draw",
        "reason": reason,
        "game_result": state["result"],
        "display_symbol": "=",
    }
    return artifact
