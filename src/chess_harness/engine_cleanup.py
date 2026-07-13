"""Kill orphaned opponent UCI subprocesses left after crashes or forced stops."""

from __future__ import annotations

import json
import subprocess
import sys

DEFAULT_OPPONENT_PROCESS_NAMES = (
    "stockfish-windows-x86-64",
    "stockfish",
    "minimalchess-0.2",
    "minimalchess-0.3",
)

_POOL_WORKER_MARKER = "multiprocessing-fork"


def _windows_pids_by_image(name: str) -> list[int]:
    stem = name if name.lower().endswith(".exe") else f"{name}.exe"
    result = subprocess.run(
        ["tasklist", "/FI", f"IMAGENAME eq {stem}", "/FO", "CSV", "/NH"],
        capture_output=True,
        text=True,
        check=False,
    )
    pids: list[int] = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line or "No tasks" in line:
            continue
        parts = line.split(",")
        if len(parts) >= 2:
            try:
                pids.append(int(parts[1].strip('"')))
            except ValueError:
                continue
    return pids


def kill_opponent_processes(*names: str) -> dict[str, int]:
    """Terminate opponent engine processes by image name. Returns {name: count killed}."""
    killed: dict[str, int] = {}
    if sys.platform == "win32":
        for name in names:
            pids = _windows_pids_by_image(name)
            count = 0
            for pid in pids:
                subprocess.run(
                    ["taskkill", "/PID", str(pid), "/F", "/T"],
                    capture_output=True,
                    check=False,
                )
                count += 1
            if count:
                killed[name] = count
        return killed

    import signal

    for name in names:
        result = subprocess.run(["pkill", "-f", name], capture_output=True, check=False)
        if result.returncode == 0:
            killed[name] = -1
    return killed


def kill_orphaned_opponent_engines() -> dict[str, int]:
    """Kill all known opponent engine binaries (Stockfish, Patricia, MinimalChess, …)."""
    return kill_opponent_processes(*DEFAULT_OPPONENT_PROCESS_NAMES)


def _windows_list_python_processes() -> list[dict]:
    script = (
        "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" "
        "| Select-Object ProcessId,ParentProcessId,CommandLine "
        "| ConvertTo-Json -Compress"
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        capture_output=True,
        text=True,
        check=False,
    )
    if not result.stdout.strip():
        return []
    data = json.loads(result.stdout)
    if isinstance(data, dict):
        return [data]
    return list(data)


def _windows_parent_cmdline(pid: int) -> str | None:
    script = (
        f"(Get-CimInstance Win32_Process -Filter 'ProcessId={pid}' "
        "-ErrorAction SilentlyContinue).CommandLine"
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        capture_output=True,
        text=True,
        check=False,
    )
    cmd = result.stdout.strip()
    return cmd or None


def kill_orphan_pool_workers(*, keep_pids: set[int] | None = None) -> int:
    """
    Kill idle ProcessPoolExecutor worker processes left behind when the parent
    spectator/calibration process was stopped without executor shutdown.
  """
    keep = keep_pids or set()
    killed = 0
    if sys.platform == "win32":
        alive_pids = {int(row["ProcessId"]) for row in _windows_list_python_processes()}
        for row in _windows_list_python_processes():
            pid = int(row["ProcessId"])
            if pid in keep:
                continue
            cmd = row.get("CommandLine") or ""
            if _POOL_WORKER_MARKER not in cmd:
                continue
            parent_pid = int(row.get("ParentProcessId") or 0)
            parent_alive = parent_pid in alive_pids
            parent_cmd = _windows_parent_cmdline(parent_pid) if parent_alive else None
            parent_is_spectator = bool(
                parent_cmd
                and ("play.py serve" in parent_cmd or "uvicorn" in parent_cmd.lower())
            )
            if parent_alive and parent_is_spectator:
                continue
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/F", "/T"],
                capture_output=True,
                check=False,
            )
            killed += 1
        return killed

    result = subprocess.run(
        ["pkill", "-f", _POOL_WORKER_MARKER],
        capture_output=True,
        check=False,
    )
    return 0 if result.returncode != 0 else -1


def kill_orphaned_harness_processes() -> dict[str, int]:
    """Kill orphaned calibration pool workers and opponent UCI subprocesses."""
    engines = kill_orphaned_opponent_engines()
    workers = kill_orphan_pool_workers()
    if workers > 0:
        engines["python-pool-workers"] = workers
    elif workers == -1:
        engines["python-pool-workers"] = -1
    return engines
