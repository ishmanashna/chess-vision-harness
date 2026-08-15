"""
Spectator web interface for Chess Vision Harness.
"""

import asyncio
import json
import re
import threading
import time
from typing import Any, Dict, Optional

from contextlib import asynccontextmanager

import chess
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from .agent_surface import (
    agent_safe_spectator_state,
    debug_state_enabled,
    quality_fields_from_state,
)
from .api_mount import mount_api_v1
from .avaa import is_avaa_state
from .board_controller import BoardController
from .elo import ELOLadder
from .game_types import (
    DEFAULT_GAME_TYPE,
    GAME_TYPE_AGENT_VS_AGENT,
    GAME_TYPE_HUMAN_VS_AGENT,
    is_human_vs_agent_state,
)
from .spectator_human import (
    human_active_card,
    human_list_fields,
    human_state_extra,
    show_eval_for_state,
)
from .ladder_display import (
    FAVICON_LINKS,
    PUBLIC_SITE_HEADER,
    THEME_INIT_SCRIPT,
    render_calibration_html,
)
from .calibration_auth import require_calibration_auth
from .contact_api import register_contact_routes
from .play_page import register_play_routes
from .calibration_view import get_calibration_status, get_calibration_status_live, rebuild_merged_ratings_file
from .public_site_shell import watch_shell_response
from .puzzle_observer import (
    _agent_name,
    observer_state,
    public_attempt_row,
    render_observer_board_png,
    replay_payload,
)
from .puzzle_attempt import PuzzleAttemptStore
from .board_text import format_board_text
from .identify_attempt import IdentifyAttemptStore
from .identify_observer import (
    _agent_name as identify_agent_name,
    observer_state as identify_observer_state,
    public_attempt_row as identify_public_row,
    render_answer_overlay_png,
    render_identify_board_png,
    replay_payload as identify_replay_payload,
)
from .continuous_calibration import (
    assess_fleet_parallel,
    assess_parallel_start,
    assess_start_all,
    can_continuously_calibrate,
    resolve_calibration_manager,
)
from .calibration_supervisor import (
    calibration_worker_error,
    calibration_worker_healthy,
    ensure_calibration_worker,
    shutdown_calibration_worker,
)
from .calibration_worker_ipc import calibration_in_process
from .api_limits import get_limit_enforcer
from .engine import EvalEngineAdapter
from .game_manager import GameManager
from .game_service import GameService
from .paths import project_root, resolve_base_dir
from .serve_utils import remove_spectator_meta
from .serve_workers import run_blocking, run_eval, shutdown_workers
from .snapshot_leaderboard import (
    export_public_snapshots,
    load_live_identify_leaderboard,
    load_live_leaderboard,
    load_live_puzzle_leaderboard,
)

LEADERBOARD_SNAPSHOT_INTERVAL_SEC = 300

_project_root = project_root()
_base = str(resolve_base_dir())
game_manager = GameManager(base_dir=_base)


def _ladder() -> ELOLadder:
    return ELOLadder(base_dir=_base)


_engine: Optional[EvalEngineAdapter] = None
_controller: Optional[BoardController] = None
_game_service: Optional[GameService] = None
_eval_cache: Dict[str, tuple[float, Optional[int]]] = {}
_finished_eval_cache: Dict[str, int] = {}
_EVAL_TTL = 2.0

NAV = (
    '<a class="back" href="/spectator/">&larr; Spectator</a> &nbsp;|&nbsp; '
    '<a class="back" href="/calibration">Calibration</a> &nbsp;|&nbsp; '
    '<a class="back" href="/leaderboard">ELO Ladder</a> &nbsp;|&nbsp; '
    '<button type="button" class="theme-toggle theme-toggle-inline" data-theme-toggle>Dark mode</button>'
)


def _game_summary(state: Dict[str, Any]) -> str:
    return _get_controller().format_spectator_summary(state)


def _game_elo_change(state: Dict[str, Any], game_id: str) -> Optional[Dict[str, int]]:
    if is_avaa_state(state) or is_human_vs_agent_state(state):
        return None
    return _get_controller().apply_elo_delta({**state, "game_id": game_id})


def _list_elo_delta(state: Dict[str, Any], game_id: str) -> Optional[Dict[str, int]]:
    """Cheap list projection: state fields only — no results.jsonl replay."""
    if state.get("status") == "in_progress":
        return None
    if is_avaa_state(state) or is_human_vs_agent_state(state):
        return None
    before = state.get("elo_before")
    if before is None:
        return None
    after = state.get("elo_after")
    if after is None:
        return None
    return {
        "elo_before": before,
        "elo_after": after,
        "elo_delta": state.get("elo_delta", after - before),
    }


def _format_elo_change(delta: Optional[Dict[str, int]], state: Dict[str, Any]) -> str:
    if is_human_vs_agent_state(state):
        return ""
    if is_avaa_state(state):
        return BoardController.format_avaa_elo_change(state)
    agent = state.get("model_display_name") or state.get("model_name") or "Agent"
    return BoardController.format_elo_change(delta, agent)


def _is_unranked_finish(state: Dict[str, Any]) -> bool:
    return state.get("result") == "*" or state.get("end_reason") == "inactivity"


def _list_agent_elo(
    state: Dict[str, Any],
    elo: Dict[str, Any],
    delta: Optional[Dict[str, int]],
    *,
    avaa: bool,
    human: bool,
) -> Optional[int]:
    if avaa:
        return elo.get("white_elo")
    if human:
        return elo.get("agent_elo")
    if state.get("status") != "in_progress" and _is_unranked_finish(state):
        return None
    if delta and delta.get("elo_after") is not None:
        return delta["elo_after"]
    after = state.get("elo_after")
    if after is not None:
        return round(after)
    return elo.get("agent_elo")


