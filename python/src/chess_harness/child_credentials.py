"""Side-scoped child credentials for parent orchestration (/api/v1).

Each credential binds a game_id, side, model_id, and an enumerated subscope
(status | board | board.txt | move | resign | pgn). Credentials are minted
before the orchestrated game is created so their fingerprints can be bound to
game sides at creation time. They expire at game end (revoked) and are capped
by an operator-tunable TTL. Separate from the permanent model-scoped
ApiKeyStore.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import filelock

from .paths import resolve_child_credentials_file

__all__ = [
    "CHILD_CREDENTIAL_SCOPES",
    "CHILD_CREDENTIAL_TTL_ENV",
    "DEFAULT_CHILD_CREDENTIAL_TTL_SEC",
    "ChildCredentialError",
    "ChildCredentialStore",
    "child_credential_ttl_sec",
]

# Enumerated subscope granted to a child credential. Imagine is intentionally
# absent: children only act on the bound game.
CHILD_CREDENTIAL_SCOPES = ("status", "board", "board.txt", "move", "resign", "pgn")

CHILD_CREDENTIAL_TTL_ENV = "CHESS_HARNESS_CHILD_KEY_TTL_SEC"
DEFAULT_CHILD_CREDENTIAL_TTL_SEC = 86400


def child_credential_ttl_sec() -> int:
    """Operator-tunable cap on child credential lifetime in seconds."""
    try:
        return max(300, int(os.environ.get(CHILD_CREDENTIAL_TTL_ENV, "")))
    except (TypeError, ValueError):
        return DEFAULT_CHILD_CREDENTIAL_TTL_SEC


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


class ChildCredentialError(Exception):
    """Rejection carrying an HTTP status for the API layer."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


class ChildCredentialStore:
    """Side-scoped child credentials with atomic JSON persistence.

    Mirrors ApiKeyStore's temp-file + fsync + os.replace write pattern. Keys
    are hashed; the raw key is returned exactly once at mint time.
    """

    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path) if path else resolve_child_credentials_file()
        self._data = self._load()

    def _load(self) -> Dict[str, Any]:
        if not self.path.exists():
            return {"credentials": []}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Child credential store is unreadable: {self.path}") from exc
        if not isinstance(data, dict) or not isinstance(data.get("credentials"), list):
            raise RuntimeError(f"Child credential store has invalid schema: {self.path}")
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

    def mint(
        self,
        game_id: str,
        side: str,
        model_id: str,
        scopes: Optional[tuple] = None,
    ) -> Dict[str, Any]:
        """Mint a credential before game creation; returns public record + raw key."""
        raw = secrets.token_urlsafe(32)
        record = {
            "credential_id": f"cred-{secrets.token_hex(4)}",
            "game_id": game_id,
            "side": str(side).upper(),
            "model_id": model_id,
            "scopes": list(scopes or CHILD_CREDENTIAL_SCOPES),
            "key_hash": hashlib.sha256(raw.encode()).hexdigest(),
            "key_prefix": raw[:8],
            "created_at": _now().isoformat(),
            "expires_at": (_now() + timedelta(seconds=child_credential_ttl_sec())).isoformat(),
            "revoked": False,
        }
        with self._locked():
            data = self._load()
            data.setdefault("credentials", []).append(record)
            self._save(data)
            self._data = data
        return {**self._public(record), "key": raw}

    def verify(self, raw_key: str) -> Optional[Dict[str, Any]]:
        """Resolve a raw key to its public record, or None if invalid/revoked."""
        if not raw_key:
            return None
        digest = hashlib.sha256(raw_key.encode()).hexdigest()
        for entry in self._data.get("credentials", []):
            if not secrets.compare_digest(entry.get("key_hash", ""), digest):
                continue
            if entry.get("revoked"):
                return None
            expires = _parse_iso(entry.get("expires_at"))
            if expires is not None and expires < _now():
                return None
            return self._public(entry)
        return None

    def get(self, credential_id: str) -> Optional[Dict[str, Any]]:
        for entry in self._data.get("credentials", []):
            if entry.get("credential_id") == credential_id and not entry.get("revoked"):
                return self._public(entry)
        return None

    def list_for_game(self, game_id: str) -> List[Dict[str, Any]]:
        return [
            self._public(entry)
            for entry in self._data.get("credentials", [])
            if entry.get("game_id") == game_id and not entry.get("revoked")
        ]

    def revoke_game(self, game_id: str) -> int:
        """Expire every credential bound to a game (game end). Returns count."""
        revoked = 0
        with self._locked():
            data = self._load()
            for entry in data.get("credentials", []):
                if entry.get("game_id") == game_id and not entry.get("revoked"):
                    entry["revoked"] = True
                    revoked += 1
            if revoked:
                self._save(data)
                self._data = data
        return revoked

    @staticmethod
    def _public(entry: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "credential_id": entry.get("credential_id"),
            "game_id": entry.get("game_id"),
            "side": entry.get("side"),
            "model_id": entry.get("model_id"),
            "scopes": list(entry.get("scopes", [])),
            "created_at": entry.get("created_at"),
            "expires_at": entry.get("expires_at"),
        }

    def _locked(self) -> filelock.FileLock:
        return filelock.FileLock(str(self.path) + ".lock", timeout=30)
