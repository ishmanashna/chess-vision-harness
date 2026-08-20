"""Persisted resume queue for the headless agent HTTP client."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from ..paths import resolve_base_dir

__all__ = [
    "QueueEntry",
    "default_queue_path",
    "load_queue",
    "save_queue",
    "enqueue",
    "reconcile_queue",
]


@dataclass(frozen=True)
class QueueEntry:
    game_id: str
    model_id: str

    def to_dict(self) -> Dict[str, str]:
        return {"game_id": self.game_id, "model_id": self.model_id}

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> Optional["QueueEntry"]:
        game_id = str(raw.get("game_id") or "").strip()
        model_id = str(raw.get("model_id") or "").strip()
        if not game_id or not model_id:
            return None
        return cls(game_id=game_id, model_id=model_id)


def default_queue_path(base_dir: Optional[Path] = None) -> Path:
    root = base_dir or resolve_base_dir()
    return root / "runner" / "queue.json"


def load_queue(path: Optional[Path] = None) -> List[QueueEntry]:
    queue_path = path or default_queue_path()
    if not queue_path.is_file():
        return []
    try:
        payload = json.loads(queue_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(payload, list):
        return []
    entries: List[QueueEntry] = []
    for item in payload:
        if isinstance(item, dict):
            entry = QueueEntry.from_dict(item)
            if entry is not None:
                entries.append(entry)
    return entries


def save_queue(entries: Iterable[QueueEntry], path: Optional[Path] = None) -> Path:
    queue_path = path or default_queue_path()
    queue_path.parent.mkdir(parents=True, exist_ok=True)
    data = [entry.to_dict() for entry in entries]
    queue_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return queue_path


def enqueue(
    game_id: str,
    model_id: str,
    *,
    path: Optional[Path] = None,
) -> List[QueueEntry]:
    entries = load_queue(path)
    filtered = [entry for entry in entries if entry.game_id != game_id]
    filtered.append(QueueEntry(game_id=game_id, model_id=model_id))
    save_queue(filtered, path)
    return filtered


def reconcile_queue(
    entries: Iterable[QueueEntry],
    server_games: Iterable[Dict[str, Any]],
) -> List[QueueEntry]:
    """Drop queue rows that are no longer in-progress on the server."""
    live_ids = {
        str(row.get("game_id"))
        for row in server_games
        if row.get("game_id") and not row.get("game_over")
    }
    kept = [entry for entry in entries if entry.game_id in live_ids]
    return kept