def _clear_stale_batch_calibration() -> None:
    """Remove leftover CLI batch live state so it is not mistaken for UI calibration."""
    live = _project_root / "elo_calibration" / "results" / "live_session.json"
    if live.exists():
        live.unlink()


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    _clear_stale_batch_calibration()
    rebuild_merged_ratings_file()
    try:
        await asyncio.to_thread(export_public_snapshots)
    except Exception:
        pass

    async def _idle_watcher():
        while True:
            await asyncio.sleep(60)
            try:
                await asyncio.to_thread(_get_game_service().prune_idle_games)
                from .identify_attempt import IdentifyAttemptStore
                from .limits import load_limits

                idle_sec = float(load_limits().idle_timeout_sec)
                await asyncio.to_thread(
                    PuzzleAttemptStore().prune_idle_active, idle_sec
                )
                await asyncio.to_thread(
                    IdentifyAttemptStore().prune_idle_active, idle_sec
                )
            except Exception:
                pass

    async def _leaderboard_snapshot_watcher():
        while True:
            await asyncio.sleep(LEADERBOARD_SNAPSHOT_INTERVAL_SEC)
            try:
                await asyncio.to_thread(export_public_snapshots)
            except Exception:
                pass

    idle_task = asyncio.create_task(_idle_watcher())
    snapshot_task = asyncio.create_task(_leaderboard_snapshot_watcher())
    if not calibration_in_process():
        try:
            await ensure_calibration_worker()
        except Exception:
            pass
    yield
    idle_task.cancel()
    snapshot_task.cancel()
    if calibration_in_process():
        await resolve_calibration_manager().stop_all()
    else:
        await shutdown_calibration_worker()
    _get_game_service()._release_engines()
    global _engine
    if _engine is not None:
        _engine.quit()
        _engine = None
    shutdown_workers()
    remove_spectator_meta()


app = FastAPI(title="Chess Vision Harness Spectator", lifespan=_lifespan)


@app.middleware("http")
async def _calibration_post_auth_middleware(request: Request, call_next):
    if request.method == "POST" and request.url.path.startswith("/api/calibration/"):
        try:
            require_calibration_auth(request)
        except HTTPException as exc:
            detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
            return JSONResponse({"detail": detail}, status_code=exc.status_code)
    return await call_next(request)


def _get_engine() -> Optional[EvalEngineAdapter]:
    global _engine
    if _engine is None:
        try:
            _engine = EvalEngineAdapter()
        except RuntimeError:
            return None
    return _engine


def _get_controller() -> BoardController:
    global _controller
    if _controller is None:
        _controller = BoardController(game_manager)
    return _controller


def _get_game_service() -> GameService:
    global _game_service
    if _game_service is None:
        # Share one BoardController with display helpers (no dual engine managers).
        _game_service = GameService(game_manager, controller=_get_controller())
    return _game_service


mount_api_v1(app, _get_game_service)
register_play_routes(app, lambda: game_manager)
register_contact_routes(app)

_public_site = _project_root / "public-site"
if (_public_site / "css").is_dir():
    app.mount("/css", StaticFiles(directory=str(_public_site / "css")), name="public_css")
if (_public_site / "js").is_dir():
    app.mount("/js", StaticFiles(directory=str(_public_site / "js")), name="public_js")


LIVE_CACHE_TTL_SEC = 5.0
_live_cache_lock = threading.Lock()
_live_cache: Dict[str, tuple[float, JSONResponse]] = {}


async def _live_cached_json_async(kind: str, build, max_age: int = 5) -> JSONResponse:
    """Short-TTL cache; runs the builder off the event loop."""
    now = time.monotonic()
    with _live_cache_lock:
        hit = _live_cache.get(kind)
        if hit and now - hit[0] < LIVE_CACHE_TTL_SEC:
            return hit[1]
    data = await asyncio.to_thread(build)
    resp = JSONResponse(data, headers={"cache-control": f"public, max-age={max_age}"})
    with _live_cache_lock:
        _live_cache[kind] = (time.monotonic(), resp)
    return resp


async def _live_leaderboard_json() -> JSONResponse:
    now = time.monotonic()
    with _live_cache_lock:
        hit = _live_cache.get("agents")
        if hit and now - hit[0] < LIVE_CACHE_TTL_SEC:
            return hit[1]
    data = await asyncio.to_thread(load_live_leaderboard, base_dir=_base)
    resp = JSONResponse(data, headers={"cache-control": "public, max-age=5"})
    with _live_cache_lock:
        _live_cache["agents"] = (time.monotonic(), resp)
    return resp


@app.get("/api/leaderboard/live")
async def live_leaderboard_api():
    """Live public ladder (agents + calibrated engines); same shape as snapshot JSON."""
    return await _live_leaderboard_json()


@app.get("/data/leaderboard.json")
async def live_leaderboard_data_file():
    """Serve live ladder at the static snapshot path while the origin is up."""
    return await _live_leaderboard_json()


async def _live_puzzle_leaderboard_json() -> JSONResponse:
    return await _live_cached_json_async("puzzles", load_live_puzzle_leaderboard)


@app.get("/api/leaderboard/puzzles/live")
async def live_puzzle_leaderboard_api():
    """Live puzzle leaderboard (agents + puzzle content view)."""
    return await _live_puzzle_leaderboard_json()


@app.get("/data/puzzles_leaderboard.json")
async def live_puzzle_data_file():
    """Serve live puzzle leaderboard at the static snapshot path while up."""
    return await _live_puzzle_leaderboard_json()


async def _live_identify_leaderboard_json() -> JSONResponse:
    return await _live_cached_json_async("identify", load_live_identify_leaderboard)


@app.get("/api/leaderboard/identify/live")
async def live_identify_leaderboard_api():
    """Live board-identification leaderboard (agent metrics per watch page)."""
    return await _live_identify_leaderboard_json()


@app.get("/data/identify_leaderboard.json")
async def live_identify_data_file():
    """Serve live identify leaderboard at the static snapshot path while up."""
    return await _live_identify_leaderboard_json()


if (_public_site / "data").is_dir():
    app.mount("/data", StaticFiles(directory=str(_public_site / "data")), name="public_data")


def _public_site_html(*parts: str) -> Optional[HTMLResponse]:
    path = _public_site.joinpath(*parts)
    if path.is_file():
        return HTMLResponse(path.read_text(encoding="utf-8"))
    return None


@app.get("/favicon.ico", include_in_schema=False)
async def favicon_ico():
    path = _public_site / "favicon.ico"
    if path.is_file():
        return FileResponse(path)
    raise HTTPException(status_code=404)


@app.get("/favicon.svg", include_in_schema=False)
async def favicon_svg():
    path = _public_site / "favicon.svg"
    if path.is_file():
        return FileResponse(path)
    raise HTTPException(status_code=404)


