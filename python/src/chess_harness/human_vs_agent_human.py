"""Human-principal moves and position for human-vs-agent games."""

from __future__ import annotations

import chess
from typing import Any, Dict, TYPE_CHECKING

from .game_types import is_human_vs_agent_state
from .human_vs_agent_finish import finish_human_vs_agent_game

if TYPE_CHECKING:
    from .human_vs_agent import HumanVsAgentPlay


def human_position(play: HumanVsAgentPlay, game_id: str) -> Dict[str, Any]:
    state = play.gm.load_state(game_id)
    if not state or not is_human_vs_agent_state(state):
        return {"ok": False, "error": f"Game {game_id} not found"}

    board = chess.Board(state["board_fen"])
    human_col = state["human_color"]
    human_side = play.ctrl._agent_color(human_col)
    in_progress = state["status"] == "in_progress"
    game_over = not in_progress or board.is_game_over()
    your_turn = in_progress and not game_over and board.turn == human_side

    payload: Dict[str, Any] = {
        "ok": True,
        "game_id": game_id,
        "fen": board.fen(),
        "your_turn": your_turn,
        "agent_joined": bool(state.get("agent_joined")),
        "game_over": game_over,
        "result": state.get("result"),
        "side_to_move": "white" if board.turn == chess.WHITE else "black",
        "human_color": human_col,
        "agent_display_name": state.get("model_display_name") or state.get("model_name"),
        "human_nickname": state.get("human_nickname"),
        "move_count": len(state.get("moves", [])),
    }
    if game_over:
        reason = state.get("end_reason")
        if reason:
            payload["end_reason"] = reason
        label = _human_end_reason_label(play, state, game_id)
        if label:
            payload["end_reason_label"] = label
    if in_progress and not game_over:
        payload["legal_moves_uci"] = [m.uci() for m in board.legal_moves]
    return payload


def _human_end_reason_label(play: HumanVsAgentPlay, state: Dict[str, Any], game_id: str) -> str | None:
    reason = state.get("end_reason")
    if reason == "inactivity":
        return "No result (idle timeout)"
    if reason == "resignation":
        human_col = state.get("human_color")
        result = state.get("result")
        human_resigned = (human_col == "WHITE" and result == "0-1") or (
            human_col == "BLACK" and result == "1-0"
        )
        if human_resigned:
            human = state.get("human_nickname") or "Human"
            return f"{human} resigned"
    return play.ctrl.resolve_end_reason(state, game_id)


def make_human_move(play: HumanVsAgentPlay, game_id: str, move_str: str) -> Dict[str, Any]:
    from .game_manager import GameBusyError

    try:
        with play.gm.game_lock(game_id):
            state = play.gm.load_state(game_id)
            if not state or not is_human_vs_agent_state(state):
                return {"ok": False, "error": f"Game {game_id} not found"}
            if state["status"] != "in_progress":
                return play.ctrl._error(game_id, f"Game is already over: {state['result']}")

            board = chess.Board(state["board_fen"])
            human_col = state["human_color"]
            human_side = play.ctrl._agent_color(human_col)
            if board.turn != human_side:
                return play.ctrl._error(game_id, "Not your turn")

            move = play.ctrl._parse_move(board, game_id, move_str)
            if isinstance(move, dict):
                return move

            play.ctrl._record_move_audit(state, board, move_str, by_color=human_col)
            try:
                board.push(move)
                state["moves"].append(move.uci())
                state["last_move_uci"] = move.uci()
                state["board_fen"] = board.fen()
            except Exception as e:
                return play.ctrl._error(game_id, f"Failed to make move: {e}")

            if board.is_game_over():
                finish_human_vs_agent_game(
                    play.ctrl,
                    play.gm,
                    game_id,
                    state,
                    board,
                    board.result(),
                    play.ctrl._get_game_over_reason(board),
                )

            play.ctrl._touch_activity(state)
            if state["status"] == "in_progress":
                play.ctrl._try_snapshot_eval(state, board)
            if not play.gm.save_state(game_id, state):
                return {"ok": False, "error": "Failed to save game state"}

            play.ctrl._auto_save_pgn(game_id, state)
            board_path = play.gm.get_board_path(game_id)
            try:
                play.ctrl._render_state_board(board, board_path, state)
            except Exception as e:
                return {"ok": False, "error": f"Failed to render board: {e}"}

            return _human_move_response(play, game_id, state, board)
    except GameBusyError as e:
        return {"ok": False, "error": str(e)}


def human_resign(play: HumanVsAgentPlay, game_id: str, reason: str = "resignation") -> Dict[str, Any]:
    from .game_manager import GameBusyError

    try:
        with play.gm.game_lock(game_id):
            state = play.gm.load_state(game_id)
            if not state or not is_human_vs_agent_state(state):
                return {"ok": False, "error": f"Game {game_id} not found"}
            if state["status"] != "in_progress":
                return play.ctrl._error(game_id, f"Game is already over: {state['result']}")

            human_col = state["human_color"]
            result = "0-1" if human_col == "WHITE" else "1-0"
            board = chess.Board(state["board_fen"])
            finish_human_vs_agent_game(play.ctrl, play.gm, game_id, state, board, result, reason)
            play.ctrl._auto_save_pgn(game_id, state)

            if not play.gm.save_state(game_id, state):
                return {"ok": False, "error": "Failed to save game state"}

            return {
                "ok": True,
                "game_id": game_id,
                "result": result,
                "game_over": True,
            }
    except GameBusyError as e:
        return {"ok": False, "error": str(e)}


def _human_move_response(
    play: HumanVsAgentPlay, game_id: str, state: Dict[str, Any], board: chess.Board
) -> Dict[str, Any]:
    human_col = state["human_color"]
    human_side = play.ctrl._agent_color(human_col)
    in_progress = state["status"] == "in_progress"
    game_over = not in_progress or board.is_game_over()

    response: Dict[str, Any] = {
        "ok": True,
        "game_id": game_id,
        "fen": board.fen(),
        "move_count": len(state.get("moves", [])),
        "game_over": game_over,
    }
    if state.get("result"):
        response["result"] = state["result"]
        response["your_turn"] = False
    else:
        response["your_turn"] = in_progress and board.turn == human_side
    return response
