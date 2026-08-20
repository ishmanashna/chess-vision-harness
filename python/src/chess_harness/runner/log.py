"""JSONL runner log under .chess_harness/runner/."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from .paths import log_path


class RunnerLog:
    def __init__(self, path: Path | None = None):
        self.path = path or log_path()

    def write(
        self,
        event: str,
        *,
        game_id: Optional[str] = None,
        model: Optional[str] = None,
        provider: Optional[str] = None,
        error: Optional[str] = None,
        quota: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> None:
        row: Dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "event": event,
        }
        if game_id:
            row["game_id"] = game_id
        if model:
            row["model"] = model
        if provider:
            row["provider"] = provider
        if error:
            row["error"] = error
        if quota:
            row["quota"] = quota
        if extra:
            row.update(extra)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
