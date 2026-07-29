"""
Thin facade over BoardController — single mutation path for adapters.

Engine lifecycle: opponent and eval engines are released after new_game and
make_move. resign prunes idle games but does not acquire engines. Read-only
calls (status, board, pgn, audit) skip prune and release.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from .board_controller import BoardController
from .game_types import DEFAULT_GAME_TYPE, GAME_TYPE_AGENT_VS_AGENT, GAME_TYPE_HUMAN_VS_AGENT
from .game_manager import GameManager

__all__ = [
    "DEFAULT_GAME_TYPE",
    "GAME_TYPE_AGENT_VS_AGENT",
    "GAME_TYPE_HUMAN_VS_AGENT",
    "GameService",
]


class GameService:
    """Delegates game rules to BoardController; owns idle prune + engine release."""

    def __init__(
        self,
        game_manager: Optional[GameManager] = None,
        controller: Optional[BoardController] = None,
    ):
        self.game_manager = game_manager or GameManager()
        self.controller = controller or BoardController(self.game_manager)

    def _prune_idle(self) -> None:
        self.controller.check_idle_games()

    def _release_engines(self) -> None:
        self.controller.opponent_mgr.release()
        if self.controller._eval_engine is not None:
            self.controller._eval_engine.quit()
            self.controller._eval_engine = None

    def prune_idle_games(self) -> list[str]:
        return self.controller.check_idle_games()

    def new_game(
        self,
        game_id: str,
        agent_color: str,
        opponent_or_skill=None,
        fen: Optional[str] = None,
        model_name: Optional[str] = None,
        force: bool = False,
        *,
        opponent_id: Optional[str] = None,
        skill: Optional[int] = None,
        game_type: str = DEFAULT_GAME_TYPE,
    ) -> Dict[str, Any]:
        self._prune_idle()
        try:
            return self.controller.new_game(
                game_id,
                agent_color,
                opponent_or_skill,
                fen=fen,
                model_name=model_name,
                force=force,
                opponent_id=opponent_id,
                skill=skill,
                game_type=game_type,
            )
        finally:
            self._release_engines()

    def new_agent_vs_agent_game(
        self,
        game_id: str,
        white_model_id: str,
        black_model_id: str,
        *,
        force: bool = False,
    ) -> Dict[str, Any]:
        self._prune_idle()
        return self.controller.new_agent_vs_agent_game(
            game_id,
            white_model_id,
            black_model_id,
            force=force,
        )

    def new_human_vs_agent_game(
        self,
        game_id: str,
        model_name: str,
        *,
        human_nickname: Optional[str] = None,
        force: bool = False,
    ) -> Dict[str, Any]:
        self._prune_idle()
        return self.controller.new_human_vs_agent_game(
            game_id,
            model_name,
            human_nickname=human_nickname,
            force=force,
        )

    def make_move(
        self, game_id: str, move_str: str, *, caller_color: Optional[str] = None
    ) -> Dict[str, Any]:
        self._prune_idle()
        try:
            return self.controller.make_agent_move(
                game_id, move_str, caller_color=caller_color
            )
        finally:
            self._release_engines()

    def resign(
        self,
        game_id: str,
        reason: str = "resignation",
        *,
        caller_color: Optional[str] = None,
    ) -> Dict[str, Any]:
        self._prune_idle()
        return self.controller.resign(game_id, reason=reason, caller_color=caller_color)

    def status(self, game_id: str, *, caller_color: Optional[str] = None) -> Dict[str, Any]:
        return self.controller.status(game_id, caller_color=caller_color)

    def get_board(self, game_id: str, *, caller_color: Optional[str] = None) -> Dict[str, Any]:
        return self.controller.get_board(game_id, caller_color=caller_color)

    def get_board_bytes(self, game_id: str, *, caller_color: Optional[str] = None) -> bytes:
        result = self.get_board(game_id, caller_color=caller_color)
        if not result.get("ok"):
            raise ValueError(result.get("error", "board unavailable"))
        return Path(result["board_path"]).read_bytes()

    def export_pgn(self, game_id: str, *, allow_in_progress: bool = False) -> Dict[str, Any]:
        return self.controller.export_pgn(game_id, allow_in_progress=allow_in_progress)

    def game_audit(self, game_id: str) -> Dict[str, Any]:
        return self.controller.game_audit(game_id)

    def human_position(self, game_id: str) -> Dict[str, Any]:
        from .human_vs_agent_human import human_position

        self._prune_idle()
        return human_position(self.controller.human_play, game_id)

    def make_human_move(self, game_id: str, move_str: str) -> Dict[str, Any]:
        from .human_vs_agent_human import make_human_move

        self._prune_idle()
        return make_human_move(self.controller.human_play, game_id, move_str)

    def human_resign(self, game_id: str, reason: str = "resignation") -> Dict[str, Any]:
        from .human_vs_agent_human import human_resign

        self._prune_idle()
        return human_resign(self.controller.human_play, game_id, reason=reason)
