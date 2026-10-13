"""Small standard-library run records; no provider or process execution."""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

TERMINAL_STATUSES = {"completed", "failed", "abandoned"}
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,100}\Z")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def code_identity() -> tuple[str | None, bool | None]:
    root = Path(__file__).resolve().parent.parent
    try:
        revision = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, stderr=subprocess.DEVNULL,
            text=True, timeout=5,
        ).strip()
        dirty = bool(subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=root, stderr=subprocess.DEVNULL,
            text=True, timeout=5,
        ).strip())
        return revision, dirty
    except (OSError, subprocess.SubprocessError):
        return None, None


def _write_json(path: Path, data: dict[str, Any]) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


class RunRecord:
    """One new directory, one manifest, an event stream, and a terminal report."""

    def __init__(self, output_root: Path, run_id: str, config: dict[str, Any], prompt: bytes):
        experiment_id = config.get("experiment_id", "")
        for value in (experiment_id, run_id):
            if not isinstance(value, str) or not _ID.fullmatch(value):
                raise ValueError("Experiment and run IDs must be simple names, not paths")
        for field in ("hypothesis", "model", "provider"):
            if not isinstance(config.get(field), str) or not config[field].strip():
                raise ValueError(f"Missing or invalid {field}")
        if config.get("observation") not in {"vision", "text", "none"}:
            raise ValueError("observation must be vision, text, or none")
        for field in ("opponents", "colors"):
            if not isinstance(config.get(field), list) or any(
                not isinstance(item, str) for item in config[field]
            ):
                raise ValueError(f"{field} must be a list of names")
        if not isinstance(config.get("synthetic"), bool):
            raise ValueError("synthetic must be explicitly true or false")
        serialized = json.dumps(config, sort_keys=True, separators=(",", ":")).encode("utf-8")
        revision, dirty = code_identity()
        self.directory = Path(output_root).resolve() / run_id
        self.directory.mkdir(parents=True, exist_ok=False)
        self.manifest: dict[str, Any] = {
            "schema_version": 1,
            "experiment_id": experiment_id,
            "run_id": run_id,
            "hypothesis": config["hypothesis"],
            "code_revision": revision,
            "code_dirty": dirty,
            "synthetic": config["synthetic"],
            "provider": config["provider"],
            "model": config["model"],
            "effort": config.get("effort"),
            "observation": config["observation"],
            "opponents": config["opponents"],
            "colors": config["colors"],
            "seed": config.get("seed"),
            "prompt_sha256": hashlib.sha256(prompt).hexdigest(),
            "config_sha256": hashlib.sha256(serialized).hexdigest(),
            "started_at": utc_now(),
            "ended_at": None,
            "last_progress_at": None,
            "status": "running",
            "reason": None,
            "usage": {"tokens": None, "cost_usd": None, "source": "unavailable"},
            "artifacts": {"events": "events.jsonl", "report": "report.md"},
        }
        self.event("run_started", phase="setup")

    def event(
        self, event: str, *, seat_id: str | None = None, game_id: str | None = None,
        phase: str | None = None, reason: str | None = None,
        retry_count: int | None = None, rate_limited: bool | None = None,
        usage: dict[str, Any] | None = None,
    ) -> None:
        if self.manifest["status"] != "running":
            raise ValueError("Cannot append events to a terminal run")
        row = {key: self.manifest[key] for key in (
            "schema_version", "experiment_id", "run_id", "model", "provider"
        )}
        row.update({"ts": utc_now(), "event": event})
        for key, value in {
            "seat_id": seat_id, "game_id": game_id, "phase": phase, "reason": reason,
            "retry_count": retry_count, "rate_limited": rate_limited, "usage": usage,
        }.items():
            if value is not None:
                row[key] = value
        with (self.directory / "events.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
        self.manifest["last_progress_at"] = row["ts"]
        _write_json(self.directory / "manifest.json", self.manifest)

    def finish(self, status: str, *, reason: str, summary: str) -> None:
        if status not in TERMINAL_STATUSES or not reason.strip() or not summary.strip():
            raise ValueError("Finish requires a terminal status, reason, and summary")
        self.event("run_finished", phase=status, reason=reason)
        report = (
            f"# {self.manifest['experiment_id']} / {self.manifest['run_id']}\n\n"
            f"Status: {status}\n\nSynthetic: {self.manifest['synthetic']}\n\n"
            f"Reason: {reason}\n\n{summary}\n\n"
            "Evidence: [manifest](manifest.json), [events](events.jsonl).\n\n"
            "Provider tokens/cost: unavailable unless separately measured.\n"
        )
        (self.directory / "report.md").write_text(report, encoding="utf-8")
        self.manifest.update(status=status, ended_at=utc_now(), reason=reason)
        _write_json(self.directory / "manifest.json", self.manifest)
