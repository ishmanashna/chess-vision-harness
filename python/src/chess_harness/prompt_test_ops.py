"""Ops snapshot for local prompt-test pack comparison."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .accuracy_elo_map import play_rating_from_accuracy
from .board_controller import BoardController
from .game_manager import GameManager
from .paths import project_root, resolve_base_dir
from .prompt_packs import is_packed_result_row, is_packed_state, pack_title
from .results import ResultsManager

__all__ = ["build_prompt_test_snapshot"]

_RECENT_GAME_LIMIT = 5


def _parse_ts(ts: Optional[str]) -> float:
    if not ts:
        return 0.0
    try:
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except ValueError:
        return 0.0


@dataclass
class _PackAgg:
    in_progress: int = 0
    finished: int = 0
    wins: int = 0
    draws: int = 0
    losses: int = 0
    accuracy_values: List[float] = field(default_factory=list)
    recent: Dict[str, float] = field(default_factory=dict)


def _mean(values: List[float]) -> Optional[float]:
    if not values:
        return None
    return sum(values) / len(values)


def build_prompt_test_snapshot(
    *,
    base_dir: Optional[Path] = None,
    cal_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Aggregate packed prompt-test games per pack id for the Ops tab.

    mean_play_rating is play_rating_from_accuracy(mean_accuracy) via the current
    accuracy→Elo map — not a mean of per-game stored play_rating.
    """
    root = Path(base_dir) if base_dir is not None else resolve_base_dir()
    if cal_root is None:
        cal_root = project_root() / "elo_calibration" / "results"
    gm = GameManager(str(root))
    rm = ResultsManager(base_dir=str(root))

    by_pack: Dict[str, _PackAgg] = {}

    def bucket(pack_id: str) -> _PackAgg:
        if pack_id not in by_pack:
            by_pack[pack_id] = _PackAgg()
        return by_pack[pack_id]

    for game in gm.list_games(status_filter="in_progress"):
        state = game["state"]
        if not is_packed_state(state):
            continue
        pack_id = str(state["prompt_pack"])
        agg = bucket(pack_id)
        agg.in_progress += 1
        recency = _parse_ts(state.get("last_activity"))
        game_id = game["game_id"]
        agg.recent[game_id] = max(agg.recent.get(game_id, 0.0), recency)

    for row in rm.load_results():
        if not is_packed_result_row(row):
            continue
        pack_id = str(row["prompt_pack"])
        agg = bucket(pack_id)
        result = row.get("result")
        if result and result != "*":
            agg.finished += 1
            agent_color = row.get("agent_color") or ""
            outcome = BoardController.agent_outcome(agent_color, result)
            oc = outcome.get("outcome")
            if oc == "win":
                agg.wins += 1
            elif oc == "draw":
                agg.draws += 1
            elif oc == "loss":
                agg.losses += 1
            accuracy = row.get("accuracy")
            if accuracy is not None:
                agg.accuracy_values.append(float(accuracy))
        game_id = row.get("game_id")
        if game_id:
            recency = _parse_ts(row.get("ts"))
            gid = str(game_id)
            agg.recent[gid] = max(agg.recent.get(gid, 0.0), recency)

    packs: List[Dict[str, Any]] = []
    for pack_id in sorted(by_pack.keys()):
        agg = by_pack[pack_id]
        recent_ids = sorted(
            agg.recent.keys(),
            key=lambda gid: agg.recent[gid],
            reverse=True,
        )[:_RECENT_GAME_LIMIT]
        mean_accuracy = (
            round(_mean(agg.accuracy_values), 2) if agg.accuracy_values else None
        )
        packs.append(
            {
                "id": pack_id,
                "title": pack_title(pack_id),
                "in_progress": agg.in_progress,
                "finished": agg.finished,
                "wins": agg.wins,
                "draws": agg.draws,
                "losses": agg.losses,
                "mean_accuracy": mean_accuracy,
                "mean_play_rating": (
                    play_rating_from_accuracy(mean_accuracy, root=cal_root)
                    if mean_accuracy is not None
                    else None
                ),
                "recent_game_ids": recent_ids,
            }
        )

    return {"ok": True, "packs": packs}
