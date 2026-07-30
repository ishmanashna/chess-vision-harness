"""Filesystem contact inbox under ``.chess_harness/inbox/``."""

from __future__ import annotations

import json
import re
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .paths import resolve_base_dir

__all__ = [
    "MAX_SENDER_LEN",
    "MAX_MESSAGE_LEN",
    "inbox_dir",
    "append_message",
    "list_messages",
    "mark_read",
    "delete_message",
    "validate_contact",
]

MAX_SENDER_LEN = 200
MAX_MESSAGE_LEN = 4000
_ID_RE = re.compile(r"^msg-[0-9a-f]{16}$")


def inbox_dir(base_dir: Optional[Path] = None) -> Path:
    root = Path(base_dir) if base_dir is not None else resolve_base_dir()
    return root / "inbox"


def _utc_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _new_id() -> str:
    return f"msg-{secrets.token_hex(8)}"


def _message_path(directory: Path, message_id: str) -> Path:
    if not _ID_RE.match(message_id):
        raise ValueError("Invalid message id")
    return directory / f"{message_id}.json"


def validate_contact(sender: str, message: str) -> Optional[str]:
    sender = (sender or "").strip()
    message = (message or "").strip()
    if not sender:
        return "Sender is required"
    if not message:
        return "Message is required"
    if len(sender) > MAX_SENDER_LEN:
        return f"Sender must be at most {MAX_SENDER_LEN} characters"
    if len(message) > MAX_MESSAGE_LEN:
        return f"Message must be at most {MAX_MESSAGE_LEN} characters"
    return None


def append_message(
    sender: str,
    message: str,
    *,
    base_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    err = validate_contact(sender, message)
    if err:
        return {"ok": False, "error": err}
    directory = inbox_dir(base_dir)
    directory.mkdir(parents=True, exist_ok=True)
    message_id = _new_id()
    row = {
        "id": message_id,
        "created_at": _utc_ts(),
        "sender": sender.strip(),
        "message": message.strip(),
        "read": False,
    }
    path = _message_path(directory, message_id)
    path.write_text(json.dumps(row, indent=2) + "\n", encoding="utf-8")
    return {"ok": True, "message": row}


def list_messages(*, base_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
    directory = inbox_dir(base_dir)
    if not directory.is_dir():
        return []
    rows: List[Dict[str, Any]] = []
    for path in directory.glob("msg-*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict) or data.get("id") != path.stem:
            continue
        rows.append(data)
    rows.sort(key=lambda r: str(r.get("created_at") or ""), reverse=True)
    return rows


def mark_read(message_id: str, *, base_dir: Optional[Path] = None) -> Dict[str, Any]:
    try:
        path = _message_path(inbox_dir(base_dir), message_id)
    except ValueError:
        return {"ok": False, "error": "Invalid message id"}
    if not path.is_file():
        return {"ok": False, "error": "Message not found"}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"ok": False, "error": "Message not found"}
    data["read"] = True
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return {"ok": True, "message": data}


def delete_message(message_id: str, *, base_dir: Optional[Path] = None) -> Dict[str, Any]:
    try:
        path = _message_path(inbox_dir(base_dir), message_id)
    except ValueError:
        return {"ok": False, "error": "Invalid message id"}
    if not path.is_file():
        return {"ok": False, "error": "Message not found"}
    try:
        path.unlink()
    except OSError:
        return {"ok": False, "error": "Could not delete message"}
    return {"ok": True, "id": message_id}