@app.get("/favicon-alert.svg", include_in_schema=False)
async def favicon_alert_svg():
    path = _public_site / "favicon-alert.svg"
    if path.is_file():
        return FileResponse(path)
    raise HTTPException(status_code=404)


@app.get("/health")
async def health():
    payload: Dict[str, Any] = {"ok": True, "status": "up"}
    if not calibration_in_process():
        worker_ok = await asyncio.to_thread(calibration_worker_healthy)
        payload["calibration_worker_ok"] = worker_ok
        if not worker_ok:
            err = calibration_worker_error()
            if err:
                payload["calibration_worker_error"] = err
    return payload


@app.get("/api/edge-health")
async def local_edge_health():
    """Same shape as Pages /api/edge-health so public chrome works on localhost."""
    return {
        "status": "online",
        "online": True,
        "origin": True,
        "message": "Local game server.",
    }


@app.get("/active")
@app.get("/active/")
async def redirect_active():
    return RedirectResponse(url="/spectator/", status_code=307)


@app.get("/completed")
@app.get("/completed/")
async def redirect_completed():
    return RedirectResponse(url="/spectator/?tab=completed", status_code=307)


@app.get("/spectator")
@app.get("/spectator/")
async def local_spectator():
    path = _project_root / "public-site" / "spectator" / "index.html"
    if path.is_file():
        return HTMLResponse(path.read_text(encoding="utf-8"))
    raise HTTPException(status_code=404)


@app.get("/human")
@app.get("/human/")
async def local_human():
    return RedirectResponse(url="/launch/?flow=playground", status_code=301)


@app.get("/contact")
@app.get("/contact/")
async def local_contact():
    resp = _public_site_html("contact", "index.html")
    if resp:
        return resp
    raise HTTPException(status_code=404)


def _eval_position(fen: str) -> Optional[int]:
    eng = _get_engine()
    if eng is None:
        return None
    now = time.time()
    cached = _eval_cache.get(fen)
    if cached and now - cached[0] < _EVAL_TTL:
        return cached[1]
    board = chess.Board(fen)
    score = eng.evaluate(board, depth=8)
    _eval_cache[fen] = (now, score)
    return score


def _board_stack_labels(labels: Dict[str, str], agent_color: str) -> Dict[str, str]:
    """Map chess-color labels to physical top/bottom (legacy agent-at-bottom helper)."""
    if agent_color == "BLACK":
        return {"top": labels["white"], "bottom": labels["black"]}
    return {"top": labels["black"], "bottom": labels["white"]}


def _eval_ui(
    score_white: Optional[int],
    labels: Dict[str, str],
    agent_color: str = "WHITE",
    *,
    white_at_bottom: bool = False,
) -> Dict[str, Any]:
    """Vertical eval aligned to board orientation.

    Spectator board.png is always white-at-bottom; pass white_at_bottom=True.
    """
    if white_at_bottom:
        stack = {"top": labels["black"], "bottom": labels["white"]}
        black_at_bottom = False
    else:
        stack = _board_stack_labels(labels, agent_color)
        black_at_bottom = agent_color == "BLACK"
    base = {
        "black_label": labels["black"],
        "white_label": labels["white"],
        "top_label": stack["top"],
        "bottom_label": stack["bottom"],
        "black_at_bottom": black_at_bottom,
    }
    if score_white is None:
        return {**base, "black_pct": "50%", "text": "—"}
    black_pct = max(4, min(96, 50 - score_white / 25))
    pawns = score_white / 100
    sign = "+" if pawns > 0 else ""
    return {**base, "black_pct": f"{black_pct:.1f}%", "text": f"{sign}{pawns:.1f}"}


def _resolve_eval_cp(state: Dict[str, Any], game_id: str) -> Optional[int]:
    if not show_eval_for_state(state):
        return None
    if state.get("last_eval_cp") is not None:
        return state["last_eval_cp"]
    if state.get("status") == "in_progress":
        return _eval_position(state["board_fen"])
    if game_id in _finished_eval_cache:
        return _finished_eval_cache[game_id]
    score = _eval_position(state["board_fen"])
    if score is not None:
        _finished_eval_cache[game_id] = score
    return score


from .move_rows import fen_at_ply as _fen_at_ply
from .move_rows import move_rows as _move_rows
from .move_rows import moves_payload, spectator_moves_payload


def _spectator_eval_ui(
    state: Dict[str, Any], score_white: Optional[int]
) -> Optional[Dict[str, Any]]:
    if not show_eval_for_state(state):
        return None
    labels = BoardController.side_labels(state)
    return _eval_ui(score_white, labels, white_at_bottom=True)


def _active_card(state: Dict[str, Any], game_id: str) -> Dict[str, Any]:
    ctrl = _get_controller()
    board = chess.Board(state["board_fen"])
    elo = ctrl._elo_context(state)

    if is_avaa_state(state):
        score_white = _eval_position(state["board_fen"])
        eval_ui = _spectator_eval_ui(state, score_white)
        white_name, black_name = BoardController.avaa_display_names(state)
        mover = white_name if board.turn == chess.WHITE else black_name
        turn = f"{mover} to move"
        if board.is_check():
            turn += " · check"
        return {
            "game_type": GAME_TYPE_AGENT_VS_AGENT,
            "white_name": white_name,
            "black_name": black_name,
            "white_elo": elo.get("white_elo"),
            "black_elo": elo.get("black_elo"),
            "agent_name": white_name,
            "opponent_label": black_name,
            "move_number": board.fullmove_number,
            "plies": len(state.get("moves", [])),
            "turn_label": turn,
            "eval_white_cp": score_white,
            "eval_ui": eval_ui,
            "show_eval": True,
            "board_url": f"/g/{game_id}/board.png",
            "board_cache": f"{len(state.get('moves', []))}:{state.get('last_move_uci') or ''}",
        }

    if is_human_vs_agent_state(state):
        card = human_active_card(state, game_id, board, elo)
        score_white = _eval_position(state["board_fen"])
        card["eval_white_cp"] = score_white
        card["eval_ui"] = _spectator_eval_ui(state, score_white)
        card["show_eval"] = True
        return card

    score_white = _eval_position(state["board_fen"])
    eval_ui = _spectator_eval_ui(state, score_white)
    persp = ctrl._perspective(board, state["agent_color"])
    model = state.get("model_display_name") or state.get("model_name") or "Agent"
    opponent_label = BoardController.engine_display_label(state)
    turn = "Agent to move" if persp["your_turn"] else "Opponent to move"
    if persp["in_check"] and persp["your_turn"]:
        turn += " · check"
    return {
        "agent_name": model,
        "agent_color": state["agent_color"],
        "opponent_label": opponent_label,
        "engine_label": opponent_label,
        "opponent_id": state.get("opponent_id"),
        "agent_elo": elo.get("agent_elo"),
        "opponent_elo": elo.get("opponent_elo"),
        "engine_elo": elo.get("engine_elo"),
        "move_number": board.fullmove_number,
        "plies": len(state.get("moves", [])),
        "your_turn": persp["your_turn"],
        "turn_label": turn,
        "eval_white_cp": score_white,
        "eval_ui": eval_ui,
        "show_eval": True,
        "board_url": f"/g/{game_id}/board.png",
        "board_cache": f"{len(state.get('moves', []))}:{state.get('last_move_uci') or ''}",
    }


