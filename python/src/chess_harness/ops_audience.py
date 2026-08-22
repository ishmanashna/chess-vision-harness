"""Umami Cloud audience metrics for the localhost operator Traffic tab."""

from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

__all__ = [
    "DEFAULT_UMAMI_API_BASE",
    "audience_snapshot",
    "fetch_audience_from_umami",
    "reset_audience_cache",
]

DEFAULT_UMAMI_API_BASE = "https://api.umami.is/v1"
CACHE_SECONDS = 60
_UNCONFIGURED_MESSAGE = (
    "Set CHESS_HARNESS_UMAMI_TOKEN and CHESS_HARNESS_UMAMI_WEBSITE_ID "
    "in the game PC serve environment to load Umami audience data here. "
    "The Umami Cloud web dashboard still works when this PC is off."
)

_cache: Optional[Dict[str, Any]] = None
_cache_at: float = 0.0
_cache_lock = threading.Lock()


def _env_config() -> Tuple[Optional[str], Optional[str], str]:
    token = os.environ.get("CHESS_HARNESS_UMAMI_TOKEN", "").strip()
    website_id = os.environ.get("CHESS_HARNESS_UMAMI_WEBSITE_ID", "").strip()
    api_base = os.environ.get("CHESS_HARNESS_UMAMI_API_HOST", DEFAULT_UMAMI_API_BASE).strip().rstrip("/")
    return (token or None, website_id or None, api_base)


def _unconfigured_payload() -> Dict[str, Any]:
    return {
        "ok": True,
        "configured": False,
        "message": _UNCONFIGURED_MESSAGE,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
        "pageviews": None,
        "visitors": None,
        "referrers": [],
        "pages": [],
        "countries": [],
        "source": "umami",
    }


def _metric_value(entry: Any) -> int:
    if isinstance(entry, dict):
        if "value" in entry:
            return int(entry.get("value") or 0)
        if "y" in entry:
            return int(entry.get("y") or 0)
        if "pageviews" in entry:
            return int(entry.get("pageviews") or 0)
        if "visitors" in entry:
            return int(entry.get("visitors") or 0)
    if entry is None:
        return 0
    try:
        return int(entry)
    except (TypeError, ValueError):
        return 0


def _fetch_json(url: str, token: str, *, timeout: float = 15.0) -> Any:
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
        },
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _range_ms(now_ms: Optional[int] = None) -> Tuple[int, int]:
    end_ms = now_ms if now_ms is not None else int(time.time() * 1000)
    start_ms = end_ms - 24 * 60 * 60 * 1000
    return start_ms, end_ms


def _metrics_rows(
    *,
    token: str,
    website_id: str,
    api_base: str,
    start_ms: int,
    end_ms: int,
    metric_type: str,
    limit: int,
    http_fetch: Callable[..., Any],
) -> List[Dict[str, Any]]:
    query = urllib.parse.urlencode(
        {
            "startAt": start_ms,
            "endAt": end_ms,
            "type": metric_type,
            "limit": limit,
        }
    )
    url = f"{api_base}/websites/{website_id}/metrics?{query}"
    rows = http_fetch(url, token)
    if not isinstance(rows, list):
        return []
    out: List[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = row.get("x")
        if name is None:
            name = row.get("name")
        label = str(name or "").strip()
        if metric_type == "referrer" and not label:
            label = "direct"
        out.append({"name": label, "visitors": _metric_value(row)})
    return out


def fetch_audience_from_umami(
    *,
    token: str,
    website_id: str,
    api_base: str,
    now_ms: Optional[int] = None,
    http_fetch: Callable[..., Any] = _fetch_json,
) -> Dict[str, Any]:
    """Pull last-24h Umami stats for the configured website."""
    start_ms, end_ms = _range_ms(now_ms)
    query = urllib.parse.urlencode({"startAt": start_ms, "endAt": end_ms})
    stats_url = f"{api_base}/websites/{website_id}/stats?{query}"
    stats = http_fetch(stats_url, token)
    if not isinstance(stats, dict):
        raise ValueError("Umami stats response was not an object")

    referrers = _metrics_rows(
        token=token,
        website_id=website_id,
        api_base=api_base,
        start_ms=start_ms,
        end_ms=end_ms,
        metric_type="referrer",
        limit=10,
        http_fetch=http_fetch,
    )
    pages_raw = _metrics_rows(
        token=token,
        website_id=website_id,
        api_base=api_base,
        start_ms=start_ms,
        end_ms=end_ms,
        metric_type="path",
        limit=10,
        http_fetch=http_fetch,
    )
    countries_raw = _metrics_rows(
        token=token,
        website_id=website_id,
        api_base=api_base,
        start_ms=start_ms,
        end_ms=end_ms,
        metric_type="country",
        limit=10,
        http_fetch=http_fetch,
    )

    return {
        "ok": True,
        "configured": True,
        "message": None,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
        "range": {"start_at_ms": start_ms, "end_at_ms": end_ms},
        "pageviews": _metric_value(stats.get("pageviews")),
        "visitors": _metric_value(stats.get("visitors")),
        "referrers": referrers,
        "pages": [{"path": row["name"], "visitors": row["visitors"]} for row in pages_raw],
        "countries": [{"code": row["name"], "visitors": row["visitors"]} for row in countries_raw],
        "source": "umami",
    }


def reset_audience_cache() -> None:
    global _cache, _cache_at
    with _cache_lock:
        _cache = None
        _cache_at = 0.0


def audience_snapshot(*, force: bool = False, now: Optional[float] = None) -> Dict[str, Any]:
    """Return Umami audience data, cached for ~60s when configured."""
    global _cache, _cache_at
    token, website_id, api_base = _env_config()
    if not token or not website_id:
        return _unconfigured_payload()

    ts = time.time() if now is None else float(now)
    with _cache_lock:
        if not force and _cache is not None and ts - _cache_at < CACHE_SECONDS:
            payload = dict(_cache)
            payload["cached"] = True
            return payload

    try:
        payload = fetch_audience_from_umami(
            token=token,
            website_id=website_id,
            api_base=api_base,
            now_ms=int(ts * 1000),
        )
        payload["cached"] = False
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
        payload = {
            "ok": False,
            "configured": True,
            "message": f"Umami request failed: {exc}",
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
            "pageviews": None,
            "visitors": None,
            "referrers": [],
            "pages": [],
            "countries": [],
            "source": "umami",
            "cached": False,
        }

    with _cache_lock:
        _cache = payload
        _cache_at = ts
    return payload
