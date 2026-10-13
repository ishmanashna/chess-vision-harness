"""Loopback-only Go Online job runner and sleep-public tunnel control."""

from __future__ import annotations

import subprocess
import sys
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request

from .calibration_auth import host_is_loopback
from .ops_online_state import log_tail, operation_lock, shared_snapshot, tunnel_process
from .paths import project_root, resolve_base_dir

__all__ = ["register_ops_job_routes", "stop_tracked_quick_tunnel"]

_JOB_LOG_NAME = "go-online-job.log"

_spawn_go_online: Optional[Callable[[Path, Path], subprocess.Popen]] = None
_stop_tracked_tunnel: Optional[Callable[[Optional[Path]], Dict[str, Any]]] = None


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _default_spawn_go_online(repo_root: Path, log_path: Path, operation_id: str = "") -> subprocess.Popen:
    script = repo_root / "deploy" / "go-online.ps1"
    if not script.is_file():
        raise FileNotFoundError(f"go-online.ps1 not found at {script}")
    log_handle = open(log_path, "a", encoding="utf-8", buffering=1)
    cmd = [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script),
        "-NoPanel",
        "-RepoRoot",
        str(repo_root),
    ]
    import os
    env = dict(os.environ, CHESS_HARNESS_DIR=str(log_path.parent.parent))
    try:
        return subprocess.Popen(cmd + ["-OperationSource", "panel", "-OperationId", operation_id], cwd=str(repo_root),
                                stdout=log_handle, stderr=subprocess.STDOUT, env=env,
                                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
    finally:
        log_handle.close()


def _kill_pid(pid: int) -> bool:
    if sys.platform == "win32":
        result = subprocess.run(
            ["taskkill", "/PID", str(pid), "/F"],
            capture_output=True,
            check=False,
        )
        return result.returncode == 0
    import signal

    try:
        import os

        os.kill(pid, signal.SIGTERM)
        return True
    except OSError:
        return False


def stop_tracked_quick_tunnel(base_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Stop the tracked Quick Tunnel process only; localhost serve stays up."""
    if _stop_tracked_tunnel is not None:
        return _stop_tracked_tunnel(base_dir)

    root = base_dir if base_dir is not None else resolve_base_dir()
    pid_path = root / "logs" / "quick-tunnel.pid"
    stopped = False
    pid: Optional[int] = None
    if pid_path.is_file():
        raw = pid_path.read_text(encoding="utf-8", errors="replace").strip()
        first = raw.splitlines()[0].strip() if raw else ""
        if first.isdigit():
            pid = int(first)
            identity = tunnel_process(pid)
            if identity == "unknown":
                raise HTTPException(status_code=409, detail="Tunnel identity could not be verified; nothing stopped")
            stopped = identity == "running" and _kill_pid(pid)
            if identity == "running" and not stopped:
                raise HTTPException(status_code=500, detail="Tunnel stop failed; tracking retained")
        try:
            pid_path.unlink()
        except OSError:
            pass
    (root / "logs" / "quick-tunnel.url").unlink(missing_ok=True)
    return {"ok": True, "stopped": stopped, "pid": pid}


class GoOnlineJobState:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.status = "idle"
        self.job_id: Optional[str] = None
        self.phase = ""
        self.started_at: Optional[str] = None
        self.finished_at: Optional[str] = None
        self.exit_code: Optional[int] = None
        self._last_shared = None
        self._proc: Optional[subprocess.Popen] = None
        self._log_path: Optional[Path] = None

    def _log_file(self, base_dir: Path) -> Path:
        logs = base_dir / "logs"
        logs.mkdir(parents=True, exist_ok=True)
        return logs / _JOB_LOG_NAME

    def _read_log_tail(self) -> List[str]:
        if not self._log_path or not self._log_path.is_file():
            return []
        return log_tail(self._log_path)

    def snapshot(self, base_dir: Optional[Path] = None) -> Dict[str, Any]:
        shared = shared_snapshot(base_dir) if base_dir is not None else None
        if shared:
            self._last_shared = shared
        else:
            shared = self._last_shared
        if shared and (self.status != "running" or shared.get("started_at", "") >= (self.started_at or "")):
            return shared
        with self._lock:
            tail = self._read_log_tail()
            phase = tail[-1] if tail and self.status == "running" else self.phase
            payload: Dict[str, Any] = {
                "ok": True,
                "status": self.status,
                "phase": phase,
                "log_tail": tail,
            }
            if self.job_id:
                payload["job_id"] = self.job_id
            if self.started_at:
                payload["started_at"] = self.started_at
            if self.finished_at:
                payload["finished_at"] = self.finished_at
            if self.exit_code is not None:
                payload["exit_code"] = self.exit_code
            return payload

    def start(self, *, base_dir: Path, repo_root: Path) -> Dict[str, Any]:
        try:
            with operation_lock(base_dir):
                pass
        except BlockingIOError:
            raise HTTPException(status_code=409, detail="Go Online or Sleep already running")
        with self._lock:
            if self.status == "running":
                raise HTTPException(status_code=409, detail="Go Online job already running")
            self.status = "running"
            self.job_id = f"go-online-{uuid.uuid4().hex[:12]}"
            self.phase = "Starting go-online.ps1..."
            self.started_at = _utc_now()
            self.finished_at = None
            self.exit_code = None
            self._log_path = self._log_file(base_dir)
            try:
                self._log_path.write_text("", encoding="utf-8")
            except OSError:
                pass
            spawn = _spawn_go_online or _default_spawn_go_online
            try:
                self._proc = spawn(repo_root, self._log_path) if _spawn_go_online else _default_spawn_go_online(repo_root, self._log_path, self.job_id)
            except Exception as exc:
                self.status = "fail"
                self.phase = str(exc)
                self.finished_at = _utc_now()
                self.exit_code = 1
                raise HTTPException(status_code=500, detail=str(exc)) from exc
            proc = self._proc
            threading.Thread(target=self._watch_process, args=(proc,), daemon=True).start()
            return {"ok": True, "job_id": self.job_id, "status": "running"}

    def _watch_process(self, proc: subprocess.Popen) -> None:
        code = 1
        try:
            code = proc.wait()
        except Exception:
            code = 1
        with self._lock:
            self.exit_code = code
            self.finished_at = _utc_now()
            tail = self._read_log_tail()
            if tail:
                self.phase = tail[-1]
            self.status = "ok" if code == 0 else "fail"
            self._proc = None


_go_online_job = GoOnlineJobState()


def register_ops_job_routes(app) -> None:
    router = APIRouter(tags=["ops"])

    def _require_loopback(request: Request) -> None:
        if not host_is_loopback(request):
            raise HTTPException(status_code=404)

    @router.post("/api/ops/go-online")
    def ops_go_online_start(request: Request):
        _require_loopback(request)
        return _go_online_job.start(
            base_dir=resolve_base_dir(),
            repo_root=project_root(),
        )

    @router.get("/api/ops/go-online")
    def ops_go_online_status(request: Request):
        _require_loopback(request)
        return _go_online_job.snapshot(resolve_base_dir())

    @router.post("/api/ops/sleep-public")
    def ops_sleep_public(request: Request):
        _require_loopback(request)
        if _go_online_job.status == "running":
            raise HTTPException(status_code=409, detail="Go Online already running")
        try:
            with operation_lock(resolve_base_dir()):
                return stop_tracked_quick_tunnel(resolve_base_dir())
        except BlockingIOError:
            raise HTTPException(status_code=409, detail="Go Online or Sleep already running")

    app.include_router(router)
