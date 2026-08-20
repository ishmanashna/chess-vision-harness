"""Probe configured provider slots."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import chess

from ..board_text import format_board_text
from ..models import OBSERVATION_TEXT
from .adapters import build_adapter
from .config import RunnerConfig, SlotConfig, load_runner_config
from .probe_state import load_probe_status, mark_probe

TransportFn = Any

_PROBE_BOARD = format_board_text(chess.Board())
_PROBE_PNG = None


def _probe_png() -> bytes:
    global _PROBE_PNG
    if _PROBE_PNG is None:
        from ..render_pillow import ChessBoardRenderer

        _PROBE_PNG = ChessBoardRenderer().render_board_bytes(chess.Board())
    return _PROBE_PNG


def probe_slot(slot: SlotConfig, transport: TransportFn, *, status_path: Path | None = None) -> Dict[str, Any]:
    if slot.is_stub:
        mark_probe(slot.inscribed_id, ok=True, message="stub ok", path=status_path)
        return {"inscribed_id": slot.inscribed_id, "ok": True, "message": "stub ok"}

    env_key = slot.env_key.strip()
    if not env_key or not os.getenv(env_key, "").strip():
        mark_probe(slot.inscribed_id, ok=False, message="missing env key", path=status_path)
        return {"inscribed_id": slot.inscribed_id, "ok": False, "message": "missing env key"}

    board_png = None if slot.observation == OBSERVATION_TEXT else _probe_png()
    try:
        adapter = build_adapter(slot, transport)
        adapter.probe(board_text=_PROBE_BOARD, board_png=board_png)
    except Exception as exc:
        mark_probe(slot.inscribed_id, ok=False, message=str(exc), path=status_path)
        return {"inscribed_id": slot.inscribed_id, "ok": False, "message": str(exc)}

    mark_probe(slot.inscribed_id, ok=True, message="probe ok", path=status_path)
    return {"inscribed_id": slot.inscribed_id, "ok": True, "message": "probe ok"}


def run_probe(
    *,
    config_path: Path | None = None,
    transport: TransportFn,
    harness_dir: Path | None = None,
) -> List[Dict[str, Any]]:
    config = load_runner_config(config_path)
    status_path = (
        Path(harness_dir) / "runner" / "probe_status.json" if harness_dir else None
    )
    return [probe_slot(slot, transport, status_path=status_path) for slot in config.slots]
