"""
Game manager for handling multiple chess games with isolation and locking.
"""

import json
import re
import shutil
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, Optional

import filelock

from .paths import resolve_base_dir


class GameBusyError(Exception):
    """Raised when a game lock cannot be acquired."""


class GameManager:
    """Manages multiple chess games with file-based locking and isolation."""

    LOCK_TIMEOUT = 30

    def __init__(self, base_dir: Optional[str] = None):
        self.base_dir = Path(base_dir) if base_dir else resolve_base_dir()
        self.games_dir = self.base_dir / "games"
        self.results_file = self.base_dir / "results.jsonl"
        self.games_dir.mkdir(parents=True, exist_ok=True)

    def validate_game_id(self, game_id: str) -> bool:
        pattern = r"^[a-zA-Z0-9_-]+$"
        return bool(re.match(pattern, game_id)) and len(game_id) <= 64

    def get_game_dir(self, game_id: str) -> Path:
        if not self.validate_game_id(game_id):
            raise ValueError(f"Invalid game_id: {game_id}")
        return self.games_dir / game_id

    def get_state_path(self, game_id: str) -> Path:
        return self.get_game_dir(game_id) / "state.json"

    def get_lock_path(self, game_id: str) -> Path:
        return self.get_state_path(game_id).with_suffix(".json.lock")

    def get_board_path(self, game_id: str) -> Path:
        return self.get_game_dir(game_id) / "board.png"

    def get_role_board_path(self, game_id: str, color: str) -> Path:
        """Per-agent board PNG (white or black perspective)."""
        suffix = "board_white.png" if color.upper() == "WHITE" else "board_black.png"
        return self.get_game_dir(game_id) / suffix

    def get_pgn_path(self, game_id: str) -> Path:
        return self.get_game_dir(game_id) / "game.pgn"

    @contextmanager
    def game_lock(self, game_id: str) -> Iterator[None]:
        """Acquire exclusive lock for a game_id across load/mutate/save."""
        if not self.validate_game_id(game_id):
            raise ValueError(f"Invalid game_id: {game_id}")
        lock_path = self.get_lock_path(game_id)
        lock = filelock.FileLock(lock_path, timeout=self.LOCK_TIMEOUT)
        try:
            lock.acquire()
            yield
        except filelock.Timeout:
            raise GameBusyError(f"Game {game_id} is busy; retry shortly") from None
        finally:
            if lock.is_locked:
                lock.release()

    def load_state(self, game_id: str) -> Optional[Dict[str, Any]]:
        state_path = self.get_state_path(game_id)
        if not state_path.exists():
            return None
        try:
            with open(state_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return None

    def save_state(self, game_id: str, state: Dict[str, Any]) -> bool:
        state_path = self.get_state_path(game_id)
        game_dir = self.get_game_dir(game_id)
        game_dir.mkdir(parents=True, exist_ok=True)
        try:
            with open(state_path, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2)
            return True
        except OSError:
            return False

    def list_games(self, status_filter: Optional[str] = None) -> list:
        games = []
        if not self.games_dir.exists():
            return games
        for game_dir in self.games_dir.iterdir():
            if game_dir.is_dir():
                state = self.load_state(game_dir.name)
                if state and (status_filter is None or state.get("status") == status_filter):
                    games.append({"game_id": game_dir.name, "state": state})
        games.sort(key=self._game_recency_key, reverse=True)
        return games

    def _game_recency_key(self, game: Dict[str, Any]) -> float:
        """Newest activity first; fall back to state.json mtime."""
        state = game.get("state") or {}
        ts = state.get("last_activity")
        if ts:
            try:
                from datetime import datetime, timezone

                last = datetime.fromisoformat(ts)
                if last.tzinfo is None:
                    last = last.replace(tzinfo=timezone.utc)
                return last.timestamp()
            except ValueError:
                pass
        path = self.get_state_path(game["game_id"])
        try:
            return path.stat().st_mtime if path.exists() else 0.0
        except OSError:
            return 0.0

    def game_exists(self, game_id: str) -> bool:
        return self.get_state_path(game_id).exists()

    def delete_game(self, game_id: str) -> bool:
        if not self.validate_game_id(game_id):
            return False
        game_dir = self.get_game_dir(game_id)
        if not game_dir.exists():
            return False
        shutil.rmtree(game_dir)
        lock_path = self.get_lock_path(game_id)
        if lock_path.exists():
            lock_path.unlink()
        return True
