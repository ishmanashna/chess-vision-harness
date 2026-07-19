"""API key persistence for public agent HTTP access."""

from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

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
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"keys": []}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._data, indent=2) + "\n", encoding="utf-8")

    def create(self, model_id: str) -> str:
        """Create a key for model_id; return raw key once (never stored)."""
        raw = secrets.token_urlsafe(32)
        entry = {
            "model_id": model_id,
            "key_hash": hashlib.sha256(raw.encode()).hexdigest(),
            "key_prefix": raw[:8],
            "created": datetime.now(timezone.utc).isoformat(),
        }
        self._data.setdefault("keys", []).append(entry)
        self._save()
        return raw

    def verify(self, raw_key: str) -> Optional[str]:
        if not raw_key:
            return None
        digest = hashlib.sha256(raw_key.encode()).hexdigest()
        for entry in self._data.get("keys", []):
            if entry.get("key_hash") == digest:
                return entry.get("model_id")
        return None

    def list_for_model(self, model_id: str) -> List[Dict[str, Any]]:
        return [e for e in self._data.get("keys", []) if e.get("model_id") == model_id]
