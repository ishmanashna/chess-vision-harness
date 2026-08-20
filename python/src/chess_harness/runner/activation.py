"""Slot activation rules."""

from __future__ import annotations

import os
from typing import Any, Dict

from .config import SlotConfig


def slot_is_active(slot: SlotConfig, probe_status: Dict[str, Dict[str, Any]]) -> bool:
    if slot.is_stub:
        return True
    env_key = slot.env_key.strip()
    if not env_key or not os.getenv(env_key, "").strip():
        return False
    row = probe_status.get(slot.inscribed_id)
    if not row or not row.get("ok"):
        return False
    return True
