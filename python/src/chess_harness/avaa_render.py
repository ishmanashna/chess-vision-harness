"""Board rendering and move responses for agent-vs-agent games."""

from __future__ import annotations

import chess
from typing import TYPE_CHECKING, Any, Dict

from .agent_surface import quality_fields_from_state

if TYPE_CHECKING:
    from .board_controller import BoardController
    from .game_manager import GameManager


def render_avaa_boards(
    ctrl: BoardController,
    gm: GameManager,
    board: chess.Board,
    game_id: str,
    state: Dict[str, Any],
) -> None:
    highlights = ctrl.highlight_moves(state)
    renderer = ctrl.renderer
    for color in ("white", "black"):
        path = gm.get_role_board_path(game_id, color)
        renderer.render_board(
            board,
            path,
            last_moves=highlights,
            agent_color=color,
            check_square=board.king(board.turn) if board.is_check() else None,
        )
    spectator_path = gm.get_board_path(game_id)
    renderer.render_board(
        board,
        spectator_path,
        last_moves=highlights,
        agent_color="white",
        check_square=board.king(board.turn) if board.is_check() else None,
    )


def avaa_move_response(
    gm: GameManager,
    ctrl: BoardController,
    game_id: str,
    state: Dict[str, Any],
    board: chess.Board,
    caller_color: str,
) -> Dict[str, Any]:
    board_path = gm.get_role_board_path(game_id, caller_color)
    response: Dict[str, Any] = {
        "ok": True,
        "game_id": game_id,
        "board_path": str(board_path),
        "agent_color": caller_color,
    }
    if state.get("result"):
        response["result"] = state["result"]
        response.update(ctrl.agent_outcome(caller_color, state["result"]))
    else:
        response["your_turn"] = ctrl._perspective(board, caller_color)["your_turn"]
    response.update(quality_fields_from_state(state))
    return response
