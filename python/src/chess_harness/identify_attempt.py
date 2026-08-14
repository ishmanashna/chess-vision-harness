"""Board-identification attempt store (atomic JSON, separate from games).

Board-identification is a vision-only task: the agent receives a board PNG and
answers with a deterministic placement map of occupied squares. Attempts are
not games — they live in their own store (``$CHESS_HARNESS_DIR/
identify_attempts.json``), never appear in ``results.jsonl``, and never count
against game, move, or puzzle caps.

The record holds the correct placement and the position's provenance and
difficulty; this module never renders them — the API layer keeps those fields
private until the answer is submitted.
"""

from __future__ import annotations

import json
import os
import secrets
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import filelock

from .paths import resolve_identify_attempts_file
from .puzzle_attempt import session_exclude_sec

__all__ = ["IdentifyAttemptStore"]

DATA_VERSION = 1


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class IdentifyAttemptStore:
    """Atomic JSON store for board-identification attempts."""

    def __init__(self, path: Optional[Path] = None):
        self.path = path or resolve_identify_attempts_file()
        self._lock = filelock.FileLock(str(self.path) + ".lock", timeout=30)

    def _load(self) -> Dict[str, Any]:
        if not self.path.exists():
            return {"version": DATA_VERSION, "attempts": {}}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"version": DATA_VERSION, "attempts": {}}
        if not isinstance(data, dict) or not isinstance(data.get("attempts"), dict):
            return {"version": DATA_VERSION, "attempts": {}}
        return data

    def _save(self, data: Dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(
            prefix=f"{self.path.name}.", dir=self.path.parent
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(data, stream, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp_name, self.path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)

    def create(
        self,
        *,
        puzzle_id: str,
        key_fingerprint: str,
        model_id: str,
        rating_min: Optional[int],
        rating_max: Optional[int],
        corpus_fen: str,
        correct_pieces: Dict[str, str],
        puzzle_rating: int,
    ) -> Dict[str, Any]:
        now = _now()
        attempt: Dict[str, Any] = {
            "attempt_id": f"bi-{secrets.token_urlsafe(16)}",
            "puzzle_id": puzzle_id,
            "key_fingerprint": key_fingerprint,
            "model_id": model_id,
            "status": "active",
            "result": None,
            "failure_reason": None,
            "rating_min": rating_min,
            "rating_max": rating_max,
            "corpus_fen": corpus_fen,
            "correct_pieces": dict(correct_pieces),
            "puzzle_rating": puzzle_rating,
            "submitted_pieces": None,
            "score": None,
            "per_square": None,
            "submitted_at": None,
            "started_at": now,
            "updated_at": now,
            "finished_at": None,
        }
        with self._lock:
            data = self._load()
            data["attempts"][attempt["attempt_id"]] = attempt
            self._save(data)
        return dict(attempt)

    def get(self, attempt_id: str) -> Optional[Dict[str, Any]]:
        data = self._load()
        record = data["attempts"].get(attempt_id)
        return dict(record) if record else None

    def update(
        self, attempt_id: str, fn: Callable[[Dict[str, Any]], None]
    ) -> Optional[Dict[str, Any]]:
        """Mutate and persist under the store lock; returns the new record."""
        with self._lock:
            data = self._load()
            record = data["attempts"].get(attempt_id)
            if record is None:
                return None
            fn(record)
            self._save(data)
        return dict(record)

    def active_count(self, key_fingerprint: str) -> int:
        data = self._load()
        return sum(
            1
            for record in data["attempts"].values()
            if record.get("key_fingerprint") == key_fingerprint
            and record.get("status") == "active"
        )

    def list_records(self) -> List[Dict[str, Any]]:
        """All identification attempt records (public browse filters and sorts)."""
        return list(self._load()["attempts"].values())

    def prune_idle_active(self, idle_sec: float) -> List[str]:
        """Abandon active attempts idle longer than ``idle_sec``; returns attempt ids."""
        if idle_sec <= 0:
            return []
        now = datetime.now(timezone.utc).timestamp()
        abandoned: List[str] = []

        def _mutate(data: Dict[str, Any]) -> None:
            for attempt_id, record in data["attempts"].items():
                if record.get("status") != "active":
                    continue
                stamp = record.get("updated_at") or record.get("started_at")
                if not stamp:
                    continue
                try:
                    age = now - datetime.fromisoformat(stamp).timestamp()
                except ValueError:
                    continue
                if age < idle_sec:
                    continue
                record["status"] = "abandoned"
                record["finished_at"] = _now()
                record["updated_at"] = record["finished_at"]
                abandoned.append(str(attempt_id))

        with self._lock:
            data = self._load()
            _mutate(data)
            if abandoned:
                self._save(data)
        return abandoned

    def recent_puzzle_ids(
        self, key_fingerprint: str, window_sec: float
    ) -> set[str]:
        """Puzzle ids the key attempted recently (re-selection avoidance)."""
        now = datetime.now(timezone.utc).timestamp()
        recent: set[str] = set()
        for record in self._load()["attempts"].values():
            if record.get("key_fingerprint") != key_fingerprint:
                continue
            started = record.get("started_at")
            if not started:
                continue
            try:
                started_ts = datetime.fromisoformat(started).timestamp()
            except ValueError:
                continue
            if now - started_ts <= window_sec:
                recent.add(str(record.get("puzzle_id") or ""))
        return recent