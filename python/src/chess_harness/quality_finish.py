"""Background post-game quality analysis (Phase 2 harness orchestrator)."""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Set

from .game_manager import GameManager
from .game_quality import GameQuality, SideQuality, analyse_game
from .game_types import GAME_TYPE_AGENT_VS_AGENT
from .results import ResultsManager

_log = logging.getLogger(__name__)

_scheduled: Set[str] = set()
_scheduled_lock = threading.Lock()


def schedule_game_quality(
    game_id: str,
    *,
    base_dir: Optional[str] = None,
    map_root: Optional[Path] = None,
) -> None:
    """Enqueue background quality analysis after PGN is on disk."""
    with _scheduled_lock:
        if game_id in _scheduled:
            return
        _scheduled.add(game_id)
    thread = threading.Thread(
        target=_run_and_clear,
        args=(game_id, base_dir, map_root),
        name=f"quality-{game_id}",
        daemon=True,
    )
    thread.start()


def _run_and_clear(
    game_id: str, base_dir: Optional[str], map_root: Optional[Path]
) -> None:
    try:
        run_game_quality(game_id, base_dir=base_dir, map_root=map_root)
    finally:
        with _scheduled_lock:
            _scheduled.discard(game_id)


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
    if state.get("quality_at") and not force:
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
            if state.get("quality_at") and not force:
                return False
            _patch_state_quality(state, quality, quality_at, map_root=map_root)
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
