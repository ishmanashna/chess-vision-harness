"""Finish and results row for human-vs-agent games (unranked)."""

from __future__ import annotations

import chess
from datetime import datetime
from typing import Any, Dict, TYPE_CHECKING

from .game_types import GAME_TYPE_HUMAN_VS_AGENT

if TYPE_CHECKING:
    from .board_controller import BoardController
    from .game_manager import GameManager


def finish_human_vs_agent_game(
    ctrl: BoardController,
    gm: GameManager,
    game_id: str,
    state: Dict[str, Any],
    board: chess.Board,
    result: str,
    reason: str,
) -> None:
    ctrl._try_snapshot_eval(state, board)
    state["status"] = "finished"
    state["result"] = result
    state["end_reason"] = reason
    state["pgn_headers"]["Result"] = result

    plies = len(state["moves"])
    pgn_path = str(gm.get_pgn_path(game_id))
    ctrl.results.append_result(
        {
            "ts": datetime.now().isoformat(),
            "game_id": game_id,
            "game_type": GAME_TYPE_HUMAN_VS_AGENT,
            "model_name": state.get("model_name"),
            "observation": ctrl.result_observation(state),
            "agent_color": state.get("agent_color"),
            "human_nickname": state.get("human_nickname"),
            "result": result,
            "reason": reason,
            "plies": plies,
            "pgn_path": pgn_path,
        }
    )
