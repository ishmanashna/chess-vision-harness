"""Persist harness API keys per inscribed model (never committed)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from ..agent_http.transport import DEFAULT_USER_AGENT, decode_json, request_with_retries
from ..models import validate_observation
from .paths import keys_path

TransportFn = Any


def load_keys(path: Path | None = None) -> Dict[str, str]:
    key_file = path or keys_path()
    if not key_file.is_file():
        return {}
    try:
        payload = json.loads(key_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    out: Dict[str, str] = {}
    for model_id, value in payload.items():
        if isinstance(value, str) and value.strip():
            out[str(model_id)] = value.strip()
    return out


def save_keys(keys: Dict[str, str], path: Path | None = None) -> Path:
    key_file = path or keys_path()
    key_file.parent.mkdir(parents=True, exist_ok=True)
    key_file.write_text(json.dumps(keys, indent=2) + "\n", encoding="utf-8")
    return key_file


def ensure_harness_key(
    *,
    base_url: str,
    inscribed_id: str,
    observation: str,
    transport: TransportFn,
    path: Path | None = None,
) -> str:
    keys = load_keys(path)
    existing = keys.get(inscribed_id)
    if existing:
        return existing
    url = f"{base_url.rstrip('/')}/api/v1/agents"
    body = json.dumps(
        {
            "id": inscribed_id,
            "name": inscribed_id,
            "observation": validate_observation(observation),
        }
    ).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": DEFAULT_USER_AGENT,
    }
    status, _hdrs, content = request_with_retries(transport, "POST", url, headers, body)
    payload = decode_json(content) if content else {}
    if status >= 400 or not payload.get("ok"):
        message = str(payload.get("error") or content.decode("utf-8", errors="replace"))
        raise RuntimeError(f"failed to mint harness key for {inscribed_id}: {message}")
    api_key = str(payload.get("api_key") or "").strip()
    if not api_key:
        raise RuntimeError(f"mint response missing api_key for {inscribed_id}")
    keys[inscribed_id] = api_key
    save_keys(keys, path)
    return api_key
