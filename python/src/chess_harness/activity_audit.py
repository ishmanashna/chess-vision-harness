"""Append-only activity audit for public create/inscribe (no auth)."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .paths import resolve_base_dir

__all__ = [
    "activity_log_path",
    "hash_client_ip",
    "record_activity",
    "tail_activity",
    "print_activity_tail",
]

_UA_MAX = 160


def activity_log_path(base_dir: Optional[str | Path] = None) -> Path:
    root = Path(base_dir) if base_dir else resolve_base_dir()
    return root / "audit" / "activity.jsonl"


def hash_client_ip(ip: str, salt: Optional[str] = None) -> str:
    secret = salt if salt is not None else os.environ.get("CHESS_HARNESS_AUDIT_SALT", "")
    raw = f"{secret}:{ip or 'unknown'}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def record_activity(
    action: str,
    *,
    model_id: Optional[str] = None,
    game_id: Optional[str] = None,
    client_ip: str = "unknown",
    user_agent: str = "",
    base_dir: Optional[str | Path] = None,
) -> Path:
    """Append one JSON line. Never raises to callers — best-effort."""
    path = activity_log_path(base_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    ua = (user_agent or "").replace("\n", " ").strip()[:_UA_MAX]
    row: Dict[str, Any] = {
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
        "action": action,
        "ip_hash": hash_client_ip(client_ip),
        "user_agent": ua,
    }
    if model_id:
        row["model_id"] = model_id
    if game_id:
        row["game_id"] = game_id
    line = json.dumps(row, ensure_ascii=False) + "\n"
    with path.open("a", encoding="utf-8") as fh:
        fh.write(line)
    return path


def tail_activity(n: int = 50, *, base_dir: Optional[str | Path] = None) -> List[Dict[str, Any]]:
    path = activity_log_path(base_dir)
    if not path.exists() or n <= 0:
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    out: List[Dict[str, Any]] = []
    for line in lines[-n:]:
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def print_activity_tail(n: int = 50, *, base_dir: Optional[str | Path] = None) -> None:
    rows = tail_activity(n, base_dir=base_dir)
    if not rows:
        print("(no activity yet — .chess_harness/audit/activity.jsonl)")
        return
    for row in rows:
        print(json.dumps(row, ensure_ascii=False))
