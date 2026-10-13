"""Detached restart helper. Never kills processes or replaces an occupied port."""
from __future__ import annotations

import argparse
import ctypes
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from .ops_online_state import operation_lock
from .ops_restart import detached_options, read_status, write_status
from .paths import project_root
from .serve_utils import is_port_in_use


def parent_alive(pid):
    if sys.platform == "win32":
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE,wintypes.DWORD]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x100000, False, pid)
        if not handle:
            if ctypes.get_last_error() == 87: return False
            raise OSError("Could not verify old server process")
        try: return kernel.WaitForSingleObject(handle,0) == 258
        finally: kernel.CloseHandle(handle)
    try:
        os.kill(pid,0)
        return True
    except ProcessLookupError: return False


def healthy(host, port):
    connect_host = "127.0.0.1" if host in {"0.0.0.0", "localhost"} else host
    if ":" in connect_host: connect_host = "[" + connect_host + "]"
    try:
        with urllib.request.urlopen(f"http://{connect_host}:{port}/health",timeout=2) as response:
            row = json.loads(response.read(4096))
        return row.get("ok") is True or row.get("status") == "up"
    except Exception: return False


def restart(root, operation, host, port, parent):
    row = read_status(root)
    if row.get("operation_id") != operation or row.get("old_pid") != parent:
        raise RuntimeError("Restart request identity changed")
    try:
        # The endpoint briefly holds the same lock while spawning this helper.
        deadline = time.monotonic() + 5
        while True:
            guard = operation_lock(root)
            try:
                guard.__enter__()
                break
            except BlockingIOError:
                if time.monotonic() >= deadline: raise
                time.sleep(.05)
        try:
            row.update(status="restarting",phase="Handoff ready")
            write_status(root,row)
            deadline = time.monotonic() + 45
            while parent_alive(parent):
                if time.monotonic() >= deadline: raise RuntimeError("Old server did not exit; no replacement started")
                time.sleep(.1)
            connect_host = "127.0.0.1" if host == "0.0.0.0" else host
            if is_port_in_use(connect_host,port):
                raise RuntimeError("Server port is occupied; no process was stopped")
            row.update(phase="Starting updated server")
            write_status(root,row)
            env = dict(os.environ,CHESS_HARNESS_DIR=str(root),CHESS_HARNESS_RESTART_HANDOFF="1")
            with (root/'logs'/'harness-restarted.log').open('a',encoding='utf-8') as output:
                process = subprocess.Popen([sys.executable,"-m","chess_harness","serve","--host",host,"--port",str(port)],
                    cwd=project_root(),env=env,stdin=subprocess.DEVNULL,stdout=output,stderr=subprocess.STDOUT,**detached_options())
            row.update(new_pid=process.pid,phase="Waiting for server health")
            write_status(root,row)
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline:
                if process.poll() is not None: raise RuntimeError("Replacement server exited; inspect harness-restarted.log")
                try:
                    meta = json.loads((root/'spectator.json').read_text())
                except (OSError,ValueError): meta = {}
                if meta.get('pid') == process.pid and healthy(host,port):
                    row.update(status="ready",phase="Updated server is healthy")
                    write_status(root,row)
                    return
                time.sleep(.5)
            raise RuntimeError("Replacement started but health did not become ready within 60s")
        finally: guard.__exit__(None,None,None)
    except Exception as error:
        row.update(status="fail",phase=str(error))
        write_status(root,row)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--operation',required=True)
    parser.add_argument('--host',required=True)
    parser.add_argument('--port',type=int,required=True)
    parser.add_argument('--parent',type=int,required=True)
    args = parser.parse_args()
    restart(args.root,args.operation,args.host,args.port,args.parent)
