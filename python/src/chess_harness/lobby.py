"""Agent-vs-agent waiting lobbies (find-or-create matchmaking)."""

from __future__ import annotations

import json
import random
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

import filelock

from .paths import resolve_base_dir

__all__ = ["LobbyStore", "ELO_BAND", "LOBBY_TTL_SEC", "assign_colors"]

ELO_BAND = 600
LOBBY_TTL_SEC = 1800  # align with idle timeout default
_LOCK_TIMEOUT = 30


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _now_ts() -> float:
    return time.time()


class LobbyStore:
    """File-backed waiting slots under ``.chess_harness/lobbies.json``."""

    def __init__(self, path: Optional[Path] = None):
        self.path = path or resolve_base_dir() / "lobbies.json"
        self._data = self._load()

    @contextmanager
    def _store_lock(self) -> Iterator[None]:
        lock_path = self.path.with_suffix(self.path.suffix + ".lock")
        lock = filelock.FileLock(lock_path, timeout=_LOCK_TIMEOUT)
        lock.acquire()
        try:
            yield
        finally:
            if lock.is_locked:
                lock.release()

    def _load(self) -> Dict[str, Any]:
        if not self.path.exists():
            return {"lobbies": []}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"lobbies": []}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._data, indent=2) + "\n", encoding="utf-8")

    def _lobbies(self) -> List[Dict[str, Any]]:
        return list(self._data.setdefault("lobbies", []))

    def _prune_stale_unlocked(self, now: Optional[float] = None) -> int:
        now = _now_ts() if now is None else now
        before = self._lobbies()
        kept = [
            lob
            for lob in before
            if now - float(lob.get("created_ts") or 0) < LOBBY_TTL_SEC
        ]
        removed = len(before) - len(kept)
        if removed:
            self._data["lobbies"] = kept
        return removed

    def prune_stale(self, now: Optional[float] = None) -> int:
        with self._store_lock():
            self._data = self._load()
            removed = self._prune_stale_unlocked(now)
            if removed:
                self._save()
            return removed

    def list_waiting(self) -> List[Dict[str, Any]]:
        with self._store_lock():
            self._data = self._load()
            self._prune_stale_unlocked()
            return [lob for lob in self._lobbies() if lob.get("status") == "waiting"]

    def get(self, lobby_id: str) -> Optional[Dict[str, Any]]:
        with self._store_lock():
            self._data = self._load()
            self._prune_stale_unlocked()
            for lob in self._lobbies():
                if lob.get("lobby_id") == lobby_id:
                    return lob
        return None

    def find_waiting_for_model(self, model_id: str) -> Optional[Dict[str, Any]]:
        """Oldest waiting lobby hosted by ``model_id``, if any."""
        with self._store_lock():
            self._data = self._load()
            self._prune_stale_unlocked()
            candidates = [
                lob
                for lob in self._lobbies()
                if lob.get("status") == "waiting" and lob.get("host_model_id") == model_id
            ]
            if not candidates:
                return None
            candidates.sort(key=lambda lob: float(lob.get("created_ts") or 0))
            return candidates[0]

    def create_waiting(
        self,
        *,
        host_model_id: str,
        host_display_name: str,
        host_elo: int,
    ) -> Dict[str, Any]:
        with self._store_lock():
            self._data = self._load()
            self._prune_stale_unlocked()
            lob = {
                "lobby_id": f"lobby-{uuid.uuid4().hex[:12]}",
                "status": "waiting",
                "host_model_id": host_model_id,
                "host_display_name": host_display_name,
                "host_elo": int(host_elo),
                "created": _now_iso(),
                "created_ts": _now_ts(),
                "game_id": None,
                "white_model_id": None,
                "black_model_id": None,
            }
            self._data.setdefault("lobbies", []).append(lob)
            self._save()
            return lob

    def cancel(self, lobby_id: str, host_model_id: str) -> bool:
        with self._store_lock():
            self._data = self._load()
            for lob in self._lobbies():
                if lob.get("lobby_id") != lobby_id:
                    continue
                if lob.get("host_model_id") != host_model_id:
                    return False
                if lob.get("status") != "waiting":
                    return False
                lob["status"] = "cancelled"
                self._save()
                return True
        return False

    def find_matchable(
        self, joiner_model_id: str, joiner_elo: int
    ) -> Optional[Dict[str, Any]]:
        """Oldest waiting lobby within Elo band, not hosted by joiner."""
        with self._store_lock():
            self._data = self._load()
            self._prune_stale_unlocked()
            candidates = []
            for lob in self._lobbies():
                if lob.get("status") != "waiting":
                    continue
                if lob.get("host_model_id") == joiner_model_id:
                    continue
                host_elo = int(lob.get("host_elo") or 0)
                if abs(host_elo - int(joiner_elo)) > ELO_BAND:
                    continue
                candidates.append(lob)
            if not candidates:
                return None
            candidates.sort(key=lambda lob: float(lob.get("created_ts") or 0))
            return candidates[0]

    def claim_join(
        self,
        lobby_id: str,
        *,
        joiner_model_id: str,
        white_model_id: str,
        black_model_id: str,
    ) -> Optional[Dict[str, Any]]:
        """Atomically seize a waiting lobby before the joiner creates a game.

        Only the winner of a concurrent race moves the lobby to ``claiming``;
        losers receive None and must not attempt to create a game. The winner
        creates the game, then calls :meth:`finalize_claim` to bind the new
        game id, or :meth:`release_claim` if creation failed.
        """
        with self._store_lock():
            self._data = self._load()
            self._prune_stale_unlocked()
            for lob in self._lobbies():
                if lob.get("lobby_id") != lobby_id:
                    continue
                if lob.get("status") != "waiting":
                    return None
                if lob.get("host_model_id") == joiner_model_id:
                    return None
                lob["status"] = "claiming"
                lob["claimant"] = joiner_model_id
                lob["white_model_id"] = white_model_id
                lob["black_model_id"] = black_model_id
                self._save()
                return lob
        return None

    def finalize_claim(
        self, lobby_id: str, *, game_id: str
    ) -> Optional[Dict[str, Any]]:
        """Bind a claimed lobby to its newly created game."""
        with self._store_lock():
            self._data = self._load()
            for lob in self._lobbies():
                if lob.get("lobby_id") != lobby_id or lob.get("status") != "claiming":
                    continue
                lob["status"] = "matched"
                lob["game_id"] = game_id
                lob["matched_at"] = _now_iso()
                lob.pop("claimant", None)
                self._save()
                return lob
        return None

    def release_claim(self, lobby_id: str, *, joiner_model_id: str) -> bool:
        """Return a claimed lobby to waiting when game creation failed."""
        with self._store_lock():
            self._data = self._load()
            for lob in self._lobbies():
                if lob.get("lobby_id") != lobby_id or lob.get("status") != "claiming":
                    continue
                if lob.get("claimant") != joiner_model_id:
                    continue
                lob["status"] = "waiting"
                lob["white_model_id"] = None
                lob["black_model_id"] = None
                lob.pop("claimant", None)
                self._save()
                return True
        return False

    def mark_matched(
        self,
        lobby_id: str,
        *,
        game_id: str,
        white_model_id: str,
        black_model_id: str,
    ) -> Optional[Dict[str, Any]]:
        with self._store_lock():
            self._data = self._load()
            for lob in self._lobbies():
                if lob.get("lobby_id") != lobby_id:
                    continue
                if lob.get("status") != "waiting":
                    return None
                lob["status"] = "matched"
                lob["game_id"] = game_id
                lob["white_model_id"] = white_model_id
                lob["black_model_id"] = black_model_id
                lob["matched_at"] = _now_iso()
                self._save()
                return lob
        return None


def assign_colors(host_model_id: str, joiner_model_id: str) -> Dict[str, str]:
    """Randomly assign white/black for a match."""
    if random.choice([True, False]):
        return {"white_model_id": host_model_id, "black_model_id": joiner_model_id}
    return {"white_model_id": joiner_model_id, "black_model_id": host_model_id}
