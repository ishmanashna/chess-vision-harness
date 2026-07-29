"""Append-only chat for human-vs-agent games (chat.jsonl + chat_seq)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from .game_types import is_human_vs_agent_state

if TYPE_CHECKING:
    from .game_manager import GameManager

__all__ = [
    "MAX_CHAT_TEXT",
    "append_chat_message",
    "chat_path",
    "read_chat_messages",
]

MAX_CHAT_TEXT = 500
_RATE_WINDOW_SEC = 60.0
_RATE_MAX_PER_WINDOW = 30
_MIN_INTERVAL_SEC = 1.0
_TAIL_SCAN = 80


def chat_path(gm: "GameManager", game_id: str) -> Path:
    return gm.get_game_dir(game_id) / "chat.jsonl"


def _utc_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _parse_ts(ts: str) -> Optional[float]:
    try:
        if ts.endswith("Z"):
            ts = ts[:-1] + "+00:00"
        return datetime.fromisoformat(ts).timestamp()
    except ValueError:
        return None


def _tail_rows(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    rows: List[Dict[str, Any]] = []
    for line in lines[-_TAIL_SCAN:]:
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def _rate_limit_error(path: Path, principal: str) -> Optional[str]:
    now = datetime.now(timezone.utc).timestamp()
    recent = [r for r in _tail_rows(path) if r.get("from") == principal]
    if not recent:
        return None
    last = recent[-1]
    last_ts = _parse_ts(str(last.get("ts", "")))
    if last_ts is not None and now - last_ts < _MIN_INTERVAL_SEC:
        return "Please wait before sending another message"
    cutoff = now - _RATE_WINDOW_SEC
    count = 0
    for row in recent:
        ts = _parse_ts(str(row.get("ts", "")))
        if ts is not None and ts >= cutoff:
            count += 1
    if count >= _RATE_MAX_PER_WINDOW:
        return "Chat rate limit exceeded; try again shortly"
    return None


def _sender_fields(state: Dict[str, Any], from_kind: str) -> tuple[str, Optional[str]]:
    if from_kind == "human":
        label = state.get("human_nickname") or "Human"
        color = state.get("human_color")
    else:
        label = state.get("model_display_name") or state.get("model_name") or "Agent"
        color = state.get("agent_color")
    return str(label), color


def append_chat_message(
    gm: "GameManager",
    game_id: str,
    *,
    from_kind: str,
    text: str,
) -> Dict[str, Any]:
    from .game_manager import GameBusyError

    cleaned = (text or "").strip()
    if not cleaned:
        return {"ok": False, "error": "Message cannot be empty"}
    if len(cleaned) > MAX_CHAT_TEXT:
        return {"ok": False, "error": f"Message too long (max {MAX_CHAT_TEXT} characters)"}
    if from_kind not in ("human", "agent"):
        return {"ok": False, "error": "Invalid sender"}

    path = chat_path(gm, game_id)
    rate_err = _rate_limit_error(path, from_kind)
    if rate_err:
        return {"ok": False, "error": rate_err}

    try:
        with gm.game_lock(game_id):
            state = gm.load_state(game_id)
            if not state or not is_human_vs_agent_state(state):
                return {"ok": False, "error": f"Game {game_id} not found"}

            rate_err = _rate_limit_error(path, from_kind)
            if rate_err:
                return {"ok": False, "error": rate_err}

            seq = int(state.get("chat_seq") or 0) + 1
            from_label, from_color = _sender_fields(state, from_kind)
            row = {
                "seq": seq,
                "ts": _utc_ts(),
                "from": from_kind,
                "from_color": from_color,
                "from_label": from_label,
                "text": cleaned,
            }
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "a", encoding="utf-8") as handle:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            state["chat_seq"] = seq
            if not gm.save_state(game_id, state):
                return {"ok": False, "error": "Failed to save game state"}
            return {"ok": True, "message": row, "chat_seq": seq}
    except GameBusyError as exc:
        return {"ok": False, "error": str(exc)}


def read_chat_messages(
    gm: "GameManager", game_id: str, since: int = 0
) -> Dict[str, Any]:
    state = gm.load_state(game_id)
    if not state or not is_human_vs_agent_state(state):
        return {"ok": False, "error": f"Game {game_id} not found"}

    since = max(0, int(since))
    path = chat_path(gm, game_id)
    latest = int(state.get("chat_seq") or 0)
    messages: List[Dict[str, Any]] = []
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if int(row.get("seq", 0)) > since:
                        messages.append(row)
        except OSError:
            return {"ok": False, "error": "Failed to read chat"}
    return {"ok": True, "messages": messages, "chat_seq": latest}
