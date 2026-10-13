"""Read-only, allowlisted views of version-1 run records; never serve raw files."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from .paths import project_root

_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9 ._:/+-]{0,150}\Z")
_SECRET = re.compile(r"(?i)(?:bearer|api.?key|secret|token|sk-|gh[pousr]_)")
_MANIFEST_KEYS = ("experiment_id", "run_id", "model", "provider", "effort", "observation",
                  "status", "started_at", "ended_at", "last_progress_at", "code_revision")
_EVENT_KEYS = ("ts", "event", "phase", "seat_id", "game_id", "model", "provider")


def _label(value):
    if value is None:
        return None
    text = str(value)
    return text if _IDENTIFIER.fullmatch(text) and not _SECRET.search(text) else "[omitted]"


def _records(repo_root=None):
    root = (Path(repo_root) if repo_root else project_root()).resolve()
    for path in sorted((root / "experiments").glob("*/runs/*/manifest.json")):
        # A run or artifact symlink must never turn this into a file browser.
        if path.resolve() != path.absolute() or not path.resolve().is_relative_to(root):
            continue
        try:
            if path.stat().st_size > 64_000:
                continue
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("schema_version") != 1:
                continue
            key = hashlib.sha256(path.relative_to(root).as_posix().encode()).hexdigest()[:20]
            yield key, path, data
        except (OSError, ValueError, AttributeError):
            continue


def _events(path):
    event_path = path.parent / "events.jsonl"
    if event_path.resolve() != event_path.absolute():
        return [], False
    events = []
    truncated = False
    try:
        # Bound bytes as well as rows; no raw prompts, reasons, headers, or usage dumps.
        with event_path.open("rb") as handle:
            remaining = 2_000_000
            while remaining > 0:
                line = handle.readline(min(remaining + 1, 64_001))
                if not line:
                    break
                remaining -= len(line)
                if len(line) > 64_000 or not line.endswith(b"\n"):
                    truncated = True
                    break
                try:
                    row = json.loads(line)
                    events.append({key: _label(row[key]) for key in _EVENT_KEYS if key in row})
                except (ValueError, TypeError):
                    continue
                if len(events) >= 2000:
                    truncated = True
                    break
            if remaining <= 0:
                truncated = True
    except OSError:
        pass
    return events, truncated


def list_experiment_runs(repo_root=None):
    runs = []
    for key, path, data in _records(repo_root):
        row = {field: _label(data.get(field)) for field in _MANIFEST_KEYS}
        row.update(key=key, synthetic=data.get("synthetic") is True,
                   report_url=f"/api/ops/experiments/{key}/report",
                   events_url=f"/api/ops/experiments/{key}/events")
        runs.append(row)
    return {"ok": True, "runs": runs,
            "note": "Version-1 local manifests only. Historical evidence is in experiments/archive; raw archived logs are not exposed."}


def run_game_links(repo_root=None):
    links = {}
    for _key, path, data in _records(repo_root):
        events, _truncated = _events(path)
        for event in events:
            gid = event.get("game_id")
            if gid and gid != "[omitted]":
                run_id = _label(data.get("run_id"))
                previous = links.get(gid)
                links[gid] = run_id if not previous or previous == run_id else "multiple-runs"
    return links


def run_artifact_view(key, kind, repo_root=None):
    for found, path, data in _records(repo_root):
        if found != key:
            continue
        manifest = {field: _label(data.get(field)) for field in _MANIFEST_KEYS}
        events, truncated = _events(path)
        if kind == "events":
            return {"ok": True, "events": events, "truncated": truncated,
                    "note": "Safe event fields only; raw messages, reasons, credentials and provider payloads omitted."}
        if kind == "report":
            return {"ok": True, "manifest": manifest, "synthetic": data.get("synthetic") is True,
                    "event_count": len(events), "events_truncated": truncated,
                    "note": "Safe operational report from manifest/events; raw report.md and private logs are not served. Research conclusions require the reviewed local report."}
    raise FileNotFoundError("Run artifact unavailable")