def _list_active_card(state: Dict[str, Any], game_id: str) -> Dict[str, Any]:
    """Games-list projection without live Stockfish eval (uses cached last_eval_cp only)."""
    ctrl = _get_controller()
    board = chess.Board(state["board_fen"])
    elo = ctrl._elo_context(state)
    cached_cp = state.get("last_eval_cp")
    eval_ui = (
        _spectator_eval_ui(state, cached_cp)
        if cached_cp is not None and show_eval_for_state(state)
        else None
    )

    if is_avaa_state(state):
        white_name, black_name = BoardController.avaa_display_names(state)
        mover = white_name if board.turn == chess.WHITE else black_name
        turn = f"{mover} to move"
        if board.is_check():
            turn += " · check"
        return {
            "game_type": GAME_TYPE_AGENT_VS_AGENT,
            "white_name": white_name,
            "black_name": black_name,
            "white_elo": elo.get("white_elo"),
            "black_elo": elo.get("black_elo"),
            "agent_name": white_name,
            "opponent_label": black_name,
            "move_number": board.fullmove_number,
            "plies": len(state.get("moves", [])),
            "turn_label": turn,
            "eval_white_cp": cached_cp,
            "eval_ui": eval_ui,
            "show_eval": True,
            "board_url": f"/g/{game_id}/board.png",
            "board_cache": f"{len(state.get('moves', []))}:{state.get('last_move_uci') or ''}",
        }

    if is_human_vs_agent_state(state):
        card = human_active_card(state, game_id, board, elo)
        card["eval_white_cp"] = cached_cp
        card["eval_ui"] = eval_ui
        return card

    persp = ctrl._perspective(board, state["agent_color"])
    model = state.get("model_display_name") or state.get("model_name") or "Agent"
    opponent_label = BoardController.engine_display_label(state)
    turn = "Agent to move" if persp["your_turn"] else "Opponent to move"
    if persp["in_check"] and persp["your_turn"]:
        turn += " · check"
    return {
        "agent_name": model,
        "agent_color": state["agent_color"],
        "opponent_label": opponent_label,
        "engine_label": opponent_label,
        "opponent_id": state.get("opponent_id"),
        "agent_elo": elo.get("agent_elo"),
        "opponent_elo": elo.get("opponent_elo"),
        "engine_elo": elo.get("engine_elo"),
        "move_number": board.fullmove_number,
        "plies": len(state.get("moves", [])),
        "your_turn": persp["your_turn"],
        "turn_label": turn,
        "eval_white_cp": cached_cp,
        "eval_ui": eval_ui,
        "show_eval": True,
        "board_url": f"/g/{game_id}/board.png",
        "board_cache": f"{len(state.get('moves', []))}:{state.get('last_move_uci') or ''}",
    }


def _avaa_list_fields(state: Dict[str, Any], elo: Dict[str, Any]) -> Dict[str, Any]:
    white_name, black_name = BoardController.avaa_display_names(state)
    return {
        "game_type": GAME_TYPE_AGENT_VS_AGENT,
        "white_model_id": state.get("white_model_id"),
        "black_model_id": state.get("black_model_id"),
        "white_display_name": white_name,
        "black_display_name": black_name,
        "white_elo": elo.get("white_elo"),
        "black_elo": elo.get("black_elo"),
        "white_joined": bool(state.get("white_joined")),
        "black_joined": bool(state.get("black_joined")),
        "model_id": state.get("white_model_id"),
        "model_name": white_name,
        "agent_elo": elo.get("white_elo"),
        "opponent_label": black_name,
        "opponent_elo": elo.get("black_elo"),
    }


def _display_name_without_elo(value: Any) -> str:
    """Remove a trailing, presentation-only Elo suffix from a player label."""
    return re.sub(r"\s*\(\d+\)\s*$", "", str(value or "")).strip()


def _side_list_fields(
    state: Dict[str, Any], elo: Dict[str, Any], *, avaa: bool, human: bool
) -> Dict[str, Any]:
    """Return white/black display and ladder Elo values for every game mode."""
    if avaa:
        return _avaa_list_fields(state, elo)
    if human:
        fields = human_list_fields(state, elo)
        agent_elo = elo.get("agent_elo")
        fields.update(
            {
                "white_display_name": _display_name_without_elo(
                    fields["white_display_name"]
                ),
                "black_display_name": _display_name_without_elo(
                    fields["black_display_name"]
                ),
                "white_elo": agent_elo
                if state.get("agent_color") == "WHITE"
                else None,
                "black_elo": agent_elo
                if state.get("agent_color") == "BLACK"
                else None,
            }
        )
        return fields

    labels = BoardController.side_labels(state)
    agent_name = _display_name_without_elo(
        state.get("model_display_name")
        or state.get("model_name")
        or labels.get("agent")
        or "Agent"
    )
    opponent_name = _display_name_without_elo(
        BoardController.engine_display_label(state) or "Opponent"
    )
    agent_elo = elo.get("agent_elo")
    opponent_elo = elo.get("opponent_elo", elo.get("engine_elo"))
    if state.get("agent_color") == "WHITE":
        white_name, black_name = agent_name, opponent_name
        white_elo, black_elo = agent_elo, opponent_elo
    else:
        white_name, black_name = opponent_name, agent_name
        white_elo, black_elo = opponent_elo, agent_elo
    return {
        "white_display_name": white_name,
        "black_display_name": black_name,
        "white_elo": white_elo,
        "black_elo": black_elo,
    }


