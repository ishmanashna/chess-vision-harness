"""Human-vs-agent play core (no engine, dual principals via agent API + play token)."""

from __future__ import annotations

import chess
import hashlib
import hmac
import random
import secrets
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, Optional

from .agent_surface import agent_safe_board, agent_safe_status
from .game_types import GAME_TYPE_HUMAN_VS_AGENT, is_human_vs_agent_state
from .human_vs_agent_draw import clear_draw_offer, draw_offer_payload
from .human_vs_agent_finish import finish_human_vs_agent_game

if TYPE_CHECKING:
    from .board_controller import BoardController


def mint_play_token() -> tuple[str, str]:
    raw = secrets.token_urlsafe(32)
    return raw, hashlib.sha256(raw.encode()).hexdigest()


def verify_play_token(raw: str, state: Dict[str, Any]) -> bool:
    """Constant-time check of raw play token against state play_token_hash."""
    expected = state.get("play_token_hash")
    if not expected or not raw:
        return False
    digest = hashlib.sha256(raw.encode()).hexdigest()
    return hmac.compare_digest(digest, expected)


def human_color(agent_color_upper: str) -> str:
    return "BLACK" if agent_color_upper == "WHITE" else "WHITE"


def ensure_agent_joined(ctrl: BoardController, game_id: str, state: Dict[str, Any]) -> None:
    if state.get("agent_joined"):
        return
    state["agent_joined"] = True
    ctrl._touch_activity(state)
    ctrl.game_manager.save_state(game_id, state)


