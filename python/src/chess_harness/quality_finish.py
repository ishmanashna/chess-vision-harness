"""Background post-game quality analysis (Phase 2 harness orchestrator)."""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Literal, Optional, Set, Tuple

from .game_manager import GameManager
from .game_quality import GameQuality, SideQuality, analyse_game
from .game_types import GAME_TYPE_AGENT_VS_AGENT
from .results import ResultsManager

_log = logging.getLogger(__name__)

QualityJob = Tuple[Literal["final", "provisional"], int, bool]

_running: Set[str] = set()
_pending: Dict[str, QualityJob] = {}
_queue_lock = threading.Lock()


def schedule_game_quality(
    game_id: str,
    *,
    base_dir: Optional[str] = None,
    map_root: Optional[Path] = None,
    force: bool = False,
) -> None:
    """Enqueue background quality analysis after PGN is on disk (finished games)."""
    _enqueue_quality(
        game_id,
        ("final", 0, force),
        base_dir=base_dir,
        map_root=map_root,
    )


def schedule_provisional_game_quality(
    game_id: str,
    *,
    move_count: int,
    base_dir: Optional[str] = None,
    map_root: Optional[Path] = None,
) -> None:
    """Enqueue debounced provisional quality for an in-progress game."""
    if move_count <= 0:
        return
    _enqueue_quality(
        game_id,
        ("provisional", move_count, False),
        base_dir=base_dir,
        map_root=map_root,
    )


def _enqueue_quality(
    game_id: str,
    job: QualityJob,
    *,
    base_dir: Optional[str] = None,
    map_root: Optional[Path] = None,
) -> None:
    with _queue_lock:
        existing = _pending.get(game_id)
        if existing:
            mode, move_count, force = job
            if mode == "final":
                _pending[game_id] = ("final", 0, force or existing[2])
            else:
                prev_mode, prev_moves, prev_force = existing
                if prev_mode == "final":
                    return
                _pending[game_id] = (
                    "provisional",
                    max(move_count, prev_moves),
                    prev_force,
                )
        else:
            _pending[game_id] = job
        if game_id in _running:
            return
        _running.add(game_id)
    thread = threading.Thread(
        target=_run_queue,
        args=(game_id, base_dir, map_root),
        name=f"quality-{game_id}",
        daemon=True,
    )
    thread.start()


def _run_queue(
    game_id: str, base_dir: Optional[str], map_root: Optional[Path]
) -> None:
    try:
        while True:
            with _queue_lock:
                job = _pending.pop(game_id, None)
            if not job:
                break
            mode, move_count, force = job
            try:
                if mode == "provisional":
                    run_provisional_game_quality(
                        game_id,
                        move_count=move_count,
                        base_dir=base_dir,
                        map_root=map_root,
                    )
                else:
                    run_game_quality(
                        game_id,
                        base_dir=base_dir,
                        map_root=map_root,
                        force=force,
                    )
            except Exception:
                _log.exception("quality job failed for %s (%s)", game_id, mode)
            with _queue_lock:
                if game_id not in _pending:
                    break
    finally:
        with _queue_lock:
            _running.discard(game_id)


def run_provisional_game_quality(
    game_id: str,
    *,
    move_count: int,
    base_dir: Optional[str] = None,
    map_root: Optional[Path] = None,
) -> bool:
    """Analyse in-progress PGN for spectator metrics. State only, no results upsert."""
    if move_count <= 0:
        return False
    gm = GameManager(base_dir=base_dir)
    state = gm.load_state(game_id)
    if not state or state.get("status") != "in_progress":
        return False
    plies = len(state.get("moves") or [])
    if plies <= 0:
        return False
    if plies < move_count:
        move_count = plies
    if (
        state.get("quality_move_count") == move_count
        and state.get("quality_provisional")
        and state.get("quality_at")
    ):
        return False

    pgn_path = gm.get_pgn_path(game_id)
    if not pgn_path.exists():
        return False

    try:
        pgn_text = pgn_path.read_text(encoding="utf-8")
        quality = analyse_game(pgn_text)
    except Exception:
        _log.exception("provisional quality analysis failed for %s", game_id)
        return False

    quality_at = datetime.now(timezone.utc).isoformat()
    try:
        with gm.game_lock(game_id):
            state = gm.load_state(game_id)
            if not state or state.get("status") != "in_progress":
                return False
            plies = len(state.get("moves") or [])
            if plies <= 0:
                return False
            if plies < move_count:
                move_count = plies
            if (
                state.get("quality_move_count") == move_count
                and state.get("quality_provisional")
                and state.get("quality_at")
            ):
                return False
            _patch_state_quality(
                state,
                quality,
                quality_at,
                map_root=map_root,
                provisional=True,
                move_count=move_count,
            )
            gm.save_state(game_id, state)
    except Exception:
        _log.exception("failed to patch provisional quality for %s", game_id)
        return False
    return True


