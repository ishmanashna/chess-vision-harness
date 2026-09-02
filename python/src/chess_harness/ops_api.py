"""Localhost operator panel: snapshot API and HTML shell."""

from __future__ import annotations

import asyncio
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from .activity_audit import tail_activity
from .calibration_auth import host_is_loopback
from .calibration_supervisor import calibration_worker_error, calibration_worker_healthy
from .calibration_worker_ipc import calibration_in_process
from .contact_inbox import list_messages
from .identify_attempt import IdentifyAttemptStore
from .identify_observer import public_attempt_row as identify_public_row
from .paths import project_root, resolve_base_dir
from .puzzle_attempt import PuzzleAttemptStore
from .ops_audience import audience_snapshot
from .ops_jobs import register_ops_job_routes
from .ops_metrics import metrics_snapshot
from .puzzle_observer import public_attempt_row as puzzle_public_row
from .prompt_test_ops import build_prompt_test_snapshot

__all__ = ["build_ops_snapshot", "register_ops_routes"]

_SNAPSHOT_ACTIVITY_LIMIT = 50
_LIVE_GAMES_LIMIT = 100
_LIVE_ATTEMPTS_LIMIT = 50
_INBOX_PREVIEW_LIMIT = 10


def _system_drive_path(base_dir: Path) -> Path:
    drive = base_dir.drive
    if drive:
        return Path(f"{drive}\\")
    return Path("/")


def _dir_size(path: Path) -> int:
    if not path.is_dir():
        return 0
    total = 0
    for entry in path.rglob("*"):
        if entry.is_file():
            try:
                total += entry.stat().st_size
            except OSError:
                continue
    return total


def _read_optional_text(path: Path) -> Optional[str]:
    if not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return text or None


def _read_optional_pid(path: Path) -> Optional[int]:
    text = _read_optional_text(path)
    if not text or not text.isdigit():
        return None
    return int(text)


def _local_health_payload() -> Dict[str, Any]:
    payload: Dict[str, Any] = {"ok": True, "status": "up"}
    if not calibration_in_process():
        worker_ok = calibration_worker_healthy()
        payload["calibration_worker_ok"] = worker_ok
        if not worker_ok:
            err = calibration_worker_error()
            if err:
                payload["calibration_worker_error"] = err
    return payload


def _inbox_snapshot(base_dir: Path) -> Dict[str, Any]:
    messages = list_messages(base_dir=base_dir)
    unread = sum(1 for row in messages if not row.get("read"))
    return {
        "unread": unread,
        "total": len(messages),
        "latest": messages[:_INBOX_PREVIEW_LIMIT],
    }


def _active_attempt_rows(
    store,
    row_fn,
    *,
    limit: int,
) -> List[Dict[str, Any]]:
    records = [
        row
        for row in store.list_records()
        if row.get("status") == "active"
    ]
    records.sort(key=lambda row: row.get("started_at") or "", reverse=True)
    return [row_fn(row) for row in records[:limit]]


def build_ops_snapshot(
    *,
    base_dir: Optional[Path] = None,
    build_games_list: Optional[Callable[..., tuple[list[Dict[str, Any]], int]]] = None,
) -> Dict[str, Any]:
    """Collect live operator desk data without go-online side effects."""
    root = Path(base_dir) if base_dir is not None else resolve_base_dir()
    drive = _system_drive_path(root)
    usage = shutil.disk_usage(str(drive))
    logs_dir = root / "logs"
    tunnel_pid_path = logs_dir / "quick-tunnel.pid"
    tunnel_url_path = logs_dir / "quick-tunnel.url"

    live_games: List[Dict[str, Any]] = []
    live_games_total = 0
    if build_games_list is not None:
        live_games, live_games_total = build_games_list(
            "in_progress", _LIVE_GAMES_LIMIT, 0
        )

    puzzle_store = PuzzleAttemptStore()
    identify_store = IdentifyAttemptStore()

    health = _local_health_payload()
    return {
        "ok": True,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
        "health": health,
        "disk": {
            "drive": str(drive),
            "total_bytes": usage.total,
            "used_bytes": usage.used,
            "free_bytes": usage.free,
        },
        "harness_dir": {
            "path": str(root),
            "size_bytes": _dir_size(root),
        },
        "tunnel": {
            "pid": _read_optional_pid(tunnel_pid_path),
            "url": _read_optional_text(tunnel_url_path),
            "pid_path": str(tunnel_pid_path),
            "url_path": str(tunnel_url_path),
        },
        "inbox": _inbox_snapshot(root),
        "activity": tail_activity(_SNAPSHOT_ACTIVITY_LIMIT, base_dir=root),
        "live": {
            "games": live_games,
            "games_total": live_games_total,
            "puzzle_attempts": _active_attempt_rows(
                puzzle_store,
                puzzle_public_row,
                limit=_LIVE_ATTEMPTS_LIMIT,
            ),
            "identify_attempts": _active_attempt_rows(
                identify_store,
                identify_public_row,
                limit=_LIVE_ATTEMPTS_LIMIT,
            ),
        },
        "metrics": metrics_snapshot(),
    }


def _ops_html() -> HTMLResponse:
    path = project_root() / "public-site" / "ops" / "index.html"
    if path.is_file():
        return HTMLResponse(path.read_text(encoding="utf-8"))
    raise HTTPException(status_code=404)


def _require_loopback(request: Request) -> None:
    if not host_is_loopback(request):
        raise HTTPException(status_code=404)


def register_ops_routes(app) -> None:
    router = APIRouter(tags=["ops"])

    @router.get("/ops", response_class=HTMLResponse)
    @router.get("/ops/", response_class=HTMLResponse)
    async def ops_page(request: Request):
        _require_loopback(request)
        return _ops_html()

    @router.get("/api/ops/snapshot")
    async def ops_snapshot(request: Request):
        if not host_is_loopback(request):
            raise HTTPException(
                status_code=403, detail="Operator snapshot is only available on localhost"
            )
        from . import spectator as spec

        payload = await asyncio.to_thread(
            build_ops_snapshot,
            base_dir=resolve_base_dir(),
            build_games_list=spec._build_games_list,
        )
        return payload

    @router.get("/api/ops/audience")
    async def ops_audience(request: Request):
        _require_loopback(request)
        return await asyncio.to_thread(audience_snapshot)

    @router.get("/api/ops/prompt-test")
    async def ops_prompt_test(request: Request):
        if not host_is_loopback(request):
            raise HTTPException(
                status_code=403,
                detail="Operator A/B is only available on localhost",
            )
        return await asyncio.to_thread(
            build_prompt_test_snapshot,
            base_dir=resolve_base_dir(),
        )

    app.include_router(router)
    register_ops_job_routes(app)