class HumanVsAgentPlay:
    """Human-vs-agent mutations delegated from BoardController."""

    def __init__(self, ctrl: BoardController) -> None:
        self.ctrl = ctrl

    @property
    def gm(self):
        return self.ctrl.game_manager

    def new_game(
        self,
        game_id: str,
        model_name: str,
        *,
        human_nickname: Optional[str] = None,
        force: bool = False,
    ) -> Dict[str, Any]:
        try:
            model_id = self.ctrl.registry.resolve(model_name)
        except ValueError as e:
            return {"ok": False, "error": str(e)}

        display_name = self.ctrl.registry.display_name(model_id)
        agent_color_upper = random.choice(["WHITE", "BLACK"])
        human_color_upper = human_color(agent_color_upper)
        play_token_raw, play_token_hash = mint_play_token()
        nickname = (human_nickname or "").strip() or "Human"

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
                human_label = nickname
                agent_label = display_name

                state: Dict[str, Any] = {
                    "game_id": game_id,
                    "game_type": GAME_TYPE_HUMAN_VS_AGENT,
                    "model_name": model_id,
                    "model_display_name": display_name,
                    "agent_color": agent_color_upper,
                    "human_nickname": nickname,
                    "human_color": human_color_upper,
                    "agent_joined": False,
                    "play_token_hash": play_token_hash,
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
                        "White": agent_label if agent_color_upper == "WHITE" else human_label,
                        "Black": human_label if agent_color_upper == "WHITE" else agent_label,
                        "Result": "*",
                        "GameId": game_id,
                        "GameType": GAME_TYPE_HUMAN_VS_AGENT,
                    },
                    "moves": [],
                    "draw_offer": None,
                }
                self.ctrl._touch_activity(state)
                if not self.gm.save_state(game_id, state):
                    return {"ok": False, "error": "Failed to save game state"}

                board_path = self.gm.get_board_path(game_id)
                try:
                    self.ctrl._render_state_board(board, board_path, state)
                except Exception as e:
                    return {"ok": False, "error": f"Failed to render board: {e}"}

                your_turn = self.ctrl._perspective(board, agent_color_upper)["your_turn"]
                return {
                    "ok": True,
                    "game_id": game_id,
                    "game_type": GAME_TYPE_HUMAN_VS_AGENT,
                    "model_name": model_id,
                    "model_display_name": display_name,
                    "agent_color": agent_color_upper,
                    "human_color": human_color_upper,
                    "human_nickname": nickname,
                    "agent_joined": False,
                    "play_token": play_token_raw,
                    "board_path": str(board_path),
                    "your_turn": your_turn,
                }
        except Exception as e:
            from .game_manager import GameBusyError

            if isinstance(e, GameBusyError):
                return {"ok": False, "error": str(e)}
            raise

    def make_move(self, game_id: str, move_str: str) -> Dict[str, Any]:
        from .game_manager import GameBusyError

        try:
            with self.gm.game_lock(game_id):
                state = self.gm.load_state(game_id)
                if not state or not is_human_vs_agent_state(state):
                    return {"ok": False, "error": f"Game {game_id} not found"}
                if state["status"] != "in_progress":
                    return self.ctrl._error(game_id, f"Game is already over: {state['result']}")

                ensure_agent_joined(self.ctrl, game_id, state)
                board = chess.Board(state["board_fen"])
                agent_color = state["agent_color"]
                side = self.ctrl._agent_color(agent_color)
                if board.turn != side:
                    return self.ctrl._error(game_id, "Not your turn")

                move = self.ctrl._parse_move(board, game_id, move_str)
                if isinstance(move, dict):
                    return move

                clear_draw_offer(state)
                self.ctrl._record_move_audit(state, board, move_str, by_color=agent_color)
                try:
                    board.push(move)
                    state["moves"].append(move.uci())
                    state["last_move_uci"] = move.uci()
                    state["board_fen"] = board.fen()
                except Exception as e:
                    return self.ctrl._error(game_id, f"Failed to make move: {e}")

                if board.is_game_over():
                    finish_human_vs_agent_game(
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
                board_path = self.gm.get_board_path(game_id)
                try:
                    self.ctrl._render_state_board(board, board_path, state)
                except Exception as e:
                    return {"ok": False, "error": f"Failed to render board: {e}"}

                return self.ctrl._move_response(game_id, board_path, state, board)
        except GameBusyError as e:
            return {"ok": False, "error": str(e)}

    def status(self, game_id: str) -> Dict[str, Any]:
        state = self.gm.load_state(game_id)
        if not state or not is_human_vs_agent_state(state):
            return {"ok": False, "error": f"Game {game_id} not found"}

        ensure_agent_joined(self.ctrl, game_id, state)
        board = chess.Board(state["board_fen"])
        persp = self.ctrl._perspective(board, state["agent_color"])
        response = agent_safe_status(state, str(self.gm.get_board_path(game_id)), persp)
        response["agent_joined"] = state.get("agent_joined", False)
        response["opponent_display_name"] = state.get("human_nickname") or "Human"
        response.update(draw_offer_payload(state, board, state["agent_color"]))
        return response

    def get_board(self, game_id: str) -> Dict[str, Any]:
        state = self.gm.load_state(game_id)
        if not state or not is_human_vs_agent_state(state):
            return {"ok": False, "error": f"Game {game_id} not found"}

        ensure_agent_joined(self.ctrl, game_id, state)
        board = chess.Board(state["board_fen"])
        board_path = self.gm.get_board_path(game_id)
        if not board_path.exists():
            self.ctrl._render_state_board(board, board_path, state)

        persp = self.ctrl._perspective(board, state["agent_color"])
        return agent_safe_board(state, str(board_path), persp)

    def resign(self, game_id: str, reason: str = "resignation") -> Dict[str, Any]:
        from .game_manager import GameBusyError

        try:
            with self.gm.game_lock(game_id):
                state = self.gm.load_state(game_id)
                if not state or not is_human_vs_agent_state(state):
                    return {"ok": False, "error": f"Game {game_id} not found"}
                if state["status"] != "in_progress":
                    return self.ctrl._error(game_id, f"Game is already over: {state['result']}")

                ensure_agent_joined(self.ctrl, game_id, state)
                clear_draw_offer(state)
                agent_color = state["agent_color"]
                result = "0-1" if agent_color == "WHITE" else "1-0"
                board = chess.Board(state["board_fen"])
                finish_human_vs_agent_game(self.ctrl, self.gm, game_id, state, board, result, reason)
                self.ctrl._auto_save_pgn(game_id, state)

                if not self.gm.save_state(game_id, state):
                    return {"ok": False, "error": "Failed to save game state"}

                return {
                    "ok": True,
                    "game_id": game_id,
                    "board_path": str(self.gm.get_board_path(game_id)),
                    "result": result,
                    **self.ctrl.agent_outcome(agent_color, result),
                }
        except GameBusyError as e:
            return {"ok": False, "error": str(e)}

    def end_no_result(self, game_id: str, reason: str = "inactivity") -> Dict[str, Any]:
        from .game_manager import GameBusyError

        try:
            with self.gm.game_lock(game_id):
                state = self.gm.load_state(game_id)
                if not state or not is_human_vs_agent_state(state):
                    return {"ok": False, "error": f"Game {game_id} not found"}
                if state["status"] != "in_progress":
                    return self.ctrl._error(game_id, f"Game is already over: {state['result']}")

                board = chess.Board(state["board_fen"])
                finish_human_vs_agent_game(self.ctrl, self.gm, game_id, state, board, "*", reason)
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
