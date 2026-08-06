"""Approval-gated follow-up game requests (requested -> approved -> used).

The harness never creates a follow-up game until an operator explicitly
approves. Approval state lives in a small JSON store under CHESS_HARNESS_DIR,
never inside game state files or the finished-games SQLite.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import filelock

from .paths import resolve_followup_approvals_file

__all__ = [
    "DEFAULT_FOLLOWUP_APPROVAL_TTL_SEC",
    "FOLLOWUP_APPROVAL_TTL_ENV",
    "FollowupApprovalError",
    "FollowupApprovalStore",
    "followup_approval_ttl_sec",
]

FOLLOWUP_APPROVAL_TTL_ENV = "CHESS_HARNESS_FOLLOWUP_APPROVAL_TTL_SEC"
DEFAULT_FOLLOWUP_APPROVAL_TTL_SEC = 1800

_REQUESTED = "requested"
_APPROVED = "approved"
_USED = "used"


def followup_approval_ttl_sec() -> int:
    """Operator-tunable approval lifetime in seconds."""
    try:
        return max(1, int(os.environ.get(FOLLOWUP_APPROVAL_TTL_ENV, "")))
    except (TypeError, ValueError):
        return DEFAULT_FOLLOWUP_APPROVAL_TTL_SEC


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


class FollowupApprovalError(Exception):
    """Rejection carrying an HTTP status for the API layer."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


class FollowupApprovalStore:
    """Per-game follow-up approval lifecycle with atomic JSON persistence.

    Lifecycle per previous game id: requested -> approved -> used. Mirrors
    ApiKeyStore's temp-file + fsync + os.replace write pattern.
    """

    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path) if path else resolve_followup_approvals_file()
        self._data = self._load()

    def _load(self) -> Dict[str, Any]:
        if not self.path.exists():
            return {"approvals": {}}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(
                f"Follow-up approval store is unreadable: {self.path}"
            ) from exc
        if not isinstance(data, dict) or not isinstance(data.get("approvals"), dict):
            raise RuntimeError(
                f"Follow-up approval store has invalid schema: {self.path}"
            )
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

    def get(self, game_id: str) -> Optional[Dict[str, Any]]:
        record = self._data.get("approvals", {}).get(game_id)
        return dict(record) if record else None

    def request(self, game_id: str, model_id: str) -> Dict[str, Any]:
        """Mark a finished game as wanting a follow-up; idempotent."""
        with self._locked():
            data = self._load()
            approvals = data.setdefault("approvals", {})
            record = approvals.get(game_id)
            if record is None:
                record = self._new_record(game_id, model_id)
                approvals[game_id] = record
                self._save(data)
                self._data = data
                return dict(record)
            if record.get("model_id") != model_id:
                raise FollowupApprovalError(
                    409, "Follow-up request for this game belongs to another model"
                )
            if record.get("state") == _APPROVED and self._is_expired(record):
                record.update(
                    {
                        "state": _REQUESTED,
                        "requested_at": _now().isoformat(),
                        "approved_at": None,
                        "expires_at": None,
                    }
                )
                self._save(data)
                self._data = data
            return dict(record)

    def approve(self, game_id: str) -> Dict[str, Any]:
        """Operator approval; single-use and time-limited."""
        with self._locked():
            data = self._load()
            record = data.get("approvals", {}).get(game_id)
            if record is None:
                raise FollowupApprovalError(409, "No follow-up request for this game")
            if record.get("state") == _REQUESTED:
                now = _now()
                record.update(
                    {
                        "state": _APPROVED,
                        "approved_at": now.isoformat(),
                        "expires_at": (
                            now + timedelta(seconds=followup_approval_ttl_sec())
                        ).isoformat(),
                    }
                )
                self._save(data)
                self._data = data
                return dict(record)
            if record.get("state") == _APPROVED:
                raise FollowupApprovalError(409, "Follow-up request is already approved")
            raise FollowupApprovalError(409, "Follow-up approval has already been used")

    def consume(self, game_id: str, model_id: str) -> Dict[str, Any]:
        """Atomically consume an approval; single-use per game id."""
        with self._locked():
            data = self._load()
            record = data.get("approvals", {}).get(game_id)
            if record is None:
                raise FollowupApprovalError(409, "No follow-up request for this game")
            if record.get("model_id") != model_id:
                raise FollowupApprovalError(
                    409, "Follow-up approval belongs to another model"
                )
            if record.get("state") == _REQUESTED:
                raise FollowupApprovalError(409, "Follow-up request is not yet approved")
            if record.get("state") == _USED:
                raise FollowupApprovalError(409, "Follow-up approval has already been used")
            if self._is_expired(record):
                raise FollowupApprovalError(409, "Follow-up approval has expired")
            record.update({"state": _USED, "consumed_at": _now().isoformat()})
            self._save(data)
            self._data = data
            return dict(record)

    def revert(self, game_id: str) -> Optional[Dict[str, Any]]:
        """Roll a consumed approval back to approved (game creation failure)."""
        with self._locked():
            data = self._load()
            record = data.get("approvals", {}).get(game_id)
            if record is None or record.get("state") != _USED:
                return None
            record.update({"state": _APPROVED, "consumed_at": None})
            self._save(data)
            self._data = data
            return dict(record)

    def _locked(self) -> filelock.FileLock:
        return filelock.FileLock(str(self.path) + ".lock", timeout=30)

    @staticmethod
    def _new_record(game_id: str, model_id: str) -> Dict[str, Any]:
        return {
            "game_id": game_id,
            "model_id": model_id,
            "state": _REQUESTED,
            "requested_at": _now().isoformat(),
            "approved_at": None,
            "expires_at": None,
            "consumed_at": None,
        }

    @staticmethod
    def _is_expired(record: Dict[str, Any]) -> bool:
        expires = _parse_iso(record.get("expires_at"))
        return expires is not None and expires < _now()