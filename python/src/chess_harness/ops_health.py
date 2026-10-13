"""Independent cached health probes; never delay the main Ops snapshot."""
from __future__ import annotations

import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from .ops_online_state import tunnel_process

_lock = threading.Lock()
_cache: dict = {}
_pending: set = set()
_TTL = 15
_STALE = 45


def _now():
    return datetime.now(timezone.utc).isoformat()


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def probe(url: str | None, *, edge=False) -> dict:
    row = {"url": url, "checked_at": _now(), "state": "unknown", "timeout_seconds": 4}
    if not url:
        return dict(row, reason="No valid URL configured")
    started = time.monotonic()
    try:
        request = urllib.request.Request(url, headers={"Cache-Control": "no-cache", "Accept": "application/json", "User-Agent": "ChessVisionHarness-Ops/1.0"})
        with urllib.request.build_opener(_NoRedirect).open(request, timeout=4) as response:
            body = json.loads(response.read(8193))
            healthy = body.get("online") is True if edge else body.get("ok") is True or body.get("status") == "up"
            row.update(state="healthy" if healthy else "unhealthy", reason="Reachable" if healthy else "Health payload reports offline")
    except urllib.error.HTTPError as exc:
        row.update(state="unhealthy", reason=f"HTTP {exc.code}")
    except Exception as exc:
        row.update(state="unhealthy", reason=type(exc).__name__)
    return dict(row, duration_ms=round((time.monotonic() - started) * 1000))


def _tracked(root: Path):
    try:
        pid = int((root / "logs" / "quick-tunnel.pid").read_text().strip())
    except (OSError, ValueError):
        pid = None
    try:
        url = (root / "logs" / "quick-tunnel.url").read_text().strip()
    except OSError:
        url = ""
    # Never send an operator probe to an arbitrary URL from a stale/edited file.
    url = url if re.fullmatch(r"https://[a-z0-9-]+\.trycloudflare\.com", url) else None
    return pid, url


def collect(root: Path, local: str, pages: str) -> dict:
    pid, tunnel = _tracked(root)
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(probe, local + "/health"), pool.submit(probe, tunnel + "/health" if tunnel else None),
                   pool.submit(probe, pages + "/api/edge-health", edge=True), pool.submit(tunnel_process, pid)]
        local_check, tunnel_check, pages_check, process = [future.result() for future in futures]
    return {"local": local_check, "tunnel": tunnel_check, "pages": pages_check,
            "process": {"pid": pid, "state": process}, "checked_at": _now()}


def health_snapshot(root: Path, local: str) -> dict:
    pages = os.getenv("CHESS_HARNESS_PUBLIC_URL", "https://chessvisionharness.pages.dev").rstrip("/")
    if not re.fullmatch(r"https://[a-zA-Z0-9.-]+(?::[0-9]+)?", pages):
        pages = "https://chessvisionharness.pages.dev"
    key = (str(root), local, pages)
    now = time.monotonic()
    with _lock:
        saved, timestamp = _cache.get(key, ({}, 0))
        if now - timestamp >= _TTL and key not in _pending:
            _pending.add(key)
            threading.Thread(target=_refresh, args=(key, root, local, pages), daemon=True).start()
        return dict(saved, refreshing=key in _pending, stale=not saved or now - timestamp > _STALE,
                    runtime_dir=str(root), logs_dir=str(root / "logs"), pages_url=pages)


def _refresh(key, root, local, pages):
    try:
        result = collect(root, local, pages)
        with _lock:
            _cache[key] = (result, time.monotonic())
    finally:
        with _lock:
            _pending.discard(key)
