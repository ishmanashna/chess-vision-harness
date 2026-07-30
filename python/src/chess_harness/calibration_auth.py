"""Tunnel-safe auth for calibration mutation endpoints."""

from __future__ import annotations

import os
import secrets

from fastapi import HTTPException, Request

__all__ = ["host_is_loopback", "require_calibration_auth"]


def _allow_remote_calibration() -> bool:
    return os.environ.get("CHESS_HARNESS_ALLOW_REMOTE_CALIBRATION", "").strip() == "1"


def _configured_secret() -> str | None:
    value = os.environ.get("CHESS_HARNESS_CALIBRATION_SECRET", "").strip()
    return value or None


def _provided_secret(request: Request) -> str | None:
    header = request.headers.get("CHESS_HARNESS_CALIBRATION_SECRET")
    if header:
        return header.strip()
    alt = request.headers.get("X-Chess-Harness-Calibration-Secret")
    if alt:
        return alt.strip()
    query = request.query_params.get("calibration_secret")
    if query:
        return query.strip()
    return None


def host_is_loopback(request: Request) -> bool:
    """True for direct localhost serve. Not client IP (unreliable behind Tunnel)."""
    host = (request.headers.get("host") or "").strip().lower()
    if not host:
        return False
    hostname = host.rsplit("@", 1)[-1]
    if hostname.startswith("["):
        end = hostname.find("]")
        hostname = hostname[1:end] if end != -1 else hostname
    else:
        hostname = hostname.split(":", 1)[0]
    return hostname in {"127.0.0.1", "localhost", "::1"}


def require_calibration_auth(request: Request) -> None:
    """
    Allow calibration POSTs when:
    - Host is loopback (direct http://127.0.0.1/... serve), or
    - CHESS_HARNESS_ALLOW_REMOTE_CALIBRATION=1, or
    - request carries a matching CHESS_HARNESS_CALIBRATION_SECRET.
    """
    if host_is_loopback(request):
        return
    if _allow_remote_calibration():
        return
    secret = _configured_secret()
    if not secret:
        raise HTTPException(
            status_code=403,
            detail=(
                "Calibration POSTs require CHESS_HARNESS_CALIBRATION_SECRET "
                "or CHESS_HARNESS_ALLOW_REMOTE_CALIBRATION=1 "
                "(or open http://127.0.0.1:8765/calibration directly)"
            ),
        )
    provided = _provided_secret(request)
    if not provided or not secrets.compare_digest(provided, secret):
        raise HTTPException(status_code=403, detail="Invalid calibration secret")
