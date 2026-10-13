"""Shared Go Online record, bounded log tail, and cross-process operation lock."""
from __future__ import annotations

import json
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path


def tunnel_process(pid: int | None) -> str:
    """Verify process identity before reporting it running or stopping it."""
    if not pid or pid <= 0:
        return "missing"
    try:
        if sys.platform == "win32":
            result = subprocess.run(
                ["powershell.exe", "-NoProfile", "-Command",
                 f"Get-CimInstance Win32_Process -Filter 'ProcessId = {int(pid)}' | Select-Object Name,CommandLine | ConvertTo-Json -Compress"],
                capture_output=True, text=True, timeout=4, creationflags=subprocess.CREATE_NO_WINDOW,
            )
            if result.returncode:
                return "unknown"
            if not result.stdout.strip():
                return "stale"
            row = json.loads(result.stdout)
            name, command = row.get("Name", ""), row.get("CommandLine", "") or ""
        else:
            process = Path(f"/proc/{pid}")
            if not process.exists():
                return "stale"
            name = (process / "comm").read_text().strip()
            command = (process / "cmdline").read_bytes().replace(b"\0", b" ").decode()
        return "running" if name.lower() in {"cloudflared", "cloudflared.exe"} and "tunnel" in command and "--url" in command else "mismatch"
    except (OSError, ValueError, AttributeError, subprocess.TimeoutExpired):
        return "unknown"


def log_tail(path: Path) -> list[str]:
    try:
        with path.open("rb") as stream:
            stream.seek(0, 2)
            stream.seek(max(0, stream.tell() - 16384))
            return stream.read(16384).decode("utf-8", errors="replace").splitlines()[-40:]
    except OSError:
        return []


@contextmanager
def operation_lock(base_dir: Path):
    """Same exclusive open as PowerShell FileShare.None; OS releases after a crash."""
    path = base_dir / "logs" / "go-online.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
        kernel.CreateFileW.restype = wintypes.HANDLE
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.CreateFileW(str(path), 0xC0000000, 0, None, 4, 0x80, None)
        if handle == wintypes.HANDLE(-1).value:
            raise BlockingIOError("Go Online or Sleep already running")
        try:
            yield
        finally:
            kernel.CloseHandle(handle)
    else:
        import fcntl
        with path.open("a+b") as stream:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            yield


def shared_snapshot(base_dir: Path) -> dict | None:
    path = base_dir / "logs" / "go-online-status.json"
    try:
        if path.stat().st_size > 16384:
            return None
        row = json.loads(path.read_text(encoding="utf-8-sig"))
        if row.get("schema_version") != 1 or row.get("status") not in {"running", "ok", "fail"}:
            return None
        result = {key: row.get(key) for key in ("job_id", "source", "status", "phase", "started_at", "updated_at", "finished_at", "exit_code", "failure_reason")}
        result.update(ok=True, log_tail=log_tail(base_dir / "logs" / "go-online-transcript.log"))
        if result["status"] == "running":
            try:
                with operation_lock(base_dir):
                    result.update(status="fail", phase="Operation interrupted; lock is no longer held", failure_reason="Operation ended without a completion record")
            except BlockingIOError:
                pass
        return result
    except (OSError, ValueError, AttributeError):
        return None