def _enrich_list_game(g: Dict[str, Any]) -> Dict[str, Any]:
    state = g["state"]
    game_id = g["game_id"]
    ctrl = _get_controller()
    revision = BoardController.game_revision(state)
    avaa = is_avaa_state(state)
    human = is_human_vs_agent_state(state)
    elo_delta_raw = None
    elo_delta = None
    active_card = None
    agent_outcome = None
    if state.get("status") != "in_progress":
        elo_delta_raw = _list_elo_delta(state, game_id)
        elo_delta = _format_elo_change(elo_delta_raw, state)
        if not avaa:
            agent_outcome = BoardController.agent_outcome(
                state["agent_color"], state.get("result")
            )
    else:
        active_card = _list_active_card(state, game_id)

    elo = ctrl._elo_context(state)
    names = _side_list_fields(state, elo, avaa=avaa, human=human)
    if avaa:
        agent_name = names["model_name"]
        opp_label = names["opponent_label"]
    elif human:
        agent_name = names["model_name"]
        opp_label = names["opponent_label"]
    else:
        agent_name = (
            state.get("model_display_name")
            or state.get("model_name")
            or "Agent"
        )
        opp_label = _display_name_without_elo(BoardController.engine_display_label(state))

    if state.get("status") != "in_progress":
        reason = state.get("end_reason")
        if reason:
            end_reason_label = ctrl.format_end_reason(reason, state)
        elif state.get("result") == "*":
            end_reason_label = "No result (idle timeout)"
        else:
            end_reason_label = None
    else:
        end_reason_label = None
    row: Dict[str, Any] = {
        "game_id": game_id,
        "revision": revision,
        "status": state.get("status"),
        "result": state.get("result"),
        "end_reason_label": end_reason_label,
        "summary": _game_summary(state),
        "elo_change": elo_delta,
        "agent_outcome": agent_outcome,
        "outcome_label": (agent_outcome or {}).get("label"),
        "active_card": active_card,
        "model_id": state.get("model_name"),
        "model_name": agent_name,
        "agent_elo": _list_agent_elo(
            state, elo, elo_delta_raw, avaa=avaa, human=human
        ),
        "opponent_id": state.get("opponent_id"),
        "opponent_label": opp_label,
        "opponent_elo": (
            elo.get("opponent_elo") or elo.get("engine_elo")
            if not avaa and not human
            else state.get("opponent_elo") or state.get("engine_elo")
        ),
        "last_activity": state.get("last_activity"),
        "turn": active_card["turn_label"] if active_card else (
            ctrl.format_spectator_summary(state).split(" — ", 1)[-1]
            if state.get("status") == "in_progress"
            else (
                end_reason_label or "No result"
                if state.get("result") == "*"
                else state.get("result") or "done"
            )
        ),
    }
    row.update(quality_fields_from_state(state, include_provisional=True))
    row.update(names)
    if avaa:
        row["game_type"] = GAME_TYPE_AGENT_VS_AGENT
    elif human:
        row["game_type"] = GAME_TYPE_HUMAN_VS_AGENT
    else:
        row["game_type"] = state.get("game_type") or DEFAULT_GAME_TYPE
    return row


def _build_games_list(
    status: Optional[str],
    limit: Optional[int],
    offset: int,
) -> tuple[list[Dict[str, Any]], int]:
    _get_game_service().prune_idle_games()
    games = game_manager.list_games()
    if status in ("in_progress", "active"):
        games = [g for g in games if g["state"].get("status") == "in_progress"]
    elif status in ("finished", "done", "completed"):
        games = [g for g in games if g["state"].get("status") != "in_progress"]

    total = len(games)
    if limit is not None:
        games = games[offset : offset + limit]
    else:
        games = games[offset:]
    return [_enrich_list_game(g) for g in games], total


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    tab = request.query_params.get("tab")
    if tab == "done":
        return RedirectResponse(url="/spectator/?tab=completed", status_code=307)
    if tab == "active":
        return RedirectResponse(url="/spectator/", status_code=307)
    resp = _public_site_html("index.html")
    if resp:
        return resp
    raise HTTPException(status_code=404)


@app.get("/create", response_class=HTMLResponse)
@app.get("/create/", response_class=HTMLResponse)
async def create_game_get(mode: Optional[str] = None):
    flow = "engine"
    if mode == "human":
        flow = "playground"
    elif mode == "avaa":
        flow = "avaa"
    elif mode == "avh":
        flow = "playground"
    return RedirectResponse(url=f"/launch/?flow={flow}", status_code=301)


@app.get("/identify", response_class=HTMLResponse)
@app.get("/identify/", response_class=HTMLResponse)
async def identify_page():
    return RedirectResponse(url="/launch/?flow=identify", status_code=301)


@app.get("/lobby", response_class=HTMLResponse)
@app.get("/lobby/", response_class=HTMLResponse)
async def lobby_page():
    return RedirectResponse(url="/launch/?flow=avaa", status_code=301)


@app.get("/leaderboard", response_class=HTMLResponse)
@app.get("/leaderboard/", response_class=HTMLResponse)
async def leaderboard():
    resp = _public_site_html("leaderboard", "index.html")
    if resp:
        return resp
    raise HTTPException(status_code=404)


@app.get("/puzzles", response_class=HTMLResponse)
@app.get("/puzzles/", response_class=HTMLResponse)
async def puzzles_page():
    return RedirectResponse(url="/launch/?flow=puzzles", status_code=301)


@app.get("/launch", response_class=HTMLResponse)
@app.get("/launch/", response_class=HTMLResponse)
async def launch_page():
    resp = _public_site_html("launch", "index.html")
    if resp:
        return resp
    raise HTTPException(status_code=404)


@app.get("/calibration", response_class=HTMLResponse)
async def calibration_page(request: Request):
    from .calibration_auth import host_is_loopback

    return HTMLResponse(render_calibration_html(loopback=host_is_loopback(request)))


@app.get("/api/calibration/status/live")
async def calibration_status_live():
    return await asyncio.to_thread(get_calibration_status_live)


