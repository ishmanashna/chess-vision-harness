"""Persist per-slot probe results."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from .paths import probe_status_path


def load_probe_status(path: Path | None = None) -> Dict[str, Dict[str, Any]]:
    probe_file = path or probe_status_path()
    if not probe_file.is_file():
        return {}
    try:
        payload = json.loads(probe_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def save_probe_status(status: Dict[str, Dict[str, Any]], path: Path | None = None) -> Path:
    probe_file = path or probe_status_path()
    probe_file.parent.mkdir(parents=True, exist_ok=True)
    probe_file.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
    return probe_file


def mark_probe(
    inscribed_id: str,
    *,
    ok: bool,
    message: str = "",
    path: Path | None = None,
) -> None:
    status = load_probe_status(path)
    status[inscribed_id] = {
        "ok": ok,
        "message": message,
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    save_probe_status(status, path)
