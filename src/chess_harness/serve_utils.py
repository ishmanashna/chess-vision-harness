"""Spectator port and process management."""

from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .paths import resolve_base_dir


def spectator_meta_path() -> Path:
    return resolve_base_dir() / "spectator.json"


def is_port_in_use(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) == 0


def find_pids_on_port(port: int) -> List[int]:
    pids: set[int] = set()
    if sys.platform == "win32":
        result = subprocess.run(
            ["netstat", "-ano"],
            capture_output=True,
            text=True,
            check=False,
        )
        needle = f":{port}"
        for line in result.stdout.splitlines():
            if "LISTENING" in line and needle in line:
                parts = line.split()
                if parts:
                    try:
                        pids.add(int(parts[-1]))
                    except ValueError:
                        pass
    else:
        for cmd in (
            ["lsof", "-ti", f":{port}"],
            ["fuser", f"{port}/tcp"],
        ):
            result = subprocess.run(cmd, capture_output=True, text=True, check=False)
            if result.returncode == 0 and result.stdout.strip():
                for token in result.stdout.replace("\n", " ").split():
                    try:
                        pids.add(int(token))
                    except ValueError:
                        pass
                break
    current = os.getpid()
    return sorted(pid for pid in pids if pid != current)


def kill_pids(pids: List[int]) -> List[int]:
    killed: List[int] = []
    for pid in pids:
        if pid == os.getpid():
            continue
        try:
            if sys.platform == "win32":
                subprocess.run(
                    ["taskkill", "/PID", str(pid), "/F"],
                    capture_output=True,
                    check=False,
                )
            else:
                os.kill(pid, signal.SIGTERM)
            killed.append(pid)
        except (OSError, ProcessLookupError):
            pass
    return killed


def read_spectator_meta() -> Optional[Dict[str, Any]]:
    path = spectator_meta_path()
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def write_spectator_meta(host: str, port: int) -> None:
    path = spectator_meta_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "pid": os.getpid(),
                "host": host,
                "port": port,
                "started_at": time.time(),
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def remove_spectator_meta() -> None:
    path = spectator_meta_path()
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def ensure_port_available(host: str, port: int, force: bool = False) -> None:
    """Raise RuntimeError with actionable message if port is taken."""
    if not is_port_in_use(host, port):
        return

    pids = find_pids_on_port(port)
    meta = read_spectator_meta()

    if force:
        killed = kill_pids(pids)
        remove_spectator_meta()
        time.sleep(0.5)
        if is_port_in_use(host, port):
            remaining = find_pids_on_port(port)
            raise RuntimeError(
                f"Port {port} is still in use after stopping PIDs {killed}. "
                f"Remaining: {remaining}. Try: python play.py serve stop"
            )
        if killed:
            print(f"Stopped previous spectator process(es): {killed}")
        return

    hint = "python play.py serve stop"
    if meta and meta.get("port") == port:
        hint = f"python play.py serve stop   (recorded pid {meta.get('pid')})"

    pid_text = ", ".join(str(p) for p in pids) if pids else "unknown"
    raise RuntimeError(
        f"Port {port} is already in use (PID(s): {pid_text}).\n"
        f"Stop the old server: {hint}\n"
        f"Or force-restart:    python play.py serve --force"
    )


def stop_spectator(port: int = 8765) -> bool:
    """Stop spectator process(es) on the given port."""
    pids = find_pids_on_port(port)
    if not pids:
        remove_spectator_meta()
        print(f"No spectator found on port {port}.")
        return False

    killed = kill_pids(pids)
    remove_spectator_meta()
    time.sleep(0.3)
    print(f"Stopped spectator on port {port} (PID(s): {killed}).")
    return True
