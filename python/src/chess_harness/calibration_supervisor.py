"""Spawn and supervise the out-of-process calibration worker."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

from .calibration_worker_ipc import (
    calibration_worker_base_url,
    calibration_worker_port,
    http_json,
    worker_health_ok,
)
from .paths import resolve_calibration_worker_dir

_log = logging.getLogger(__name__)

_worker_proc: Optional[subprocess.Popen] = None
_spawn_lock = asyncio.Lock()
_worker_error: Optional[str] = None


def calibration_worker_error() -> Optional[str]:
    """Last calibration worker spawn/health failure, if any."""
    return _worker_error


def calibration_worker_healthy() -> bool:
    """Whether the calibration worker HTTP health endpoint responds."""
    return worker_health_ok()


def _worker_dir() -> Path:
    path = resolve_calibration_worker_dir()
    path.mkdir(parents=True, exist_ok=True)
    return path


def _pid_path() -> Path:
    return _worker_dir() / "worker.pid"


def _write_pid(pid: int) -> None:
    _pid_path().write_text(str(pid), encoding="utf-8")


def _clear_pid() -> None:
    try:
        _pid_path().unlink()
    except OSError:
        pass


def _spawn_worker_process() -> subprocess.Popen:
    env = os.environ.copy()
    port = calibration_worker_port()
    env["CHESS_HARNESS_CALIBRATION_WORKER"] = "1"
    env["CHESS_HARNESS_CALIBRATION_WORKER_PORT"] = str(port)
    env.setdefault("CHESS_HARNESS_CALIBRATION_IN_PROCESS", "1")
    cmd = [sys.executable, "-m", "chess_harness.calibration_worker"]
    proc = subprocess.Popen(
        cmd,
        env=env,
        cwd=str(Path(__file__).resolve().parent.parent.parent.parent),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    _write_pid(proc.pid)
    return proc


async def _wait_for_worker(timeout_sec: float = 30.0) -> None:
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        if worker_health_ok(timeout=0.5):
            return
        await asyncio.sleep(0.2)
    raise RuntimeError(
        f"calibration worker did not become healthy on {calibration_worker_base_url()}"
    )


async def ensure_calibration_worker() -> None:
    """Start the worker subprocess if nothing healthy is listening."""
    global _worker_proc, _worker_error
    async with _spawn_lock:
        if worker_health_ok():
            _worker_error = None
            return
        if _worker_proc is not None and _worker_proc.poll() is None:
            try:
                await _wait_for_worker()
                _worker_error = None
                return
            except Exception as exc:
                _worker_error = str(exc)
                _log.exception("calibration worker failed to become healthy")
                raise
        try:
            _worker_proc = _spawn_worker_process()
            await _wait_for_worker()
            _worker_error = None
        except Exception as exc:
            _worker_error = str(exc)
            _log.exception("calibration worker failed to start")
            raise


async def shutdown_calibration_worker() -> None:
    """Stop calibration loops and tear down the supervised worker."""
    global _worker_proc
    if worker_health_ok():
        try:
            await asyncio.to_thread(http_json, "POST", "/stop-all", timeout=10.0)
        except Exception:
            pass
        try:
            await asyncio.to_thread(http_json, "POST", "/shutdown", timeout=5.0)
        except Exception:
            pass
    proc = _worker_proc
    _worker_proc = None
    if proc is not None and proc.poll() is None:
        proc.terminate()
        try:
            await asyncio.to_thread(proc.wait, 5)
        except Exception:
            proc.kill()
    _clear_pid()


def cmd_calibration_worker(host: str = "127.0.0.1", port: int | None = None) -> None:
    """CLI entry: run the calibration worker HTTP service."""
    from .calibration_worker import run_calibration_worker

    run_calibration_worker(host=host, port=port or calibration_worker_port())
