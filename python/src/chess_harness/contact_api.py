"""Public contact form plus local or secret-authenticated inbox API."""

from __future__ import annotations

import os
import secrets
from collections import defaultdict, deque
from time import time
from typing import Deque, Dict, Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .api_limits import client_ip, limit_error
from .calibration_auth import host_is_loopback
from .contact_inbox import (
    MAX_MESSAGE_LEN,
    MAX_SENDER_LEN,
    append_message,
    delete_message,
    list_messages,
    mark_read,
)
from .paths import resolve_base_dir

__all__ = ["register_contact_routes"]

_RATE_WINDOW_SEC = 3600.0
_RATE_MAX_PER_IP = 5
_events: Dict[str, Deque[float]] = defaultdict(deque)


class ContactBody(BaseModel):
    sender: str = Field(..., max_length=MAX_SENDER_LEN)
    message: str = Field(..., max_length=MAX_MESSAGE_LEN)


def _prune(ip: str, now: float) -> Deque[float]:
    q = _events[ip]
    cutoff = now - _RATE_WINDOW_SEC
    while q and q[0] <= cutoff:
        q.popleft()
    return q


def _rate_limited(ip: str) -> Optional[JSONResponse]:
    now = time()
    q = _prune(ip, now)
    if len(q) >= _RATE_MAX_PER_IP:
        retry = max(1, int(q[0] + _RATE_WINDOW_SEC - now) + 1)
        return limit_error(429, "Too many contact messages; try again later", retry)
    return None


def _record(ip: str) -> None:
    _prune(ip, time()).append(time())


def _err(status: int, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"ok": False, "error": message})


def _require_loopback(request: Request) -> Optional[JSONResponse]:
    if host_is_loopback(request):
        return None
    configured = os.environ.get("CHESS_HARNESS_INBOX_SECRET", "").strip()
    provided = request.headers.get("X-Chess-Harness-Inbox-Secret", "").strip()
    if configured and provided and secrets.compare_digest(configured, provided):
        return None
    return _err(403, "Inbox is only available on localhost or with the inbox secret")


def register_contact_routes(app) -> None:
    router = APIRouter(prefix="/api/contact", tags=["contact"])

    @router.post("")
    @router.post("/")
    async def contact_submit(body: ContactBody, request: Request):
        limited = _rate_limited(client_ip(request))
        if limited is not None:
            return limited
        result = append_message(
            body.sender, body.message, base_dir=resolve_base_dir()
        )
        if not result.get("ok"):
            return _err(400, result.get("error", "Invalid contact message"))
        _record(client_ip(request))
        return {"ok": True, "id": result["message"]["id"]}

    @router.get("/inbox")
    async def contact_inbox_list(request: Request):
        denied = _require_loopback(request)
        if denied is not None:
            return denied
        return {"ok": True, "messages": list_messages(base_dir=resolve_base_dir())}

    @router.post("/inbox/{message_id}/read")
    async def contact_inbox_read(message_id: str, request: Request):
        denied = _require_loopback(request)
        if denied is not None:
            return denied
        result = mark_read(message_id, base_dir=resolve_base_dir())
        if not result.get("ok"):
            status = 404 if "not found" in result.get("error", "").lower() else 400
            return _err(status, result.get("error", "Update failed"))
        return result

    @router.delete("/inbox/{message_id}")
    async def contact_inbox_delete(message_id: str, request: Request):
        denied = _require_loopback(request)
        if denied is not None:
            return denied
        result = delete_message(message_id, base_dir=resolve_base_dir())
        if not result.get("ok"):
            status = 404 if "not found" in result.get("error", "").lower() else 400
            return _err(status, result.get("error", "Delete failed"))
        return result

    app.include_router(router)
