"""Parent orchestration records: draft -> approved -> launched -> done/failed.

The harness creates games and task envelopes; it does not launch models or
subagents itself. Drafting an orchestration never starts a game — an explicit
approval action (person or parent runtime) must precede the launch, which is
the only step that calls GameService.
"""

from __future__ import annotations

import json
import os
import secrets
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import filelock

from .paths import resolve_orchestrations_file

__all__ = [
    "ORCH_MODES",
    "OrchestrationError",
    "OrchestrationStore",
    "new_orchestration_id",
]

# Approved orchestration modes.
ORCH_SELF_VS_ENGINE = "self_vs_engine"
ORCH_CHILD_VS_ENGINE = "child_vs_engine"
ORCH_PARENT_VS_CHILD = "parent_vs_child"
ORCH_CHILD_VS_CHILD = "child_vs_child"
ORCH_MODES = (
    ORCH_SELF_VS_ENGINE,
    ORCH_CHILD_VS_ENGINE,
    ORCH_PARENT_VS_CHILD,
    ORCH_CHILD_VS_CHILD,
)

_ENGINE_MODES = (ORCH_SELF_VS_ENGINE, ORCH_CHILD_VS_ENGINE)

_APPROVAL_STATES = ("draft", "approved", "launched", "failed")

# Allowed participant roles per mode: (side kinds, model roles).
_MODE_SIDE_RULES: Dict[str, Dict[str, Any]] = {
    ORCH_SELF_VS_ENGINE: {"kinds": ("model", "engine"), "roles": ("parent",)},
    ORCH_CHILD_VS_ENGINE: {"kinds": ("model", "engine"), "roles": ("child",)},
    ORCH_PARENT_VS_CHILD: {"kinds": ("model", "model"), "roles": ("parent", "child")},
    ORCH_CHILD_VS_CHILD: {"kinds": ("model", "model"), "roles": ("child",)},
}


def new_orchestration_id() -> str:
    return f"orch-{secrets.token_hex(4)}"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso() -> str:
    return _now().isoformat()


