"""Filtered, deduplicated prompt-pack evidence for the localhost Ops desk."""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .accuracy_elo_map import play_rating_from_accuracy
from .board_controller import BoardController
from .game_manager import GameManager
from .paths import project_root, resolve_base_dir
from .prompt_packs import pack_family, pack_title
from .results import ResultsManager
from .ops_experiment_runs import run_game_links

STATUSES = ("finished", "in_progress", "failed", "abandoned", "excluded", "no_result")
SCORED = {"1-0", "0-1", "1/2-1/2"}


def _number(value):
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _row(game_id, state, result, cal_root):
    data = dict(result)
    data.update({key: value for key, value in state.items() if value is not None})
    pack = str(data.get("prompt_pack") or data.get("prompt_pack_original") or "")
    if not pack:
        return None
    score = state.get("result") if state.get("result") in SCORED else result.get("result")
    excluded = bool(data.get("prompt_test_excluded"))
    raw_status = str(data.get("status") or "")
    if excluded:
        status = "excluded"
    elif score in SCORED:
        status = "finished"
    elif raw_status == "in_progress":
        status = "in_progress"
    elif raw_status == "failed" or data.get("error"):
        status = "failed"
    elif raw_status == "abandoned" or data.get("end_reason") in {"idle_timeout", "timeout", "abandoned"}:
        status = "abandoned"
    else:
        status = "no_result"
    accuracy = _number(data.get("agent_accuracy", data.get("accuracy")))
    performance = play_rating_from_accuracy(accuracy, root=cal_root) if accuracy is not None else None
    metric_reason = None
    if status != "finished":
        metric_reason = "Not a scored, included finish; omitted from pack means."
    elif accuracy is None:
        metric_reason = "Analysis pending or unavailable."
    elif performance is None:
        metric_reason = "Calibration map unavailable."
    return {
        "game_id": game_id, "prompt_pack": pack, "title": pack_title(pack),
        "family": pack_family(pack), "model_id": str(data.get("model_name") or data.get("model_id") or "unknown"),
        "run_id": str(data.get("experiment_run_id") or data.get("run_id") or data.get("prompt_test_run_id") or "legacy-unassigned"),
        "status": status, "result": score if score in SCORED else "*",
        "outcome": BoardController.agent_outcome(data.get("agent_color", ""), score).get("outcome") if score in SCORED else None,
        "agent_color": data.get("agent_color"), "opponent_id": str(data.get("opponent_id") or "unknown"),
        "plies": len(state["moves"]) if "moves" in state else result.get("plies"),
        "accuracy": round(accuracy, 2) if accuracy is not None else None,
        "play_rating": performance, "metric_reason": metric_reason,
        "updated_at": str(data.get("last_activity") or data.get("ts") or ""),
    }


def _chats(root, selected):
    chats = []
    for game in selected:
        path = root / "prompt_test" / game["game_id"] / "thread.json"
        if not path.resolve().is_relative_to((root / "prompt_test").resolve()):
            continue
        try:
            if path.stat().st_size > 2_000_000:
                continue
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        chats.append({"game_id": game["game_id"], "prompt_pack": game["prompt_pack"],
                      "title": game["title"], "status": data.get("status", "open"),
                      "messages": (data.get("messages") or data.get("notes") or [])[-50:]})
    return chats


def _counts(games):
    counts = {status: sum(row["status"] == status for row in games) for status in STATUSES}
    counts["total"] = len(games)
    counts["analysed"] = sum(row["status"] == "finished" and row["accuracy"] is not None for row in games)
    return counts


def build_prompt_test_snapshot(family=None, *, base_dir=None, cal_root=None,
                               run_id=None, model=None, pack=None, opponent=None,
                               status=None, offset=0, limit=100) -> dict[str, Any]:
    """All pack means and counts use exactly the selected, deduplicated games.

    Games are explicitly paginated; totals include every matching game, not just
    the page. Old records without a run ID are descriptive legacy evidence.
    """
    family = family or "composer"
    if family not in {"composer", "jeff", "all"} or (status and status not in STATUSES):
        raise ValueError("Invalid experiment family or status")
    if offset < 0 or not 1 <= limit <= 200:
        raise ValueError("Invalid experiment pagination")
    root = Path(base_dir) if base_dir is not None else resolve_base_dir()
    cal_root = cal_root or project_root() / "elo_calibration" / "results"
    states = {game["game_id"]: game["state"] for game in GameManager(str(root)).list_games()}
    results = {}
    for result in ResultsManager(base_dir=str(root)).load_results():
        gid = result.get("game_id")
        if gid and str(result.get("ts") or "") >= str(results.get(gid, {}).get("ts") or ""):
            results[gid] = result
    rows = []
    for gid in states.keys() | results.keys():
        row = _row(gid, states.get(gid, {}), results.get(gid, {}), cal_root)
        if row and (family == "all" or row["family"] == family):
            rows.append(row)
    rows.sort(key=lambda row: (row["updated_at"], row["game_id"]), reverse=True)
    links = run_game_links()
    for row in rows:
        if row["run_id"] == "legacy-unassigned":
            row["run_id"] = links.get(row["game_id"], "legacy-unassigned")
    mapping = {"run_id": run_id, "model_id": model, "prompt_pack": pack,
               "opponent_id": opponent, "status": status}
    options = {key: sorted({row[key] for row in rows}) for key in mapping}
    selected = [row for row in rows if all(not value or row[key] == value for key, value in mapping.items())]
    packs = []
    for pid in sorted({row["prompt_pack"] for row in selected}):
        games = [row for row in selected if row["prompt_pack"] == pid]
        scored = [row for row in games if row["status"] == "finished"]
        accuracies = [row["accuracy"] for row in scored if row["accuracy"] is not None]
        mean = round(sum(accuracies) / len(accuracies), 2) if accuracies else None
        packs.append({"id": pid, "title": pack_title(pid), "family": pack_family(pid),
                      **_counts(games), "wins": sum(row["outcome"] == "win" for row in scored),
                      "draws": sum(row["outcome"] == "draw" for row in scored),
                      "losses": sum(row["outcome"] == "loss" for row in scored),
                      "mean_accuracy": mean,
                      "mean_play_rating": play_rating_from_accuracy(mean, root=cal_root) if mean is not None else None,
                      "recent_game_ids": [row["game_id"] for row in games[:5]]})
    page = selected[offset:offset + limit]
    return {"ok": True, "generated_at": datetime.now(timezone.utc).isoformat(),
            "family": family, "filters": mapping, "options": options,
            "summary": _counts(selected), "packs": packs, "games": page,
            "chats": _chats(root, page), "total": len(selected), "offset": offset,
            "limit": limit, "has_more": offset + len(page) < len(selected),
            "scope_note": "Descriptive aggregates of matching games, not a controlled study. Legacy/unassigned means no recorded run ID. Chat follows the displayed game page."}
