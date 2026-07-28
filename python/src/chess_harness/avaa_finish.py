"""Dual Elo finish and results rows for agent-vs-agent games."""

from __future__ import annotations

import chess
from datetime import datetime
from typing import Any, Dict, TYPE_CHECKING

from .game_types import GAME_TYPE_AGENT_VS_AGENT

if TYPE_CHECKING:
    from .board_controller import BoardController
    from .game_manager import GameManager


def finish_avaa_game(
    ctrl: BoardController,
    gm: GameManager,
    game_id: str,
    state: Dict[str, Any],
    board: chess.Board,
    result: str,
    reason: str,
    *,
    record_elo: bool = True,
) -> None:
    ctrl._try_snapshot_eval(state, board)
    state["status"] = "finished"
    state["result"] = result
    state["end_reason"] = reason
    state["pgn_headers"]["Result"] = result

    white_id = state["white_model_id"]
    black_id = state["black_model_id"]
    registry = ctrl.registry
    white_pre = round(registry.get_elo(white_id))
    black_pre = round(registry.get_elo(black_id))
    plies = len(state["moves"])
    pgn_path = str(gm.get_pgn_path(game_id))
    ts = datetime.now().isoformat()

    ctrl.results.append_result(
        {
            "ts": ts,
            "game_id": game_id,
            "game_type": GAME_TYPE_AGENT_VS_AGENT,
            "model_name": white_id,
            "agent_color": "WHITE",
            "opponent_model": black_id,
            "opponent_elo": black_pre,
            "result": result,
            "reason": reason,
            "plies": plies,
            "pgn_path": pgn_path,
        }
    )
    ctrl.results.append_result(
        {
            "ts": ts,
            "game_id": game_id,
            "game_type": GAME_TYPE_AGENT_VS_AGENT,
            "model_name": black_id,
            "agent_color": "BLACK",
            "opponent_model": white_id,
            "opponent_elo": white_pre,
            "result": result,
            "reason": reason,
            "plies": plies,
            "pgn_path": pgn_path,
        }
    )

    if record_elo and result != "*":
        white_delta = ctrl.elo.record_game(white_id, black_pre, result, "WHITE")
        black_delta = ctrl.elo.record_game(black_id, white_pre, result, "BLACK")
        if white_delta:
            state["white_elo_before"] = white_delta["elo_before"]
            state["white_elo_after"] = white_delta["elo_after"]
        if black_delta:
            state["black_elo_before"] = black_delta["elo_before"]
            state["black_elo_after"] = black_delta["elo_after"]
