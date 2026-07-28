"""Agent-vs-agent play core (no engine, dual principals)."""

from __future__ import annotations

import chess
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, Optional

from .agent_surface import agent_safe_board, agent_safe_status
from .avaa_finish import finish_avaa_game
from .avaa_render import avaa_move_response, render_avaa_boards
from .game_types import GAME_TYPE_AGENT_VS_AGENT

if TYPE_CHECKING:
    from .board_controller import BoardController


def is_avaa_state(state: Dict[str, Any]) -> bool:
    return state.get("game_type") == GAME_TYPE_AGENT_VS_AGENT


def participant_color(state: Dict[str, Any], model_id: str) -> Optional[str]:
    if model_id == state.get("white_model_id"):
        return "WHITE"
    if model_id == state.get("black_model_id"):
        return "BLACK"
    return None


class AvAAPlay:
    """AvaA mutations delegated from BoardController."""

    def __init__(self, ctrl: BoardController) -> None:
        self.ctrl = ctrl

    @property
    def gm(self):
        return self.ctrl.game_manager

    def new_game(
        self,
        game_id: str,
        white_model_id: str,
        black_model_id: str,
        *,
        force: bool = False,
    ) -> Dict[str, Any]:
        if white_model_id == black_model_id:
            return {"ok": False, "error": "white_model_id and black_model_id must differ"}
        registry = self.ctrl.registry
        try:
            white_id = registry.resolve(white_model_id)
            black_id = registry.resolve(black_model_id)
        except ValueError as e:
            return {"ok": False, "error": str(e)}

        white_name = registry.display_name(white_id)
        black_name = registry.display_name(black_id)

        try:
            with self.gm.game_lock(game_id):
                existing = self.gm.load_state(game_id)
                if existing and not force:
                    if existing.get("status") == "in_progress":
                        return {
                            "ok": False,
                            "error": f"Game {game_id} already in progress; use force=true or pick a new id",
                        }
                    return {
                        "ok": False,
                        "error": f"Game {game_id} already exists (finished); use force=true or pick a new id",
                    }

                board = chess.Board()
                start_fen = board.fen()
                state: Dict[str, Any] = {
                    "game_id": game_id,
                    "game_type": GAME_TYPE_AGENT_VS_AGENT,
                    "white_model_id": white_id,
                    "black_model_id": black_id,
                    "white_display_name": white_name,
                    "black_display_name": black_name,
                    "start_fen": start_fen,
                    "board_fen": start_fen,
                    "last_move_uci": None,
                    "status": "in_progress",
                    "result": None,
                    "pgn_headers": {
                        "Event": "Chess Vision Harness Game",
                        "Site": f"Local ({game_id})",
                        "Date": datetime.now().strftime("%Y.%m.%d"),
                        "Round": "1",
                        "White": white_name,
                        "Black": black_name,
                        "Result": "*",
                        "GameId": game_id,
                        "GameType": GAME_TYPE_AGENT_VS_AGENT,
                    },
                    "moves": [],
                }
                self.ctrl._touch_activity(state)
                if not self.gm.save_state(game_id, state):
                    return {"ok": False, "error": "Failed to save game state"}

                render_avaa_boards(self.ctrl, self.gm, board, game_id, state)
                return {
                    "ok": True,
                    "game_id": game_id,
                    "game_type": GAME_TYPE_AGENT_VS_AGENT,
                    "white_model_id": white_id,
                    "black_model_id": black_id,
                    "white_display_name": white_name,
                    "black_display_name": black_name,
                    "board_path": str(self.gm.get_board_path(game_id)),
                    "your_turn": True,
                    "agent_color": "WHITE",
                }
        except Exception as e:
            from .game_manager import GameBusyError

            if isinstance(e, GameBusyError):
                return {"ok": False, "error": str(e)}
            raise

    def make_move(self, game_id: str, move_str: str, caller_color: str) -> Dict[str, Any]:
        from .game_manager import GameBusyError

        try:
            with self.gm.game_lock(game_id):
                state = self.gm.load_state(game_id)
                if not state or not is_avaa_state(state):
                    return {"ok": False, "error": f"Game {game_id} not found"}
                if state["status"] != "in_progress":
                    return self.ctrl._error(game_id, f"Game is already over: {state['result']}")

                board = chess.Board(state["board_fen"])
                side = self.ctrl._agent_color(caller_color)
                if board.turn != side:
                    return self.ctrl._error(game_id, "Not your turn")

                move = self.ctrl._parse_move(board, game_id, move_str)
                if isinstance(move, dict):
                    return move

                self.ctrl._record_move_audit(state, board, move_str, by_color=caller_color)
                try:
                    board.push(move)
                    state["moves"].append(move.uci())
                    state["last_move_uci"] = move.uci()
                    state["board_fen"] = board.fen()
                except Exception as e:
                    return self.ctrl._error(game_id, f"Failed to make move: {e}")

                if board.is_game_over():
                    finish_avaa_game(
                        self.ctrl,
                        self.gm,
                        game_id,
                        state,
                        board,
                        board.result(),
                        self.ctrl._get_game_over_reason(board),
                    )

                self.ctrl._touch_activity(state)
                if state["status"] == "in_progress":
                    self.ctrl._try_snapshot_eval(state, board)
                if not self.gm.save_state(game_id, state):
                    return {"ok": False, "error": "Failed to save game state"}

                self.ctrl._auto_save_pgn(game_id, state)
                render_avaa_boards(self.ctrl, self.gm, board, game_id, state)
                return avaa_move_response(self.gm, self.ctrl, game_id, state, board, caller_color)
        except GameBusyError as e:
            return {"ok": False, "error": str(e)}

    def status(self, game_id: str, caller_color: str) -> Dict[str, Any]:
        state = self.gm.load_state(game_id)
        if not state or not is_avaa_state(state):
            return {"ok": False, "error": f"Game {game_id} not found"}

        board = chess.Board(state["board_fen"])
        board_path = str(self.gm.get_role_board_path(game_id, caller_color))
        persp = self.ctrl._perspective(board, caller_color)
        response = agent_safe_status(state, board_path, persp)
        response["agent_color"] = caller_color
        response["opponent_display_name"] = self._opponent_name(state, caller_color)
        return response

    def get_board(self, game_id: str, caller_color: str) -> Dict[str, Any]:
        state = self.gm.load_state(game_id)
        if not state or not is_avaa_state(state):
            return {"ok": False, "error": f"Game {game_id} not found"}

        board = chess.Board(state["board_fen"])
        board_path = self.gm.get_role_board_path(game_id, caller_color)
        if not board_path.exists():
            render_avaa_boards(self.ctrl, self.gm, board, game_id, state)

        persp = self.ctrl._perspective(board, caller_color)
        return agent_safe_board(state, str(board_path), persp, caller_color=caller_color)

    def resign(self, game_id: str, caller_color: str, reason: str = "resignation") -> Dict[str, Any]:
        from .game_manager import GameBusyError

        try:
            with self.gm.game_lock(game_id):
                state = self.gm.load_state(game_id)
                if not state or not is_avaa_state(state):
                    return {"ok": False, "error": f"Game {game_id} not found"}
                if state["status"] != "in_progress":
                    return self.ctrl._error(game_id, f"Game is already over: {state['result']}")

                result = "0-1" if caller_color == "WHITE" else "1-0"
                board = chess.Board(state["board_fen"])
                finish_avaa_game(self.ctrl, self.gm, game_id, state, board, result, reason)
                self.ctrl._auto_save_pgn(game_id, state)

                if not self.gm.save_state(game_id, state):
                    return {"ok": False, "error": "Failed to save game state"}

                return {
                    "ok": True,
                    "game_id": game_id,
                    "board_path": str(self.gm.get_role_board_path(game_id, caller_color)),
                    "result": result,
                    **self.ctrl.agent_outcome(caller_color, result),
                }
        except GameBusyError as e:
            return {"ok": False, "error": str(e)}

    def _opponent_name(self, state: Dict[str, Any], caller_color: str) -> str:
        if caller_color == "WHITE":
            return state.get("black_display_name") or state.get("black_model_id") or "Black"
        return state.get("white_display_name") or state.get("white_model_id") or "White"

    def end_no_result(self, game_id: str, reason: str = "inactivity") -> Dict[str, Any]:
        from .game_manager import GameBusyError

        try:
            with self.gm.game_lock(game_id):
                state = self.gm.load_state(game_id)
                if not state or not is_avaa_state(state):
                    return {"ok": False, "error": f"Game {game_id} not found"}
                if state["status"] != "in_progress":
                    return self.ctrl._error(game_id, f"Game is already over: {state['result']}")

                board = chess.Board(state["board_fen"])
                finish_avaa_game(
                    self.ctrl, self.gm, game_id, state, board, "*", reason, record_elo=False
                )
                self.ctrl._auto_save_pgn(game_id, state)

                if not self.gm.save_state(game_id, state):
                    return {"ok": False, "error": "Failed to save game state"}

                return {
                    "ok": True,
                    "game_id": game_id,
                    "board_path": str(self.gm.get_board_path(game_id)),
                    "result": "*",
                }
        except GameBusyError as e:
            return {"ok": False, "error": str(e)}
