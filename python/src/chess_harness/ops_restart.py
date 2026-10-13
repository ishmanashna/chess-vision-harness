"""Loopback-only, idle-only graceful restart handoff for managed serve."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import BackgroundTasks, HTTPException, Request
from fastapi.responses import JSONResponse

from .calibration_auth import host_is_loopback
from .game_manager import GameManager
from .ops_online_state import operation_lock
from .paths import project_root, resolve_base_dir

_lock = threading.Lock()


def local_request(request):
    if not host_is_loopback(request):
        return False
    origin = request.headers.get("origin")
    if origin:
        parsed = urlsplit(origin)
        if parsed.scheme not in {"http", "https"} or parsed.netloc.lower() != request.headers.get("host", "").lower():
            return False
    return request.headers.get("sec-fetch-site") != "cross-site"


def status_path(root):
    return root / "logs" / "restart-server.json"


def write_status(root, payload):
    path = status_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(payload, updated_at=datetime.now(timezone.utc).isoformat())
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload), encoding="utf-8")
    for attempt in range(10):
        try:
            temporary.replace(path)
            return
        except PermissionError:
            if attempt == 9: raise
            time.sleep(.05)


def read_status(root):
    try:
        return json.loads(status_path(root).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"status": "idle"}


def active_work(root):
    from filelock import FileLock, Timeout
    from .continuous_calibration import resolve_calibration_manager
    from .identify_attempt import IdentifyAttemptStore
    from .puzzle_attempt import PuzzleAttemptStore
    from .quality_finish import _queue_lock, _running
    reasons = []
    (root / "logs").mkdir(parents=True, exist_ok=True)
    try:
        with FileLock(str(root / "logs" / "annotation-backfill.lock"), timeout=0):
            pass
    except Timeout:
        reasons.append("historical annotation backfill is running")
    if GameManager(str(root)).list_games(status_filter="in_progress"):
        reasons.append("games are running")
    for store, name in ((PuzzleAttemptStore(root / "puzzle_attempts.json"), "puzzle attempts"),
                        (IdentifyAttemptStore(root / "identify_attempts.json"), "identification attempts")):
        if any(row.get("status") == "active" for row in store.list_records()):
            reasons.append(name + " are active")
    with _queue_lock:
        if _running: reasons.append("post-game analysis is running")
    try:
        if resolve_calibration_manager().status_payload().get("active"):
            reasons.append("calibration is running")
    except Exception:
        reasons.append("calibration activity could not be verified")
    return reasons


def detached_options():
    if sys.platform == "win32":
        return {"creationflags": subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def spawn_handoff(root, operation, host, port):
    logs = root / "logs"
    env = dict(os.environ, CHESS_HARNESS_DIR=str(root))
    with (logs / "restart-server.log").open("a", encoding="utf-8") as output:
        return subprocess.Popen([sys.executable, "-m", "chess_harness.restart_worker", "--root", str(root),
                                 "--operation", operation, "--host", host, "--port", str(port), "--parent", str(os.getpid())],
                                cwd=project_root(), env=env, stdin=subprocess.DEVNULL, stdout=output,
                                stderr=subprocess.STDOUT, **detached_options())


def register_restart_routes(app):
    app.state.restart_pending = False
    app.state.mutations_in_flight = 0
    app.state.server_instance = uuid.uuid4().hex

    @app.middleware("http")
    async def restart_admission(request, call_next):
        mutation = request.method in {"POST", "PUT", "PATCH", "DELETE"}
        if mutation and app.state.restart_pending:
            return JSONResponse({"detail": "Server restart in progress; retry after reconnection"}, status_code=409)
        if mutation: app.state.mutations_in_flight += 1
        try:
            return await call_next(request)
        finally:
            if mutation: app.state.mutations_in_flight -= 1

    @app.get("/api/ops/restart-server")
    def restart_status(request: Request):
        if not local_request(request): raise HTTPException(404)
        row = read_status(resolve_base_dir())
        if row.get("status") == "fail" and row.get("old_pid") == os.getpid():
            app.state.restart_pending = False
        return dict(row, server_pid=os.getpid(), instance=app.state.server_instance,
                    supported=callable(getattr(app.state, "request_server_shutdown", None)))

    @app.post("/api/ops/restart-server", status_code=202)
    def restart_start(request: Request, background: BackgroundTasks):
        if not local_request(request): raise HTTPException(404)
        shutdown = getattr(app.state, "request_server_shutdown", None)
        if not callable(shutdown):
            raise HTTPException(409, "This server was not started with managed chess-harness serve")
        root = resolve_base_dir()
        with _lock:
            if app.state.restart_pending: raise HTTPException(409, "Restart already pending")
            app.state.restart_pending = True
            try:
                if app.state.mutations_in_flight > 1:
                    raise HTTPException(409, "Another request is changing server data; retry shortly")
                reasons = active_work(root)
                if reasons: raise HTTPException(409, "Restart refused: " + "; ".join(reasons))
                from .ops_jobs import _go_online_job
                if _go_online_job.status == "running": raise HTTPException(409, "Go Online is running")
                with operation_lock(root):
                    operation = "restart-" + uuid.uuid4().hex[:12]
                    row = {"operation_id": operation, "status": "starting", "phase": "Waiting for graceful shutdown",
                           "old_pid": os.getpid(), "old_instance": app.state.server_instance}
                    write_status(root, row)
                    host, port = getattr(app.state, "serve_address", ("127.0.0.1", request.url.port or 8765))
                    proc = spawn_handoff(root, operation, host, port)
                    row["helper_pid"] = proc.pid
                    write_status(root, row)
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    saved = read_status(root)
                    if saved.get("operation_id") == operation and saved.get("phase") == "Handoff ready":
                        break
                    if proc.poll() is not None:
                        raise RuntimeError("Restart helper exited before handoff")
                    time.sleep(.05)
                else:
                    raise RuntimeError("Restart helper did not acknowledge handoff")
                background.add_task(shutdown)
                return row
            except Exception as exc:
                app.state.restart_pending = False
                if isinstance(exc, HTTPException): raise
                if isinstance(exc, BlockingIOError): raise HTTPException(409, "Go Online or Sleep is running")
                write_status(root, {"status": "fail", "phase": "Could not start restart helper", "reason": type(exc).__name__})
                raise HTTPException(500, "Could not start restart helper; server remains running")
