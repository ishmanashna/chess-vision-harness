"""Draw offers for human-vs-agent games (unranked agreement draws)."""

from __future__ import annotations

import chess
from typing import Any, Dict, TYPE_CHECKING

from .game_types import is_human_vs_agent_state
from .human_vs_agent_finish import finish_human_vs_agent_game

if TYPE_CHECKING:
    from .human_vs_agent import HumanVsAgentPlay


def clear_draw_offer(state: Dict[str, Any]) -> None:
    state["draw_offer"] = None


def draw_offer_payload(state: Dict[str, Any], board: chess.Board, color: str) -> Dict[str, Any]:
    """UI/status flags for one principal (WHITE or BLACK)."""
    offer = state.get("draw_offer")
    in_progress = state.get("status") == "in_progress"
    offered_by = offer.get("offered_by") if offer else None
    pending = bool(offer)
    return {
        "draw_offer_pending": pending,
        "draw_offered_by": offered_by,
        "you_offered_draw": pending and offered_by == color,
        "can_offer_draw": in_progress and not pending,
        "can_respond_draw": in_progress and pending and offered_by != color,
    }


def offer_draw(play: HumanVsAgentPlay, game_id: str, by_color: str) -> Dict[str, Any]:
    from .game_manager import GameBusyError

    try:
        with play.gm.game_lock(game_id):
            state = play.gm.load_state(game_id)
            if not state or not is_human_vs_agent_state(state):
                return {"ok": False, "error": f"Game {game_id} not found"}
            if state["status"] != "in_progress":
                return play.ctrl._error(game_id, f"Game is already over: {state['result']}")

            board = chess.Board(state["board_fen"])
            if state.get("draw_offer"):
                return play.ctrl._error(game_id, "A draw offer is already pending")

            state["draw_offer"] = {
                "offered_by": by_color,
                "at_ply": len(state.get("moves", [])),
            }
            play.ctrl._touch_activity(state)
            if not play.gm.save_state(game_id, state):
                return {"ok": False, "error": "Failed to save game state"}

            return {"ok": True, "game_id": game_id, **draw_offer_payload(state, board, by_color)}
    except GameBusyError as e:
        return {"ok": False, "error": str(e)}


def accept_draw(play: HumanVsAgentPlay, game_id: str, by_color: str) -> Dict[str, Any]:
    from .game_manager import GameBusyError

    try:
        with play.gm.game_lock(game_id):
            state = play.gm.load_state(game_id)
            if not state or not is_human_vs_agent_state(state):
                return {"ok": False, "error": f"Game {game_id} not found"}
            if state["status"] != "in_progress":
                return play.ctrl._error(game_id, f"Game is already over: {state['result']}")

            offer = state.get("draw_offer")
            if not offer:
                return play.ctrl._error(game_id, "No draw offer to accept")
            if offer.get("offered_by") == by_color:
                return play.ctrl._error(game_id, "Cannot accept your own draw offer")

            board = chess.Board(state["board_fen"])
            clear_draw_offer(state)
            finish_human_vs_agent_game(
                play.ctrl, play.gm, game_id, state, board, "1/2-1/2", "agreement"
            )
            play.ctrl._auto_save_pgn(game_id, state)
            if not play.gm.save_state(game_id, state):
                return {"ok": False, "error": "Failed to save game state"}

            return {
                "ok": True,
                "game_id": game_id,
                "result": "1/2-1/2",
                "game_over": True,
                "end_reason": "agreement",
            }
    except GameBusyError as e:
        return {"ok": False, "error": str(e)}


def decline_draw(play: HumanVsAgentPlay, game_id: str, by_color: str) -> Dict[str, Any]:
    from .game_manager import GameBusyError

    try:
        with play.gm.game_lock(game_id):
            state = play.gm.load_state(game_id)
            if not state or not is_human_vs_agent_state(state):
                return {"ok": False, "error": f"Game {game_id} not found"}
            if state["status"] != "in_progress":
                return play.ctrl._error(game_id, f"Game is already over: {state['result']}")

            offer = state.get("draw_offer")
            if not offer:
                return play.ctrl._error(game_id, "No draw offer to decline")
            if offer.get("offered_by") == by_color:
                return play.ctrl._error(game_id, "Cannot decline your own draw offer")

            board = chess.Board(state["board_fen"])
            clear_draw_offer(state)
            play.ctrl._touch_activity(state)
            if not play.gm.save_state(game_id, state):
                return {"ok": False, "error": "Failed to save game state"}

            return {"ok": True, "game_id": game_id, **draw_offer_payload(state, board, by_color)}
    except GameBusyError as e:
        return {"ok": False, "error": str(e)}
