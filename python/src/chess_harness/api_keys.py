"""API key persistence for public agent HTTP access."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import filelock

from .paths import resolve_base_dir

__all__ = ["ApiKeyStore"]


class ApiKeyStore:
    """Stores hashed API keys tied to inscribed model ids."""

    def __init__(self, path: Optional[Path] = None):
        self.path = path or resolve_base_dir() / "api_keys.json"
        self._data = self._load()

    def _load(self) -> Dict[str, Any]:
        if not self.path.exists():
            return {"keys": []}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"API key store is unreadable: {self.path}") from exc
        if not isinstance(data, dict) or not isinstance(data.get("keys"), list):
            raise RuntimeError(f"API key store has invalid schema: {self.path}")
        return data

    def _save(self, data: Dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=f"{self.path.name}.", dir=self.path.parent)
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

    def create(self, model_id: str) -> str:
        """Create a key for model_id; return raw key once (never stored)."""
        lock = filelock.FileLock(str(self.path) + ".lock", timeout=30)
        with lock:
            data = self._load()
            raw = secrets.token_urlsafe(32)
            data["keys"].append(
                {
                    "model_id": model_id,
                    "key_hash": hashlib.sha256(raw.encode()).hexdigest(),
                    "key_prefix": raw[:8],
                    "created": datetime.now(timezone.utc).isoformat(),
                }
            )
            self._save(data)
            self._data = data
            return raw

    def verify(self, raw_key: str) -> Optional[str]:
        if not raw_key:
            return None
        digest = hashlib.sha256(raw_key.encode()).hexdigest()
        for entry in self._data.get("keys", []):
            if hmac.compare_digest(entry.get("key_hash", ""), digest):
                return entry.get("model_id")
        return None

    def list_for_model(self, model_id: str) -> List[Dict[str, Any]]:
        return [e for e in self._data.get("keys", []) if e.get("model_id") == model_id]
