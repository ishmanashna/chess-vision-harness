"""HTTP transport with retries for the headless agent client."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any, Callable, Dict, Mapping, Optional, Tuple, Union

DEFAULT_USER_AGENT = (
    "ChessVisionHarness-AgentHttp/0.2 (+https://chessvisionharness.pages.dev)"
)

TransportFn = Callable[
    [str, str, Mapping[str, str], Optional[bytes]],
    Tuple[int, Mapping[str, str], bytes],
]

_RETRYABLE_STATUS = frozenset({429, 502, 503, 504})
_MAX_ATTEMPTS = 6
_MAX_TOTAL_SLEEP_SEC = 120.0


def _parse_retry_after(headers: Mapping[str, str]) -> Optional[float]:
    raw = headers.get("Retry-After") or headers.get("retry-after")
    if not raw:
        return None
    try:
        return max(0.0, float(raw))
    except ValueError:
        return None


def _cap_sleep(requested: float, spent: float) -> float:
    remaining = _MAX_TOTAL_SLEEP_SEC - spent
    if remaining <= 0:
        return 0.0
    return min(requested, remaining)


def request_with_retries(
    transport: TransportFn,
    method: str,
    url: str,
    headers: Mapping[str, str],
    body: Optional[bytes] = None,
) -> Tuple[int, Mapping[str, str], bytes]:
    """Call *transport* with bounded backoff on 429/502/network errors."""
    attempt = 0
    slept = 0.0
    last_error: Optional[Exception] = None
    while attempt < _MAX_ATTEMPTS:
        attempt += 1
        try:
            status, resp_headers, content = transport(method, url, headers, body)
        except urllib.error.URLError as exc:
            last_error = exc
            if attempt >= _MAX_ATTEMPTS or slept >= _MAX_TOTAL_SLEEP_SEC:
                raise
            delay = _cap_sleep(min(2.0 ** (attempt - 1), 30.0), slept)
            if delay <= 0:
                raise
            time.sleep(delay)
            slept += delay
            continue
        if status not in _RETRYABLE_STATUS or attempt >= _MAX_ATTEMPTS:
            return status, resp_headers, content
        retry_after = _parse_retry_after(resp_headers)
        delay = retry_after if retry_after is not None else min(2.0 ** (attempt - 1), 30.0)
        delay = _cap_sleep(delay, slept)
        if delay <= 0:
            return status, resp_headers, content
        time.sleep(delay)
        slept += delay
    if last_error is not None:
        raise last_error
    raise RuntimeError("request_with_retries exhausted attempts")


def urllib_transport(
    timeout_sec: float = 120.0,
) -> TransportFn:
    """Production transport using urllib with a caller-supplied User-Agent."""

    def _transport(
        method: str,
        url: str,
        headers: Mapping[str, str],
        body: Optional[bytes],
    ) -> Tuple[int, Mapping[str, str], bytes]:
        req = urllib.request.Request(url, data=body, method=method.upper())
        for key, value in headers.items():
            req.add_header(key, value)
        try:
            with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
                content = resp.read()
                status = getattr(resp, "status", 200)
                resp_headers = dict(resp.headers.items())
                return status, resp_headers, content
        except urllib.error.HTTPError as exc:
            content = exc.read()
            return exc.code, dict(exc.headers.items()), content

    return _transport


def decode_json(content: bytes) -> Dict[str, Any]:
    if not content:
        return {}
    data = json.loads(content.decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("expected JSON object")
    return data
