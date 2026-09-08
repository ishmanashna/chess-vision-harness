"""Ops snapshot for local prompt-test pack comparison."""

from __future__ import annotations

import json
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
_GAME_LIST_LIMIT = 40


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


def _mapped_play_rating(
    accuracy: Optional[float], cal_root: Optional[Path]
) -> Optional[float]:
    if accuracy is None:
        return None
    return play_rating_from_accuracy(float(accuracy), root=cal_root)


def _merge_game_row(
    games_by_id: Dict[str, Dict[str, Any]],
    game_id: str,
    *,
    pack_id: str,
    recency: float,
    status: str,
    result: Optional[str] = None,
    agent_color: Optional[str] = None,
    opponent_id: Optional[str] = None,
    plies: Optional[int] = None,
    accuracy: Optional[float] = None,
    cal_root: Optional[Path] = None,
) -> None:
    existing = games_by_id.get(game_id) or {}
    outcome = None
    if result and result != "*" and agent_color:
        outcome = BoardController.agent_outcome(agent_color, result).get("outcome")
    play_rating = _mapped_play_rating(accuracy, cal_root)
    merged = {
        "game_id": game_id,
        "prompt_pack": pack_id,
        "title": pack_title(pack_id),
        "status": status or existing.get("status") or "unknown",
        "result": result if result is not None else existing.get("result"),
        "outcome": outcome or existing.get("outcome"),
        "agent_color": agent_color or existing.get("agent_color"),
        "opponent_id": opponent_id or existing.get("opponent_id"),
        "plies": plies if plies is not None else existing.get("plies"),
        "accuracy": (
            round(float(accuracy), 2) if accuracy is not None else existing.get("accuracy")
        ),
        "play_rating": (
            play_rating if play_rating is not None else existing.get("play_rating")
        ),
        "_recency": max(float(existing.get("_recency") or 0.0), recency),
    }
    if existing.get("status") == "in_progress":
        merged["status"] = "in_progress"
    games_by_id[game_id] = merged


def _load_committee_chats(
    root: Path, games_by_id: Dict[str, Dict[str, Any]]
) -> List[Dict[str, Any]]:
    chats: List[Dict[str, Any]] = []
    prompt_root = root / "prompt_test"
    if not prompt_root.is_dir():
        return chats
    for game_dir in prompt_root.iterdir():
        if not game_dir.is_dir():
            continue
        thread_path = game_dir / "thread.json"
        if not thread_path.is_file():
            continue
        try:
            data = json.loads(thread_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        messages = data.get("messages") or data.get("notes") or []
        game_id = game_dir.name
        info = games_by_id.get(game_id) or {}
        chats.append(
            {
                "game_id": game_id,
                "prompt_pack": info.get("prompt_pack"),
                "title": info.get("title") or game_id,
                "turn": int(data.get("turn") or data.get("ply") or 0),
                "status": data.get("status") or "open",
                "messages": messages,
                "votes": data.get("votes") or [],
            }
        )
    chats.sort(key=lambda row: row.get("game_id") or "")
    return chats


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
    games_by_id: Dict[str, Dict[str, Any]] = {}

    def bucket(pack_id: str) -> _PackAgg:
        if pack_id not in by_pack:
            by_pack[pack_id] = _PackAgg()
        return by_pack[pack_id]

    for game in gm.list_games():
        state = game["state"]
        if not is_packed_state(state):
            continue
        pack_id = str(state["prompt_pack"])
        agg = bucket(pack_id)
        recency = _parse_ts(state.get("last_activity"))
        game_id = game["game_id"]
        agg.recent[game_id] = max(agg.recent.get(game_id, 0.0), recency)
        status = str(state.get("status") or "unknown")
        if status == "in_progress":
            agg.in_progress += 1
        accuracy = state.get("agent_accuracy")
        _merge_game_row(
            games_by_id,
            game_id,
            pack_id=pack_id,
            recency=recency,
            status=status,
            result=state.get("result"),
            agent_color=state.get("agent_color"),
            opponent_id=state.get("opponent_id"),
            plies=len(state.get("moves") or []),
            accuracy=float(accuracy) if accuracy is not None else None,
            cal_root=cal_root,
        )

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
            _merge_game_row(
                games_by_id,
                gid,
                pack_id=pack_id,
                recency=recency,
                status="finished" if result and result != "*" else "unknown",
                result=result,
                agent_color=row.get("agent_color"),
                opponent_id=row.get("opponent_id"),
                plies=row.get("plies"),
                accuracy=float(row["accuracy"]) if row.get("accuracy") is not None else None,
                cal_root=cal_root,
            )

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

    games = list(games_by_id.values())
    games.sort(key=lambda row: float(row.get("_recency") or 0.0), reverse=True)
    public_games: List[Dict[str, Any]] = []
    for row in games[:_GAME_LIST_LIMIT]:
        public_games.append({k: v for k, v in row.items() if not k.startswith("_")})

    chats = _load_committee_chats(root, games_by_id)

    return {"ok": True, "packs": packs, "games": public_games, "chats": chats}