@app.get("/api/calibration/status")
async def calibration_status():
    # Heavy sync work (samples/maps/ratings) — keep the event loop free for HTML/UI.
    return await asyncio.to_thread(get_calibration_status)


@app.post("/api/calibration/continuous/{engine_id}/start")
async def calibration_continuous_start(
    engine_id: str,
    parallel: int = Query(1, ge=1, le=100),
    confirm: bool = Query(False),
):
    mgr = resolve_calibration_manager()
    if not can_continuously_calibrate(engine_id, pairing_mode=mgr.pairing_mode()):
        raise HTTPException(400, f"Engine cannot be continuously calibrated: {engine_id}")
    if mgr.is_running(engine_id):
        raise HTTPException(409, f"Continuous calibration already running for {engine_id}")
    err = assess_parallel_start(parallel, confirm=confirm)
    if err:
        raise HTTPException(400, err)
    err = assess_fleet_parallel(mgr, parallel, confirm=confirm)
    if err:
        raise HTTPException(400, err)
    try:
        if not calibration_in_process():
            await ensure_calibration_worker()
        await mgr.start(engine_id, parallel=parallel)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except RuntimeError as e:
        msg = str(e)
        if "already running" in msg.lower():
            raise HTTPException(409, msg) from e
        raise HTTPException(503, msg) from e
    return {"ok": True, "engine_id": engine_id, "running": True, "parallel": parallel}


@app.post("/api/calibration/continuous/{engine_id}/stop")
async def calibration_continuous_stop(engine_id: str):
    await resolve_calibration_manager().stop(engine_id)
    return {"ok": True, "engine_id": engine_id, "running": False}


def _reject_pairing_change_while_running() -> None:
    mgr = resolve_calibration_manager()
    if mgr.running_engines():
        raise HTTPException(
            409,
            "Stop continuous calibration before changing pairing settings",
        )


@app.post("/api/calibration/pairing-mode")
async def calibration_set_pairing_mode(mode: str = Query(...)):
    _reject_pairing_change_while_running()
    try:
        pairing_mode = resolve_calibration_manager().set_pairing_mode(mode)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return {"ok": True, "pairing_mode": pairing_mode}


@app.post("/api/calibration/start-all")
async def calibration_start_all(
    parallel: int = Query(1, ge=1, le=100),
    confirm: bool = Query(False),
):
    mgr = resolve_calibration_manager()
    err = assess_start_all(mgr, parallel, confirm=confirm)
    if err:
        raise HTTPException(400, err)
    try:
        if not calibration_in_process():
            await ensure_calibration_worker()
        started = await mgr.start_all(parallel=parallel)
    except RuntimeError as e:
        raise HTTPException(503, str(e)) from e
    return {"ok": True, "started": started, "count": len(started), "parallel": parallel}


@app.post("/api/calibration/stop-all")
async def calibration_stop_all():
    stopped = await resolve_calibration_manager().stop_all()
    return {"ok": True, "stopped": stopped, "count": len(stopped)}


@app.post("/api/calibration/fixed-opponent")
async def calibration_set_fixed_opponent(opponent: str = Query(...)):
    _reject_pairing_change_while_running()
    try:
        opponent_id = resolve_calibration_manager().set_fixed_opponent(opponent)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return {"ok": True, "fixed_opponent_id": opponent_id}


@app.post("/api/calibration/rebuild-play-rating-map")
async def calibration_rebuild_play_rating_map():
    from .accuracy_elo_map import rebuild_accuracy_elo_map
    from .results import ResultsManager

    payload = await asyncio.to_thread(rebuild_accuracy_elo_map)
    recomputed = await asyncio.to_thread(ResultsManager().recompute_play_rating_rows)
    await asyncio.to_thread(export_public_snapshots)
    engine_count = int(payload.get("engine_count") or 0)
    min_engines = int(payload.get("min_engines") or 2)
    return {
        "ok": True,
        "engine_count": engine_count,
        "min_engines": min_engines,
        "sample_count": engine_count,
        "min_samples": min_engines,
        "fitted_at": payload.get("fitted_at"),
        "rows_recomputed": recomputed,
        "warm": engine_count >= min_engines and bool(payload.get("fitted_at")),
    }


@app.get("/g/{game_id}", response_class=HTMLResponse)
async def game_view(game_id: str):
    """Static shell from public-site/g/; game data via /api/games/*."""
    return watch_shell_response("g")


@app.get("/g/{game_id}/board.png")
async def get_board_image(game_id: str):
    if not game_manager.validate_game_id(game_id):
        raise HTTPException(404, "Board not found")
    await run_blocking(_get_controller().refresh_board_image, game_id)
    board_path = game_manager.get_board_path(game_id)
    if not board_path.exists():
        raise HTTPException(404, "Board not found")
    return FileResponse(board_path, media_type="image/png")


def _public_attempt(attempt_id: str):
    from .limits import load_limits

    record = PuzzleAttemptStore().abandon_if_idle(
        attempt_id, float(load_limits().idle_timeout_sec)
    )
    if record is None:
        raise HTTPException(404, "Attempt not found")
    return record


@app.get("/p/{attempt_id}", response_class=HTMLResponse)
async def puzzle_watch_page(attempt_id: str):
    """Static shell from public-site/p/; attempt data via public puzzle API."""
    return watch_shell_response("p")


@app.get("/p/{attempt_id}/board.png")
async def puzzle_watch_board_image(attempt_id: str):
    record = _public_attempt(attempt_id)
    return Response(
        content=render_observer_board_png(record),
        media_type="image/png",
        headers={"Cache-Control": "no-store"},
    )


@app.get("/p/{attempt_id}/board.txt")
async def puzzle_watch_board_text(attempt_id: str):
    record = _public_attempt(attempt_id)
    board = chess.Board(record.get("board_fen", chess.STARTING_FEN))
    return PlainTextResponse(
        content=format_board_text(board),
        headers={"Cache-Control": "no-store"},
    )