def run_game_quality(
    game_id: str,
    *,
    base_dir: Optional[str] = None,
    map_root: Optional[Path] = None,
    force: bool = False,
) -> bool:
    """Synchronous quality pass (scheduler + tests). Returns True if fields were patched."""
    gm = GameManager(base_dir=base_dir)
    state = gm.load_state(game_id)
    if not state or state.get("status") != "finished":
        return False
    if state.get("result") == "*":
        return False
    if state.get("quality_at") and not force and not state.get("quality_provisional"):
        return False

    pgn_path = gm.get_pgn_path(game_id)
    if not pgn_path.exists():
        return False

    try:
        pgn_text = pgn_path.read_text(encoding="utf-8")
        quality = analyse_game(pgn_text)
    except Exception:
        _log.exception("quality analysis failed for %s", game_id)
        return False

    quality_at = datetime.now(timezone.utc).isoformat()
    rm = ResultsManager(base_dir=base_dir)

    try:
        with gm.game_lock(game_id):
            state = gm.load_state(game_id)
            if not state or state.get("status") != "finished" or state.get("result") == "*":
                return False
            if state.get("quality_at") and not force and not state.get("quality_provisional"):
                return False
            _patch_state_quality(
                state,
                quality,
                quality_at,
                map_root=map_root,
                provisional=False,
            )
            gm.save_state(game_id, state)
    except Exception:
        _log.exception("failed to patch state quality for %s", game_id)
        return False

    try:
        _upsert_results_quality(
            rm, game_id, state, quality, quality_at, map_root=map_root
        )
    except Exception:
        _log.exception("failed to upsert results quality for %s", game_id)
        return False
    return True


def _round_accuracy(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    return round(value, 2)


def _play_rating_for_side(
    side: SideQuality, map_root: Optional[Path] = None
) -> Optional[float]:
    from .play_rating import play_rating_for_side

    return play_rating_for_side(side, root=map_root)


def _patch_state_quality(
    state: Dict[str, Any],
    quality: GameQuality,
    quality_at: str,
    *,
    map_root: Optional[Path] = None,
    provisional: bool = False,
    move_count: Optional[int] = None,
) -> None:
    state["quality_depth"] = quality.quality_depth
    state["quality_thin"] = quality.quality_thin
    state["quality_at"] = quality_at

    state["white_accuracy"] = _round_accuracy(quality.white.accuracy)
    state["white_play_rating"] = _play_rating_for_side(quality.white, map_root)
    state["black_accuracy"] = _round_accuracy(quality.black.accuracy)
    state["black_play_rating"] = _play_rating_for_side(quality.black, map_root)

    if state.get("game_type") != GAME_TYPE_AGENT_VS_AGENT:
        agent_color = state.get("agent_color")
        agent_side = quality.white if agent_color == "WHITE" else quality.black
        state["agent_accuracy"] = _round_accuracy(agent_side.accuracy)
        state["agent_play_rating"] = _play_rating_for_side(agent_side, map_root)

    if provisional:
        state["quality_provisional"] = True
        state["quality_move_count"] = (
            move_count if move_count is not None else len(state.get("moves") or [])
        )
    else:
        state.pop("quality_provisional", None)
        state.pop("quality_move_count", None)


def _quality_row_fields(
    side: SideQuality,
    quality: GameQuality,
    quality_at: str,
    *,
    map_root: Optional[Path] = None,
) -> Dict[str, Any]:
    return {
        "accuracy": _round_accuracy(side.accuracy),
        "play_rating": _play_rating_for_side(side, map_root),
        "quality_depth": quality.quality_depth,
        "quality_thin": quality.quality_thin,
        "quality_at": quality_at,
    }


def _upsert_results_quality(
    rm: ResultsManager,
    game_id: str,
    state: Dict[str, Any],
    quality: GameQuality,
    quality_at: str,
    *,
    map_root: Optional[Path] = None,
) -> None:
    if state.get("game_type") == GAME_TYPE_AGENT_VS_AGENT:
        white_id = state["white_model_id"]
        black_id = state["black_model_id"]
        rm.upsert_quality_fields(
            game_id,
            white_id,
            _quality_row_fields(
                quality.white, quality, quality_at, map_root=map_root
            ),
        )
        rm.upsert_quality_fields(
            game_id,
            black_id,
            _quality_row_fields(
                quality.black, quality, quality_at, map_root=map_root
            ),
        )
        return

    model_id = state.get("model_name")
    if not model_id:
        return
    agent_color = state.get("agent_color")
    agent_side = quality.white if agent_color == "WHITE" else quality.black
    rm.upsert_quality_fields(
        game_id,
        model_id,
        _quality_row_fields(agent_side, quality, quality_at, map_root=map_root),
    )
