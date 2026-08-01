"""
Board controller for managing chess game state and moves.
"""

from __future__ import annotations

import chess
import chess.pgn
import hashlib
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .agent_surface import agent_safe_board, agent_safe_status, quality_fields_from_state
from .avaa import AvAAPlay, is_avaa_state
from .elo import ELOLadder, ENGINE_DISPLAY_NAME, format_stockfish_label
from .engine import EvalEngineAdapter, OpponentEngineManager, configure_opponent_strength
from .game_manager import GameBusyError, GameManager
from .game_types import DEFAULT_GAME_TYPE, GAME_TYPE_AGENT_VS_AGENT, is_human_vs_agent_state
from .human_vs_agent import HumanVsAgentPlay
from .models import ModelRegistry
from .calibration_view import ladder_elo_for_opponent
from .opponents import Opponent, get_catalog
from .render_pillow import ChessBoardRenderer
from .limits import load_limits
from .quality_finish import schedule_game_quality, schedule_provisional_game_quality
from .results import ResultsManager

IDLE_TIMEOUT_SECONDS = 1800  # default; check_idle_games uses load_limits()
MAX_IMAGINE_PLIES = 12


class BoardController:
    """Manages chess game state, moves, and rendering."""

    def __init__(self, game_manager: GameManager, engine=None):
        self.game_manager = game_manager
        self.opponent_mgr = OpponentEngineManager()
        self._eval_engine: Optional[EvalEngineAdapter] = None
        self.renderer = ChessBoardRenderer()
        self.registry = ModelRegistry()
        self.elo = ELOLadder(base_dir=str(game_manager.base_dir), registry=self.registry)
        self.results = ResultsManager(base_dir=str(game_manager.base_dir))
        # `engine` ignored — kept for backward-compatible test fixtures
        self._avaa_play: Optional[AvAAPlay] = None
        self._human_play: Optional[HumanVsAgentPlay] = None

    @property
    def avaa(self) -> AvAAPlay:
        if self._avaa_play is None:
            self._avaa_play = AvAAPlay(self)
        return self._avaa_play

    @property
    def human_play(self) -> HumanVsAgentPlay:
        if self._human_play is None:
            self._human_play = HumanVsAgentPlay(self)
        return self._human_play

    def new_agent_vs_agent_game(
        self,
        game_id: str,
        white_model_id: str,
        black_model_id: str,
        *,
        force: bool = False,
        white_key_fp: Optional[str] = None,
        black_key_fp: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not self.game_manager.validate_game_id(game_id):
            return {"ok": False, "error": f"Invalid game_id: {game_id}"}
        return self.avaa.new_game(
            game_id,
            white_model_id,
            black_model_id,
            force=force,
            white_key_fp=white_key_fp,
            black_key_fp=black_key_fp,
        )

    def new_human_vs_agent_game(
        self,
        game_id: str,
        model_name: str,
        *,
        human_nickname: Optional[str] = None,
        force: bool = False,
    ) -> Dict[str, Any]:
        if not self.game_manager.validate_game_id(game_id):
            return {"ok": False, "error": f"Invalid game_id: {game_id}"}
        return self.human_play.new_game(
            game_id, model_name, human_nickname=human_nickname, force=force
        )

    def _get_eval_engine(self) -> EvalEngineAdapter:
        if self._eval_engine is None:
            self._eval_engine = EvalEngineAdapter()
        return self._eval_engine

    def _board_path(self, game_id: str) -> str:
        return str(self.game_manager.get_board_path(game_id))

    def _agent_color(self, agent_color_upper: str) -> chess.Color:
        return chess.WHITE if agent_color_upper == "WHITE" else chess.BLACK

    def _perspective(self, board: chess.Board, agent_color_upper: str) -> Dict[str, Any]:
        agent = self._agent_color(agent_color_upper)
        game_over = board.is_game_over()
        your_turn = not game_over and board.turn == agent
        return {
            "agent_color": agent_color_upper,
            "your_turn": your_turn,
            "in_check": board.is_check() if your_turn else False,
            "move_number": board.fullmove_number,
            "game_over": game_over,
        }

    def _elo_context(self, state: Dict[str, Any]) -> Dict[str, Any]:
        if is_avaa_state(state):
            white_id = state.get("white_model_id")
            black_id = state.get("black_model_id")
            ctx: Dict[str, Any] = {"game_type": GAME_TYPE_AGENT_VS_AGENT}
            if white_id:
                ctx["white_elo"] = self._avaa_elo_value(state, "white", white_id)
            if black_id:
                ctx["black_elo"] = self._avaa_elo_value(state, "black", black_id)
            return ctx

        model_id = state.get("model_name")
        opponent_elo = state.get("opponent_elo")
        ctx = {
            "opponent_id": state.get("opponent_id"),
            "opponent_elo": opponent_elo,
            "engine_elo": opponent_elo,
            "skill": state.get("skill"),
        }
        if model_id:
            ctx["model_id"] = model_id
            ctx["agent_elo"] = round(self.elo.get_rating(model_id))
        return ctx

    def _avaa_elo_value(self, state: Dict[str, Any], color: str, model_id: str) -> int:
        after = state.get(f"{color}_elo_after")
        if after is not None:
            return round(after)
        before = state.get(f"{color}_elo_before")
        if before is not None:
            return round(before)
        return round(self.elo.get_rating(model_id))

    def _resolve_opponent(
        self,
        model_id: str,
        opponent_or_skill=None,
        *,
        opponent_id: Optional[str] = None,
        skill: Optional[int] = None,
    ) -> Opponent:
        catalog = get_catalog()
        agent_elo = self.elo.get_rating(model_id)
        if opponent_id is not None:
            oid = catalog.resolve_opponent_id(opponent_id=opponent_id, agent_elo=agent_elo)
        elif skill is not None:
            oid = catalog.resolve_opponent_id(skill=skill, agent_elo=agent_elo)
        elif isinstance(opponent_or_skill, int):
            oid = catalog.resolve_opponent_id(skill=opponent_or_skill, agent_elo=agent_elo)
        elif isinstance(opponent_or_skill, str):
            oid = catalog.resolve_opponent_id(opponent_id=opponent_or_skill, agent_elo=agent_elo)
        else:
            oid = catalog.resolve_opponent_id(agent_elo=agent_elo)
        return catalog.get(oid)

    def _opponent_from_state(self, state: Dict[str, Any]) -> Opponent:
        catalog = get_catalog()
        oid = state.get("opponent_id")
        if oid:
            return catalog.get(oid)
        skill = state.get("skill")
        if skill is not None:
            return catalog.get(f"stockfish:{skill}")
        raise KeyError("Game state has no opponent_id or skill")

    def _move_pair(self, uci: Optional[str], san: Optional[str]) -> Optional[Dict[str, str]]:
        if not uci:
            return None
        return {"uci": uci, "san": san or uci}

    def _error(self, game_id: str, error: str, **extra: Any) -> Dict[str, Any]:
        response = {
            "ok": False,
            "error": error,
            "board_path": self._board_path(game_id),
        }
        response.update(extra)
        return response

    def _record_move_audit(
        self,
        state: Dict[str, Any],
        board: chess.Board,
        move_str: str,
        *,
        by_color: Optional[str] = None,
    ) -> None:
        audit = state.setdefault("move_audit", [])
        entry: Dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "move_input": move_str,
            "board_hash_before": hashlib.sha256(board.fen().encode()).hexdigest()[:16],
        }
        if by_color:
            entry["by_color"] = by_color
        audit.append(entry)

    def game_audit(self, game_id: str) -> Dict[str, Any]:
        state = self.game_manager.load_state(game_id)
        if not state:
            return {"ok": False, "error": f"Game {game_id} not found"}
        audit: Dict[str, Any] = {
            "ok": True,
            "game_id": game_id,
            "status": state.get("status"),
            "move_count": len(state.get("moves", [])),
            "move_audit": state.get("move_audit", []),
        }
        if is_avaa_state(state):
            audit["game_type"] = GAME_TYPE_AGENT_VS_AGENT
            audit["white_model_id"] = state.get("white_model_id")
            audit["black_model_id"] = state.get("black_model_id")
        else:
            audit["opponent_id"] = state.get("opponent_id")
            audit["opponent_uci_config"] = state.get("opponent_uci_config")
        return audit

    def _touch_activity(self, state: Dict[str, Any]) -> None:
        state["last_activity"] = datetime.now(timezone.utc).isoformat()

    def _idle_seconds(self, game_id: str, state: Dict[str, Any]) -> float:
        ts = state.get("last_activity")
        if ts:
            try:
                last = datetime.fromisoformat(ts)
                if last.tzinfo is None:
                    last = last.replace(tzinfo=timezone.utc)
                return (datetime.now(timezone.utc) - last).total_seconds()
            except ValueError:
                pass
        state_path = self.game_manager.get_state_path(game_id)
        if state_path.exists():
            return max(0.0, time.time() - state_path.stat().st_mtime)
        return 0.0

    def check_idle_games(self) -> List[str]:
        """End in-progress games idle longer than configured timeout with no result."""
        idle_limit = load_limits().idle_timeout_sec
        ended: List[str] = []
        if not self.game_manager.games_dir.exists():
            return ended
        for game_dir in self.game_manager.games_dir.iterdir():
            if not game_dir.is_dir():
                continue
            game_id = game_dir.name
            state = self.game_manager.load_state(game_id)
            if not state or state.get("status") != "in_progress":
                continue
            if is_avaa_state(state):
                from .avaa import awaiting_joins

                if awaiting_joins(state):
                    continue
            if self._idle_seconds(game_id, state) >= idle_limit:
                result = self.end_no_result(game_id, reason="inactivity")
                if result.get("ok"):
                    ended.append(game_id)
        return ended

    @staticmethod
    def game_revision(state: Dict[str, Any]) -> str:
        return f"{state.get('status')}:{len(state.get('moves', []))}:{state.get('last_move_uci') or ''}"

    @staticmethod
    def highlight_moves(state: Dict[str, Any]) -> list:
        """Last one or two plies for spectator board highlights (oldest first)."""
        moves: list = []
        for uci in (state.get("moves") or [])[-2:]:
            try:
                moves.append(chess.Move.from_uci(uci))
            except ValueError:
                continue
        if not moves and state.get("last_move_uci"):
            try:
                moves.append(chess.Move.from_uci(state["last_move_uci"]))
            except ValueError:
                pass
        return moves

    def _render_state_board(self, board: chess.Board, board_path, state: Dict[str, Any]) -> None:
        self.renderer.render_board(
            board,
            board_path,
            last_moves=self.highlight_moves(state),
            bottom_color="white",
            check_square=board.king(board.turn) if board.is_check() else None,
        )

    @staticmethod
    def avaa_display_names(state: Dict[str, Any]) -> tuple[str, str]:
        white = state.get("white_display_name") or state.get("white_model_id") or "White"
        black = state.get("black_display_name") or state.get("black_model_id") or "Black"
        return white, black

    @staticmethod
    def side_labels(state: Dict[str, Any]) -> Dict[str, str]:
        if is_avaa_state(state):
            white, black = BoardController.avaa_display_names(state)
            return {"white": white, "black": black}
        if is_human_vs_agent_state(state):
            from .spectator_human import human_display_names

            white, black = human_display_names(state)
            return {"white": white, "black": black}
        model = state.get("model_display_name") or state.get("model_name") or "Agent"
        engine = BoardController.engine_display_label(state)
        if state.get("agent_color") == "WHITE":
            return {"black": engine, "white": model}
        return {"black": model, "white": engine}

    @staticmethod
    def engine_display_label(state: Dict[str, Any]) -> str:
        if state.get("opponent_label"):
            return state["opponent_label"]
        headers = state.get("pgn_headers") or {}
        engine_name = headers.get("EngineName", ENGINE_DISPLAY_NAME)
        skill = state.get("skill")
        if skill is not None:
            return format_stockfish_label(skill, engine_name=engine_name)
        return engine_name

    @staticmethod
    def agent_outcome(agent_color: str, result: Optional[str]) -> Dict[str, str]:
        """Agent-centric outcome (Win/Loss/Draw/No result), separate from PGN white-first notation."""
        if not result:
            return {"outcome": "live", "label": "in progress", "pgn": "", "pgn_note": ""}
        if result == "*":
            return {
                "outcome": "none",
                "label": "No result",
                "pgn": "*",
                "pgn_note": "No result",
            }
        if result == "1/2-1/2":
            return {"outcome": "draw", "label": "Draw", "pgn": result, "pgn_note": "Draw"}
        agent_won = (agent_color == "WHITE" and result == "1-0") or (
            agent_color == "BLACK" and result == "0-1"
        )
        if agent_won:
            return {
                "outcome": "win",
                "label": "Win",
                "pgn": result,
                "pgn_note": f"Agent won ({result})",
            }
        if result == "1-0":
            note = "White won (1-0)"
        elif result == "0-1":
            note = "Black won (0-1)"
        else:
            note = result
        return {"outcome": "loss", "label": "Loss", "pgn": result, "pgn_note": note}

    def _move_response(
        self, game_id: str, board_path, state: Dict[str, Any], board: chess.Board
    ) -> Dict[str, Any]:
        response: Dict[str, Any] = {
            "ok": True,
            "game_id": game_id,
            "board_path": str(board_path),
        }
        if state.get("result"):
            response["result"] = state["result"]
            response.update(self.agent_outcome(state["agent_color"], state["result"]))
        else:
            response["your_turn"] = self._perspective(board, state["agent_color"])["your_turn"]
        response.update(quality_fields_from_state(state))
        return response

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
        if not self.game_manager.validate_game_id(game_id):
            return {"ok": False, "error": f"Invalid game_id: {game_id}"}
        if agent_color.lower() not in ("white", "black"):
            return {"ok": False, "error": "agent_color must be 'white' or 'black'"}

        try:
            model_id = self.registry.resolve(model_name)
        except ValueError as e:
            return {"ok": False, "error": str(e)}

        if fen and os.getenv("CHESS_HARNESS_DEBUG", "").lower() not in ("1", "true", "yes"):
            return {
                "ok": False,
                "error": "Custom FEN is operator-only (set CHESS_HARNESS_DEBUG=1)",
            }

        try:
            opponent = self._resolve_opponent(
                model_id, opponent_or_skill, opponent_id=opponent_id, skill=skill
            )
        except ValueError as e:
            return {"ok": False, "error": str(e)}

        display_name = self.registry.display_name(model_id)

        try:
            with self.game_manager.game_lock(game_id):
                existing = self.game_manager.load_state(game_id)
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

                try:
                    board = chess.Board(fen) if fen else chess.Board()
                except ValueError as e:
                    return {"ok": False, "error": f"Invalid FEN: {e}"}

                start_fen = board.fen()

                try:
                    if opponent.type == "random":
                        uci_config = {"type": "random"}
                    else:
                        adapter = self.opponent_mgr.get_adapter(opponent)
                        uci_config = configure_opponent_strength(adapter.engine, opponent)
                except Exception as e:
                    return {"ok": False, "error": f"Failed to load opponent: {e}"}

                agent_color_upper = agent_color.upper()
                agent_label = display_name
                opponent_ladder_elo = ladder_elo_for_opponent(opponent)
                engine_label = f"{opponent.display_name} ({opponent_ladder_elo})"

                state: Dict[str, Any] = {
                    "game_id": game_id,
                    "game_type": game_type,
                    "agent_color": agent_color_upper,
                    "opponent_id": opponent.id,
                    "opponent_elo": opponent_ladder_elo,
                    "opponent_label": engine_label,
                    "skill": opponent.skill_level
                    if opponent.type in ("stockfish", "stockfish_harness", "inverse_sf")
                    else None,
                    "model_name": model_id,
                    "model_display_name": display_name,
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
                        "White": agent_label if agent_color_upper == "WHITE" else engine_label,
                        "Black": engine_label if agent_color_upper == "WHITE" else agent_label,
                        "Result": "*",
                        "GameId": game_id,
                        "AgentColor": agent_color_upper,
                        "OpponentId": opponent.id,
                        "OpponentElo": str(opponent_ladder_elo),
                        "EngineName": opponent.display_name,
                    },
                    "moves": [],
                    "engine_first_move": None,
                    "opponent_uci_config": uci_config,
                }
                if opponent.skill_level is not None:
                    state["pgn_headers"]["EngineSkill"] = str(opponent.skill_level)
                if fen:
                    state["pgn_headers"]["FEN"] = start_fen
                    state["pgn_headers"]["SetUp"] = "1"

                engine_first_move = None
                if agent_color_upper == "BLACK" and board.turn == chess.WHITE:
                    try:
                        result = self.opponent_mgr.play(opponent, board, time_limit=0.1)
                        engine_first_move = result.move
                        board.push(engine_first_move)
                        state["board_fen"] = board.fen()
                        state["last_move_uci"] = engine_first_move.uci()
                        state["moves"].append(engine_first_move.uci())
                        state["engine_first_move"] = engine_first_move.uci()
                    except Exception as e:
                        return {"ok": False, "error": f"Opponent failed to make first move: {e}"}

                self._touch_activity(state)

                if not self.game_manager.save_state(game_id, state):
                    return {"ok": False, "error": "Failed to save game state"}

                board_path = self.game_manager.get_board_path(game_id)
                try:
                    self._render_state_board(board, board_path, state)
                except Exception as e:
                    return {"ok": False, "error": f"Failed to render board: {e}"}

                response: Dict[str, Any] = {
                    "ok": True,
                    "game_id": game_id,
                    "board_path": str(board_path),
                    "your_turn": self._perspective(board, agent_color_upper)["your_turn"],
                    "agent_color": agent_color_upper,
                    "model_name": model_id,
                    "model_display_name": display_name,
                    "opponent_id": opponent.id,
                    "opponent_label": engine_label,
                    "opponent_elo": opponent_ladder_elo,
                    "agent_elo": round(self.elo.get_rating(model_id)),
                }
                return response
        except GameBusyError as e:
            return {"ok": False, "error": str(e)}

    def make_agent_move(
        self, game_id: str, move_str: str, *, caller_color: Optional[str] = None
    ) -> Dict[str, Any]:
        state = self.game_manager.load_state(game_id)
        if state is None or (
            state
            and not is_avaa_state(state)
            and not is_human_vs_agent_state(state)
            and "agent_color" not in state
        ):
            # Retry once — concurrent save can make a read fail briefly on Windows.
            state = self.game_manager.load_state(game_id)
        if state and is_avaa_state(state):
            if not caller_color:
                return {"ok": False, "error": "caller_color required for agent-vs-agent games"}
            return self.avaa.make_move(game_id, move_str, caller_color)
        if state and is_human_vs_agent_state(state):
            return self.human_play.make_move(game_id, move_str)
        # Do not fall through to the engine path for missing/partial/AvA state
        # (AvA has no agent_color and would KeyError).
        if not state or "agent_color" not in state:
            return {"ok": False, "error": f"Game {game_id} not found"}
        try:
            with self.game_manager.game_lock(game_id):
                state = self.game_manager.load_state(game_id)
                if not state:
                    return {"ok": False, "error": f"Game {game_id} not found"}
                if is_avaa_state(state) or "agent_color" not in state:
                    return {"ok": False, "error": f"Game {game_id} not found"}
                if state["status"] != "in_progress":
                    return self._error(game_id, f"Game is already over: {state['result']}")

                board = chess.Board(state["board_fen"])
                agent_color = chess.WHITE if state["agent_color"] == "WHITE" else chess.BLACK
                if board.turn != agent_color:
                    return self._error(game_id, "Not your turn")

                move = self._parse_move(board, game_id, move_str)
                if isinstance(move, dict):
                    return move

                self._record_move_audit(state, board, move_str)

                try:
                    san = board.san(move)
                    board.push(move)
                    state["moves"].append(move.uci())
                    state["last_move_uci"] = move.uci()
                    state["board_fen"] = board.fen()
                except Exception as e:
                    return self._error(game_id, f"Failed to make move: {e}")

                if board.is_game_over():
                    self._finish_game(game_id, state, board)

                engine_move = None
                engine_san = None
                if state["status"] == "in_progress" and board.turn != agent_color:
                    try:
                        opponent = self._opponent_from_state(state)
                        result = self.opponent_mgr.play(opponent, board, time_limit=0.1)
                        engine_move = result.move
                        engine_san = board.san(engine_move)
                        board.push(engine_move)
                        state["moves"].append(engine_move.uci())
                        state["last_move_uci"] = engine_move.uci()
                        state["board_fen"] = board.fen()
                        if board.is_game_over():
                            self._finish_game(game_id, state, board)
                    except Exception as e:
                        return self._error(game_id, f"Opponent failed to move: {e}")

                self._touch_activity(state)
                if state["status"] == "in_progress":
                    self._try_snapshot_eval(state, board)
                if not self.game_manager.save_state(game_id, state):
                    return {"ok": False, "error": "Failed to save game state"}

                self._auto_save_pgn(game_id, state)
                self._schedule_quality_if_scored(game_id, state)

                board_path = self.game_manager.get_board_path(game_id)
                try:
                    self._render_state_board(board, board_path, state)
                except Exception as e:
                    return {"ok": False, "error": f"Failed to render board: {e}"}

                return self._move_response(game_id, board_path, state, board)
        except GameBusyError as e:
            return {"ok": False, "error": str(e)}

    def _parse_move(
        self, board: chess.Board, game_id: str, move_str: str
    ) -> chess.Move | Dict[str, Any]:
        try:
            move = chess.Move.from_uci(move_str)
            if move not in board.legal_moves:
                return self._error(game_id, f"Illegal move: {move_str}")
            return move
        except ValueError:
            pass

        try:
            return board.parse_san(move_str)
        except chess.InvalidMoveError as e:
            return self._error(game_id, f"Invalid move format: {e}")
        except chess.AmbiguousMoveError:
            return self._error(
                game_id,
                f"Ambiguous move '{move_str}'; use full UCI or disambiguated SAN",
            )
        except chess.IllegalMoveError as e:
            return self._error(game_id, f"Illegal move: {e}")

    def _try_snapshot_eval(self, state: Dict[str, Any], board: chess.Board) -> None:
        if is_human_vs_agent_state(state):
            return
        try:
            score = self._get_eval_engine().evaluate(board, depth=8)
            if score is not None:
                state["last_eval_cp"] = score
        except Exception:
            pass

    def _finish_game(self, game_id: str, state: Dict[str, Any], board: chess.Board) -> None:
        self._try_snapshot_eval(state, board)
        state["status"] = "finished"
        state["result"] = board.result()
        state["end_reason"] = self._get_game_over_reason(board)
        state["pgn_headers"]["Result"] = state["result"]
        opponent_elo = state.get("opponent_elo")
        if opponent_elo is None:
            opponent_elo = ladder_elo_for_opponent(self._opponent_from_state(state))
        self.results.append_result(
            {
                "ts": datetime.now().isoformat(),
                "game_id": game_id,
                "opponent_id": state.get("opponent_id"),
                "opponent_elo": opponent_elo,
                "skill": state.get("skill"),
                "agent_color": state["agent_color"],
                "result": state["result"],
                "reason": self._get_game_over_reason(board),
                "plies": len(state["moves"]),
                "pgn_path": str(self.game_manager.get_pgn_path(game_id)),
                "model_name": state.get("model_name"),
            }
        )
        delta = self.elo.record_game(
            state.get("model_name"),
            opponent_elo,
            state["result"],
            state["agent_color"],
            opponent_id=state.get("opponent_id"),
        )
        if delta:
            state.update(delta)
            from .snapshot_leaderboard import request_leaderboard_snapshot_refresh

            request_leaderboard_snapshot_refresh()

    def apply_elo_delta(self, state: Dict[str, Any]) -> Optional[Dict[str, int]]:
        """Return ELO change for a game, backfilling from results if needed."""
        if state.get("elo_before") is not None:
            return {
                "elo_before": state["elo_before"],
                "elo_after": state["elo_after"],
                "elo_delta": state["elo_delta"],
            }
        game_id = state.get("game_id")
        if not game_id:
            return None
        delta = self.elo.elo_change_for_game(game_id)
        if delta:
            state.update(delta)
        return delta

    @staticmethod
    def format_end_reason(reason: str, state: Dict[str, Any]) -> str:
        model = state.get("model_display_name") or state.get("model_name") or "Agent"
        if reason == "resignation":
            return f"{model} resigned"
        if reason == "inactivity":
            return "No result (idle timeout)"
        return reason

    def resolve_end_reason(self, state: Dict[str, Any], game_id: str) -> Optional[str]:
        reason = state.get("end_reason")
        if not reason:
            entry = self.results.get_result_for_game(game_id)
            reason = entry.get("reason") if entry else None
        if not reason:
            return None
        return self.format_end_reason(reason, state)

    @staticmethod
    def format_elo_change(delta: Optional[Dict[str, int]], agent_name: str = "Agent") -> str:
        if not delta:
            return ""
        change = delta["elo_delta"]
        sign = "+" if change > 0 else ""
        return f"{agent_name} {delta['elo_before']} → {delta['elo_after']} ({sign}{change})"

    @staticmethod
    def format_avaa_elo_change(state: Dict[str, Any]) -> str:
        white, black = BoardController.avaa_display_names(state)
        parts: List[str] = []
        for color, name in (("white", white), ("black", black)):
            before = state.get(f"{color}_elo_before")
            after = state.get(f"{color}_elo_after")
            if before is None or after is None:
                continue
            delta = after - before
            sign = "+" if delta > 0 else ""
            parts.append(f"{name} {before} → {after} ({sign}{delta})")
        return " · ".join(parts)

    def get_board(self, game_id: str, *, caller_color: Optional[str] = None) -> Dict[str, Any]:
        state = self.game_manager.load_state(game_id)
        if not state:
            return {"ok": False, "error": f"Game {game_id} not found"}
        if is_avaa_state(state):
            if not caller_color:
                return {"ok": False, "error": "caller_color required for agent-vs-agent games"}
            return self.avaa.get_board(game_id, caller_color)
        if is_human_vs_agent_state(state):
            return self.human_play.get_board(game_id)

        board = chess.Board(state["board_fen"])
        board_path = self.game_manager.get_board_path(game_id)

        if not board_path.exists():
            try:
                self._render_state_board(board, board_path, state)
            except Exception as e:
                return {"ok": False, "error": f"Failed to render board: {e}"}

        persp = self._perspective(board, state["agent_color"])
        return agent_safe_board(state, str(board_path), persp)

    def imagine_board(self, game_id: str, moves: List[str]) -> Dict[str, Any]:
        """Apply a hypothetical line from the current FEN and render a PNG.

        Read-only: does not touch activity, joined flags, board.png, moves, or audit.
        """
        state = self.game_manager.load_state(game_id)
        if not state:
            return {"ok": False, "error": f"Game {game_id} not found"}
        if not isinstance(moves, list):
            return {"ok": False, "error": "moves must be a list of UCI/SAN strings"}
        if len(moves) > MAX_IMAGINE_PLIES:
            return {
                "ok": False,
                "error": f"Too many moves (max {MAX_IMAGINE_PLIES} plies)",
            }

        board = chess.Board(state["board_fen"])
        applied: List[chess.Move] = []
        for index, raw in enumerate(moves):
            move_str = str(raw or "").strip()
            if not move_str:
                return {
                    "ok": False,
                    "error": f"Empty move at index {index}",
                    "index": index,
                }
            parsed = self._parse_move(board, game_id, move_str)
            if isinstance(parsed, dict):
                err = parsed.get("error", f"Illegal move: {move_str}")
                return {"ok": False, "error": err, "index": index}
            board.push(parsed)
            applied.append(parsed)

        try:
            png = self.renderer.render_board_bytes(
                board,
                last_moves=applied[-2:] if applied else None,
                bottom_color="white",
                check_square=board.king(board.turn) if board.is_check() else None,
            )
        except Exception as e:
            return {"ok": False, "error": f"Failed to render imagined board: {e}"}

        return {
            "ok": True,
            "game_id": game_id,
            "png_bytes": png,
            "applied_count": len(applied),
            "hypothetical": True,
        }

    def refresh_board_image(self, game_id: str) -> bool:
        """Re-render board PNG (e.g. after renderer defaults change)."""
        state = self.game_manager.load_state(game_id)
        if not state:
            return False
        board = chess.Board(state["board_fen"])
        try:
            if is_avaa_state(state):
                from .avaa_render import render_avaa_boards

                render_avaa_boards(self, self.game_manager, board, game_id, state)
            else:
                board_path = self.game_manager.get_board_path(game_id)
                self._render_state_board(board, board_path, state)
            return True
        except Exception:
            return False

    def end_no_result(self, game_id: str, reason: str = "inactivity") -> Dict[str, Any]:
        """Finish a game with PGN result '*' — no win/loss/draw, no ELO change."""
        state = self.game_manager.load_state(game_id)
        if state and is_avaa_state(state):
            return self.avaa.end_no_result(game_id, reason=reason)
        if state and is_human_vs_agent_state(state):
            return self.human_play.end_no_result(game_id, reason=reason)
        try:
            with self.game_manager.game_lock(game_id):
                state = self.game_manager.load_state(game_id)
                if not state:
                    return {"ok": False, "error": f"Game {game_id} not found"}
                if state["status"] != "in_progress":
                    return self._error(game_id, f"Game is already over: {state['result']}")

                agent_color = state["agent_color"]
                result = "*"
                state["status"] = "finished"
                state["result"] = result
                state["end_reason"] = reason
                state["pgn_headers"]["Result"] = result

                board = chess.Board(state["board_fen"])
                self._try_snapshot_eval(state, board)
                self._auto_save_pgn(game_id, state)

                opp_elo = state.get("opponent_elo")
                if opp_elo is None:
                    opp_elo = ladder_elo_for_opponent(self._opponent_from_state(state))
                self.results.append_result(
                    {
                        "ts": datetime.now().isoformat(),
                        "game_id": game_id,
                        "opponent_id": state.get("opponent_id"),
                        "opponent_elo": opp_elo,
                        "skill": state.get("skill"),
                        "agent_color": agent_color,
                        "result": result,
                        "reason": reason,
                        "plies": len(state["moves"]),
                        "pgn_path": str(self.game_manager.get_pgn_path(game_id)),
                        "model_name": state.get("model_name"),
                    }
                )

                if not self.game_manager.save_state(game_id, state):
                    return {"ok": False, "error": "Failed to save game state"}

                return {
                    "ok": True,
                    "game_id": game_id,
                    "board_path": self._board_path(game_id),
                    "result": result,
                    **self.agent_outcome(agent_color, result),
                }
        except GameBusyError as e:
            return {"ok": False, "error": str(e)}

    def resign(
        self, game_id: str, reason: str = "resignation", *, caller_color: Optional[str] = None
    ) -> Dict[str, Any]:
        state = self.game_manager.load_state(game_id)
        if state and is_avaa_state(state):
            if not caller_color:
                return {"ok": False, "error": "caller_color required for agent-vs-agent games"}
            return self.avaa.resign(game_id, caller_color, reason=reason)
        if state and is_human_vs_agent_state(state):
            return self.human_play.resign(game_id, reason=reason)
        try:
            with self.game_manager.game_lock(game_id):
                state = self.game_manager.load_state(game_id)
                if not state:
                    return {"ok": False, "error": f"Game {game_id} not found"}
                if state["status"] != "in_progress":
                    return self._error(game_id, f"Game is already over: {state['result']}")

                agent_color = state["agent_color"]
                result = "0-1" if agent_color == "WHITE" else "1-0"
                state["status"] = "finished"
                state["result"] = result
                state["end_reason"] = reason
                state["pgn_headers"]["Result"] = result

                board = chess.Board(state["board_fen"])
                self._try_snapshot_eval(state, board)

                self._auto_save_pgn(game_id, state)
                opp_elo = state.get("opponent_elo")
                if opp_elo is None:
                    opp_elo = ladder_elo_for_opponent(self._opponent_from_state(state))
                self.results.append_result(
                    {
                        "ts": datetime.now().isoformat(),
                        "game_id": game_id,
                        "opponent_id": state.get("opponent_id"),
                        "opponent_elo": opp_elo,
                        "skill": state.get("skill"),
                        "agent_color": agent_color,
                        "result": result,
                        "reason": reason,
                        "plies": len(state["moves"]),
                        "pgn_path": str(self.game_manager.get_pgn_path(game_id)),
                        "model_name": state.get("model_name"),
                    }
                )
                delta = self.elo.record_game(
                    state.get("model_name"),
                    opp_elo,
                    result,
                    agent_color,
                    opponent_id=state.get("opponent_id"),
                )
                if delta:
                    state.update(delta)

                if not self.game_manager.save_state(game_id, state):
                    return {"ok": False, "error": "Failed to save game state"}
                # Quality reads state from disk — must save finished status first.
                self._schedule_quality_if_scored(game_id, state)

                return {
                    "ok": True,
                    "game_id": game_id,
                    "board_path": self._board_path(game_id),
                    "result": result,
                    **self.agent_outcome(agent_color, result),
                }
        except GameBusyError as e:
            return {"ok": False, "error": str(e)}

    def export_pgn(self, game_id: str, *, allow_in_progress: bool = False) -> Dict[str, Any]:
        state = self.game_manager.load_state(game_id)
        if not state:
            return {"ok": False, "error": f"Game {game_id} not found"}

        if state.get("status") == "in_progress" and not allow_in_progress:
            return {
                "ok": False,
                "error": "PGN available after the game ends. Use board image to play.",
            }

        pgn_path = self.game_manager.get_pgn_path(game_id)
        if pgn_path.exists():
            pgn_text = self._clean_pgn(pgn_path.read_text(encoding="utf-8"))
            return {
                "ok": True,
                "pgn": pgn_text,
                "pgn_path": str(pgn_path),
            }

        game = self._build_pgn_game(state)
        pgn_text = self._clean_pgn(str(game))
        try:
            pgn_path.write_text(pgn_text, encoding="utf-8")
        except OSError as e:
            return {"ok": False, "error": f"Failed to write PGN: {e}"}

        return {
            "ok": True,
            "pgn": pgn_text,
            "pgn_path": str(pgn_path),
        }

    def status(self, game_id: str, *, caller_color: Optional[str] = None) -> Dict[str, Any]:
        state = self.game_manager.load_state(game_id)
        if not state:
            return {"ok": False, "error": f"Game {game_id} not found"}
        if is_avaa_state(state):
            if not caller_color:
                return {"ok": False, "error": "caller_color required for agent-vs-agent games"}
            return self.avaa.status(game_id, caller_color)
        if is_human_vs_agent_state(state):
            return self.human_play.status(game_id)

        board = chess.Board(state["board_fen"])
        persp = self._perspective(board, state["agent_color"])
        response = agent_safe_status(state, self._board_path(game_id), persp)
        response.update(self._elo_context(state))
        return response

    def _clean_pgn(self, pgn_text: str) -> str:
        lines = [
            line
            for line in pgn_text.splitlines()
            if not line.strip().startswith("[Annotator ")
        ]
        return "\n".join(lines).strip() + "\n"

    def _matchup_line(self, state: Dict[str, Any], agent_elo: Optional[int] = None) -> str:
        """Standard notation: WHITE player first, BLACK player second."""
        if is_avaa_state(state):
            white, black = BoardController.avaa_display_names(state)
            elo = self._elo_context(state)
            white_elo = elo.get("white_elo")
            black_elo = elo.get("black_elo")
            white_part = f"{white} ({white_elo} ELO)" if white_elo is not None else white
            black_part = f"{black} ({black_elo} ELO)" if black_elo is not None else black
            return f"WHITE {white_part} vs BLACK {black_part}"

        if is_human_vs_agent_state(state):
            from .spectator_human import human_display_names

            white, black = human_display_names(state)
            elo = self._elo_context(state)
            agent_elo_val = agent_elo if agent_elo is not None else elo.get("agent_elo")
            if state.get("agent_color") == "WHITE":
                white_part = (
                    f"{white} ({agent_elo_val} ELO)" if agent_elo_val is not None else white
                )
                black_part = black
            else:
                white_part = white
                black_part = (
                    f"{black} ({agent_elo_val} ELO)" if agent_elo_val is not None else black
                )
            return f"WHITE {white_part} vs BLACK {black_part}"

        elo = self._elo_context(state)
        model = state.get("model_display_name") or state.get("model_name") or "Agent"
        if agent_elo is None:
            agent_elo = elo.get("agent_elo")
        engine_elo = elo.get("engine_elo") or state.get("opponent_elo")
        engine_label = BoardController.engine_display_label(state)

        agent_part = model
        if agent_elo is not None:
            agent_part += f" ({agent_elo} ELO)"

        if state.get("opponent_label"):
            engine_part = engine_label
        else:
            engine_part = engine_label
            if engine_elo is not None:
                engine_part += f" ({engine_elo} ELO)"

        if state["agent_color"] == "WHITE":
            white_part, black_part = agent_part, engine_part
        else:
            white_part, black_part = engine_part, agent_part

        return f"WHITE {white_part} vs BLACK {black_part}"

    def format_spectator_summary(self, state: Dict[str, Any]) -> str:
        board = chess.Board(state["board_fen"])
        if is_avaa_state(state):
            matchup = self._matchup_line(state)
            if state["status"] != "in_progress":
                return f"{matchup} — {state.get('result', 'done')}"
            if board.is_game_over():
                return f"{matchup} — {board.result()}"
            white, black = BoardController.avaa_display_names(state)
            mover = white if board.turn == chess.WHITE else black
            turn = f"{mover} to move"
            if board.is_check():
                turn += " (check)"
            return f"{matchup} — {turn}"

        if is_human_vs_agent_state(state):
            from .spectator_human import human_display_names

            matchup = self._matchup_line(state)
            if state["status"] != "in_progress":
                return f"{matchup} — {state.get('result', 'done')}"
            if board.is_game_over():
                return f"{matchup} — {board.result()}"
            white, black = human_display_names(state)
            mover = white if board.turn == chess.WHITE else black
            turn = f"{mover} to move"
            if board.is_check():
                turn += " (check)"
            return f"{matchup} — {turn}"

        persp = self._perspective(board, state["agent_color"])
        delta = None
        agent_elo = None
        if state.get("status") != "in_progress":
            if state.get("elo_before") is not None:
                delta = {
                    "elo_before": state["elo_before"],
                    "elo_after": state["elo_after"],
                    "elo_delta": state["elo_delta"],
                }
            elif state.get("game_id"):
                delta = self.elo.elo_change_for_game(state["game_id"])
            if delta:
                agent_elo = delta["elo_after"]
        matchup = self._matchup_line(state, agent_elo=agent_elo)
        if state["status"] != "in_progress":
            return f"{matchup} — {state.get('result', 'done')}"
        if persp["game_over"]:
            return f"{matchup} — {board.result()}"
        turn = "White to move" if board.turn == chess.WHITE else "Black to move"
        if board.is_check():
            turn += " (check)"
        return f"{matchup} — {turn}"

    def _build_pgn_game(self, state: Dict[str, Any]) -> chess.pgn.Game:
        game = chess.pgn.Game()
        for key, value in state["pgn_headers"].items():
            game.headers[key] = value
        board = chess.Board(state.get("start_fen", chess.STARTING_FEN))
        node = game
        for move_uci in state["moves"]:
            move = chess.Move.from_uci(move_uci)
            node = node.add_variation(move)
            board.push(move)
        return game

    def _get_game_over_reason(self, board: chess.Board) -> str:
        if board.is_checkmate():
            winner = "White" if board.turn == chess.BLACK else "Black"
            return f"checkmate ({winner} wins)"
        if board.is_stalemate():
            return "stalemate"
        if board.is_insufficient_material():
            return "insufficient material"
        if board.is_fifty_moves():
            return "fifty-move rule"
        if board.is_repetition():
            return "repetition"
        return "game over"

    def _auto_save_pgn(self, game_id: str, state: Dict[str, Any]) -> None:
        try:
            game = self._build_pgn_game(state)
            self.game_manager.get_pgn_path(game_id).write_text(
                self._clean_pgn(str(game)), encoding="utf-8"
            )
        except Exception:
            return
        if state.get("status") == "in_progress" and state.get("moves"):
            schedule_provisional_game_quality(
                game_id,
                move_count=len(state["moves"]),
                base_dir=str(self.game_manager.base_dir),
            )

    def _schedule_quality_if_scored(self, game_id: str, state: Dict[str, Any]) -> None:
        if state.get("status") == "finished" and state.get("result") not in (None, "*"):
            from .finished_games_db import record_scored_finish

            # Dual-write permanent record (outside .chess_harness/). Live delete
            # must not remove this row.
            record_scored_finish(
                game_id,
                state,
                game_manager=self.game_manager,
                results_manager=self.results,
            )
            schedule_game_quality(
                game_id,
                base_dir=str(self.game_manager.base_dir),
                force=bool(state.get("quality_provisional")),
            )