@app.get("/api/v1/puzzles/public/attempts")
async def public_puzzle_attempts(
    request: Request,
    status: Optional[str] = Query(None),
    by_key: Optional[str] = Query(None),
    by_agent: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """Observer-scoped discovery: active, finished, and abandoned attempts, newest first.

    ``by_key`` narrows the list to one pseudonymous attempt chain; it is
    rate-limited per client (and caps the page size) so a key cannot be used
    as an unbounded scanning handle over the whole store.
    """
    records = PuzzleAttemptStore().list_records()
    if by_key:
        limits = get_limit_enforcer()
        denied = limits.check_public_by_key(request, by_key)
        if denied is not None:
            return denied
        limits.record_public_by_key(request, by_key)
        records = [r for r in records if r.get("key_fingerprint") == by_key]
        limit = min(limit, 50)
    elif by_agent:
        records = [r for r in records if _agent_name(r) == by_agent]
        limit = min(limit, 50)
    if status in ("active", "finished", "abandoned"):
        records = [r for r in records if r.get("status") == status]
    else:
        records = [
            r
            for r in records
            if r.get("status") in ("active", "finished", "abandoned")
        ]
    records.sort(key=lambda r: r.get("started_at") or "", reverse=True)
    total = len(records)
    rows = [public_attempt_row(r) for r in records[offset : offset + limit]]
    return {"ok": True, "attempts": rows, "total": total}


@app.get("/api/v1/puzzles/public/{attempt_id}")
async def public_puzzle_state(attempt_id: str):
    return observer_state(_public_attempt(attempt_id))


@app.get("/api/v1/puzzles/public/{attempt_id}/replay")
async def public_puzzle_replay(attempt_id: str):
    """Replay unlocks only after the attempt ends (no observer secrecy leak)."""
    record = _public_attempt(attempt_id)
    if record.get("status") == "active":
        raise HTTPException(409, "Replay unlocks only after the attempt ends")
    if record.get("status") != "finished":
        raise HTTPException(404, "No replay for an abandoned attempt")
    return replay_payload(record)


def _public_identify(attempt_id: str):
    from .limits import load_limits

    record = IdentifyAttemptStore().abandon_if_idle(
        attempt_id, float(load_limits().idle_timeout_sec)
    )
    if record is None:
        raise HTTPException(404, "Attempt not found")
    return record


@app.get("/i/{attempt_id}", response_class=HTMLResponse)
async def identify_watch_page(attempt_id: str):
    """Static shell from public-site/i/; attempt data via public identify API."""
    return watch_shell_response("i")


@app.get("/i/{attempt_id}/board.png")
async def identify_watch_board_image(attempt_id: str):
    record = _public_identify(attempt_id)
    return Response(
        content=render_identify_board_png(record),
        media_type="image/png",
        headers={"Cache-Control": "no-store"},
    )


@app.get("/i/{attempt_id}/board.txt")
async def identify_watch_board_text(attempt_id: str):
    record = _public_identify(attempt_id)
    board = chess.Board(record.get("corpus_fen", chess.STARTING_FEN))
    return PlainTextResponse(
        content=format_board_text(board),
        headers={"Cache-Control": "no-store"},
    )


@app.get("/i/{attempt_id}/answer.png")
async def identify_watch_answer_image(attempt_id: str):
    """Answer overlay board (true placement); only after the attempt ends."""
    record = _public_identify(attempt_id)
    if record.get("status") == "active":
        raise HTTPException(409, "Answer unlocks only after the attempt ends")
    if record.get("status") != "finished":
        raise HTTPException(404, "No answer for an abandoned attempt")
    return Response(
        content=render_answer_overlay_png(record),
        media_type="image/png",
        headers={"Cache-Control": "no-store"},
    )


@app.get("/api/v1/identify/public/attempts")
async def public_identify_attempts(
    request: Request,
    status: Optional[str] = Query(None),
    by_key: Optional[str] = Query(None),
    by_agent: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """Observer-scoped discovery: active, finished, and abandoned identification attempts.

    ``by_key`` narrows the list to one pseudonymous attempt chain; it is
    rate-limited per client (and caps the page size) so a key cannot be used
    as an unbounded scanning handle over the whole store.
    """
    records = IdentifyAttemptStore().list_records()
    if by_key:
        limits = get_limit_enforcer()
        denied = limits.check_public_by_key(request, by_key)
        if denied is not None:
            return denied
        limits.record_public_by_key(request, by_key)
        records = [r for r in records if r.get("key_fingerprint") == by_key]
        limit = min(limit, 50)
    elif by_agent:
        records = [r for r in records if identify_agent_name(r) == by_agent]
        limit = min(limit, 50)
    if status in ("active", "finished", "abandoned"):
        records = [r for r in records if r.get("status") == status]
    else:
        records = [
            r
            for r in records
            if r.get("status") in ("active", "finished", "abandoned")
        ]
    records.sort(key=lambda r: r.get("started_at") or "", reverse=True)
    total = len(records)
    rows = [identify_public_row(r) for r in records[offset : offset + limit]]
    return {"ok": True, "attempts": rows, "total": total}


@app.get("/api/v1/identify/public/{attempt_id}")
async def public_identify_state(attempt_id: str):
    return identify_observer_state(_public_identify(attempt_id))


@app.get("/api/v1/identify/public/{attempt_id}/replay")
async def public_identify_replay(attempt_id: str):
    """Replay unlocks only after the attempt ends (no observer secrecy leak)."""
    record = _public_identify(attempt_id)
    if record.get("status") == "active":
        raise HTTPException(409, "Replay unlocks only after the attempt ends")
    if record.get("status") != "finished":
        raise HTTPException(404, "No replay for an abandoned attempt")
    return identify_replay_payload(record)


@app.get("/api/games")
async def list_games(
    status: Optional[str] = Query(None),
    limit: Optional[int] = Query(None, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """List games newest-first. status=in_progress|finished; omit for all."""
    enriched, total = await run_blocking(_build_games_list, status, limit, offset)
    return {
        "games": enriched,
        "total": total,
        "offset": offset,
        "limit": limit,
    }


@app.get("/api/games/{game_id}/state")
async def get_game_state(game_id: str, debug: Optional[str] = None):
    state = game_manager.load_state(game_id)
    if not state:
        raise HTTPException(404, "Game not found")
    avaa = is_avaa_state(state)
    human = is_human_vs_agent_state(state)
    delta = _game_elo_change(state, game_id)
    ctrl = _get_controller()
    board = chess.Board(state["board_fen"])
    labels = BoardController.side_labels(state)
    show_eval = show_eval_for_state(state)
    score_white = (
        await run_eval(_resolve_eval_cp, state, game_id) if show_eval else None
    )
    eval_ui = _spectator_eval_ui(state, score_white) if show_eval else None
    end_reason_label = (
        ctrl.resolve_end_reason(state, game_id) if state.get("status") != "in_progress" else None
    )
    board_path = str(game_manager.get_board_path(game_id))
    game_over = state.get("status") != "in_progress" or board.is_game_over()
    elo_ctx = ctrl._elo_context(state)

    if avaa:
        white_name, black_name = BoardController.avaa_display_names(state)
        outcome = None
        agent_elo = elo_ctx.get("white_elo")
        engine_elo = elo_ctx.get("black_elo")
        engine_label = black_name
        opponent_label = black_name
        extra = _avaa_list_fields(state, elo_ctx)
    elif human:
        from .spectator_human import human_display_names

        white_name, black_name = human_display_names(state)
        outcome = BoardController.agent_outcome(state["agent_color"], state.get("result"))
        agent_elo = elo_ctx.get("agent_elo")
        engine_elo = None
        engine_label = white_name if state.get("human_color") == "WHITE" else black_name
        opponent_label = state.get("human_nickname") or "Human"
        extra = human_state_extra(state, elo_ctx)
        game_over = state.get("status") != "in_progress" or board.is_game_over()
    else:
        persp = ctrl._perspective(board, state["agent_color"])
        outcome = BoardController.agent_outcome(state["agent_color"], state.get("result"))
        game_over = state.get("status") != "in_progress" or persp.get("game_over")
        pgn_headers = state.get("pgn_headers") or {}
        engine_name = pgn_headers.get("EngineName", "Stockfish 17.1")
        engine_label = BoardController.engine_display_label(state)
        opponent_label = engine_label
        agent_elo = (
            delta["elo_after"]
            if delta
            else round(_ladder().get_rating(state["model_name"]))
            if state.get("model_name")
            else None
        )
        engine_elo = state.get("opponent_elo")
        extra = {}

    if debug_state_enabled(debug):
        payload: Dict[str, Any] = {
            **state,
            "revision": BoardController.game_revision(state),
            "summary": _game_summary(state),
            "elo_change": _format_elo_change(delta, state),
            "end_reason_label": end_reason_label,
            "engine_label": engine_label,
            "agent_outcome": outcome if state.get("status") != "in_progress" else None,
            "move_rows": _move_rows(state),
            "eval_ui": eval_ui,
            "show_eval": show_eval,
            "agent_elo": agent_elo,
            "engine_elo": engine_elo,
            "game_over": game_over,
            "move_count": len(state.get("moves", [])),
            "board_path": board_path,
            **extra,
        }
        if not avaa:
            payload["engine_name"] = engine_name
        return payload

    return agent_safe_spectator_state(
        state,
        revision=BoardController.game_revision(state),
        summary=_game_summary(state),
        elo_change=_format_elo_change(delta, state),
        end_reason_label=end_reason_label,
        engine_label=engine_label,
        agent_outcome=outcome if state.get("status") != "in_progress" else None,
        eval_ui=eval_ui,
        show_eval=show_eval,
        agent_elo=agent_elo,
        engine_elo=engine_elo,
        game_over=game_over,
        board_path=board_path,
        opponent_label=opponent_label,
        extra=extra,
    )


@app.get("/api/games/{game_id}/moves")
async def get_game_moves(game_id: str):
    state = game_manager.load_state(game_id)
    if not state:
        raise HTTPException(404, "Game not found")
    return spectator_moves_payload(state)


@app.get("/api/games/{game_id}/chat")
async def get_game_chat(game_id: str, since: int = Query(0, ge=0)):
    """Public read-only chat for spectators of human-vs-agent games."""
    from .chat import read_chat_messages
    from .game_types import is_human_vs_agent_state

    state = game_manager.load_state(game_id)
    if not state:
        raise HTTPException(404, "Game not found")
    if not is_human_vs_agent_state(state):
        raise HTTPException(404, "Chat is only available for agent vs human games")
    result = read_chat_messages(game_manager, game_id, since=since)
    if not result.get("ok"):
        raise HTTPException(404, result.get("error", "Game not found"))
    return result


@app.get("/api/games/{game_id}/pgn")
async def get_game_pgn(game_id: str, debug: Optional[str] = None):
    if not debug_state_enabled(debug):
        state = game_manager.load_state(game_id)
        if state and state.get("status") == "in_progress":
            raise HTTPException(
                403,
                "PGN available after the game ends. Enable CHESS_HARNESS_DEBUG for operator access.",
            )
    pgn_path = game_manager.get_pgn_path(game_id)
    if pgn_path.exists():
        return {"pgn": _get_controller()._clean_pgn(pgn_path.read_text(encoding="utf-8"))}
    result = _get_game_service().export_pgn(
        game_id, allow_in_progress=debug_state_enabled(debug)
    )
    if not result["ok"]:
        raise HTTPException(404, result["error"])
    return {"pgn": result["pgn"]}


@app.get("/api/games/{game_id}/eval")
async def get_eval(game_id: str, ply: Optional[int] = Query(None)):
    """Tip eval (omit ply) or historical ply eval. Never returns FEN."""
    state = game_manager.load_state(game_id)
    if not state:
        raise HTTPException(404, "Game not found")
    if not show_eval_for_state(state):
        return {"ok": True, "show_eval": False}

    def _compute() -> Dict[str, Any]:
        tip_ply = len(state.get("moves", []))
        at_tip = ply is None or int(ply) >= tip_ply
        final = state["status"] != "in_progress"
        try:
            if at_tip:
                score = _resolve_eval_cp(state, game_id)
            else:
                n = max(0, int(ply))
                fen = _fen_at_ply(state, n)
                score = _eval_position(fen)
            body: Dict[str, Any] = {
                "ok": True,
                "score": score if score is not None else 0,
                "eval_ui": _spectator_eval_ui(state, score),
            }
            if final:
                body["final"] = True
            return body
        except Exception:
            return {"ok": False, "score": 0}

    return await run_eval(_compute)


def start_spectator(host: str = "127.0.0.1", port: int = 8765):
    import uvicorn

    uvicorn.run(app, host=host, port=port)