class OrchestrationError(Exception):
    """Rejection carrying an HTTP status for the API layer."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


class OrchestrationStore:
    """Lightweight orchestration records with atomic JSON persistence."""

    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path) if path else resolve_orchestrations_file()
        self._data = self._load()

    def _load(self) -> Dict[str, Any]:
        if not self.path.exists():
            return {"orchestrations": {}}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Orchestration store is unreadable: {self.path}") from exc
        if not isinstance(data, dict) or not isinstance(data.get("orchestrations"), dict):
            raise RuntimeError(f"Orchestration store has invalid schema: {self.path}")
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

    def create(
        self,
        parent_model_id: str,
        mode: str,
        white: Dict[str, Any],
        black: Dict[str, Any],
        engine_opponent: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Draft an orchestration; no game is created."""
        if mode not in ORCH_MODES:
            raise OrchestrationError(400, f"Unknown orchestration mode '{mode}'")
        rule = _MODE_SIDE_RULES[mode]
        sides = {"white": dict(white), "black": dict(black)}
        for color, spec in sides.items():
            spec["color"] = color.upper()
            kind = spec.get("kind")
            if kind not in rule["kinds"]:
                raise OrchestrationError(
                    400, f"{mode} requires sides of kind {rule['kinds']}, got '{kind}'"
                )
            if kind == "engine":
                if spec.get("model_id"):
                    raise OrchestrationError(400, "Engine sides do not take a model_id")
                spec["model_id"] = None
                spec["role"] = "engine"
                spec["task_id"] = f"task-{color.lower()}-engine"
            else:
                model_id = str(spec.get("model_id") or "").strip()
                role = str(spec.get("role") or "").strip()
                if not model_id:
                    raise OrchestrationError(400, f"{color} side needs model_id")
                if role not in rule["roles"]:
                    raise OrchestrationError(
                        400,
                        f"{mode} allows roles {rule['roles']} on model sides, got '{role}'",
                    )
                spec["model_id"] = model_id
                spec["role"] = role
                spec["task_id"] = f"task-{color.lower()}-{role}"
            spec["status"] = "pending"
        if mode in _ENGINE_MODES and not engine_opponent:
            raise OrchestrationError(400, "Engine modes require engine_opponent")
        roles = [s["role"] for s in sides.values()]
        if mode == ORCH_PARENT_VS_CHILD and set(roles) != {"parent", "child"}:
            raise OrchestrationError(
                400, "parent_vs_child needs one parent side and one child side"
            )
        record = {
            "orchestration_id": new_orchestration_id(),
            "parent_model_id": parent_model_id,
            "mode": mode,
            "approval_state": "draft",
            "engine_opponent": engine_opponent,
            "created_at": _iso(),
            "approved_at": None,
            "launched_at": None,
            "game_id": None,
            "participants": sides,
            "error": None,
            "result": None,
        }
        with self._locked():
            data = self._load()
            data["orchestrations"][record["orchestration_id"]] = record
            self._save(data)
            self._data = data
        return dict(record)

    def get(self, orchestration_id: str) -> Optional[Dict[str, Any]]:
        record = self._data.get("orchestrations", {}).get(orchestration_id)
        return dict(record) if record else None

    def list_by_parent(self, parent_model_id: str) -> list:
        return [
            dict(record)
            for record in self._data.get("orchestrations", {}).values()
            if record.get("parent_model_id") == parent_model_id
        ]

    def approve(self, orchestration_id: str) -> Dict[str, Any]:
        """Explicit approval: draft -> approved. Still creates no game."""
        with self._locked():
            data = self._load()
            record = data["orchestrations"].get(orchestration_id)
            if record is None:
                raise OrchestrationError(404, "Orchestration not found")
            if record.get("approval_state") == "approved":
                raise OrchestrationError(409, "Orchestration is already approved")
            if record.get("approval_state") != "draft":
                raise OrchestrationError(
                    409, f"Orchestration is {record['approval_state']}, cannot approve"
                )
            record["approval_state"] = "approved"
            record["approved_at"] = _iso()
            self._save(data)
            self._data = data
            return dict(record)

    def launch(
        self,
        orchestration_id: str,
        game_id: str,
        game_type: str,
        task_ids: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Approved -> launched; the only step that records a created game."""
        with self._locked():
            data = self._load()
            record = data["orchestrations"].get(orchestration_id)
            if record is None:
                raise OrchestrationError(404, "Orchestration not found")
            if record.get("approval_state") != "approved":
                raise OrchestrationError(
                    409, "Orchestration must be approved before launch"
                )
            record["approval_state"] = "launched"
            record["launched_at"] = _iso()
            record["game_id"] = game_id
            record["game_type"] = game_type
            if task_ids:
                for color, task_id in task_ids.items():
                    side = record["participants"].get(color)
                    if side is not None:
                        side["task_id"] = task_id
            for side in record["participants"].values():
                if side.get("kind") == "model":
                    side["status"] = "issued"
            self._save(data)
            self._data = data
            return dict(record)

    def fail(self, orchestration_id: str, error: str) -> Optional[Dict[str, Any]]:
        with self._locked():
            data = self._load()
            record = data["orchestrations"].get(orchestration_id)
            if record is None or record.get("approval_state") in ("launched", "failed"):
                return None
            record["approval_state"] = "failed"
            record["error"] = error
            self._save(data)
            self._data = data
            return dict(record)

    def set_result(self, orchestration_id: str, result: Dict[str, Any]) -> None:
        """Attach a result reference (PGN, outcome) without child secrets."""
        with self._locked():
            data = self._load()
            record = data["orchestrations"].get(orchestration_id)
            if record is None:
                return
            record["result"] = dict(result)
            self._save(data)
            self._data = data

    def _locked(self) -> filelock.FileLock:
        return filelock.FileLock(str(self.path) + ".lock", timeout=30)
