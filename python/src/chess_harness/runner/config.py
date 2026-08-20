"""Load runner slot configuration."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..models import normalize_observation, validate_observation
from .paths import default_config_path

_VALID_KINDS = frozenset({"ave", "puzzles", "identify"})


def validate_kind(raw: Any) -> str:
    kind = str(raw or "ave").strip().lower()
    if kind not in _VALID_KINDS:
        raise ValueError(f"invalid kind '{kind}' — expected ave, puzzles, or identify")
    return kind


@dataclass(frozen=True)
class SlotConfig:
    inscribed_id: str
    provider: str
    observation: str
    provider_model: str
    base_url: str
    env_key: str
    rpm: int
    rpd: int
    kind: str = "ave"
    opponent: Optional[str] = None
    agent_color: Optional[str] = None
    jpeg_max_side: Optional[int] = None
    puzzle_rating_min: Optional[int] = None
    puzzle_rating_max: Optional[int] = None
    puzzle_theme: Optional[str] = None
    identify_rating_min: Optional[int] = None
    identify_rating_max: Optional[int] = None

    @property
    def is_stub(self) -> bool:
        return self.provider.strip().lower() in {"stub", "fake"}


@dataclass(frozen=True)
class RunnerConfig:
    version: int
    max_concurrent_games: int
    harness_base_url: str
    slots: List[SlotConfig]
    source_path: Path


def _resolve_harness_base(raw: Any) -> str:
    env = os.getenv("HARNESS_BASE_URL", "").strip()
    if env:
        return env.rstrip("/")
    if isinstance(raw, str) and raw.strip():
        return raw.strip().rstrip("/")
    return "http://127.0.0.1:8765"


def _parse_slot(raw: Dict[str, Any]) -> SlotConfig:
    inscribed_id = str(raw.get("inscribed_id") or "").strip()
    if not inscribed_id:
        raise ValueError("slot missing inscribed_id")
    provider = str(raw.get("provider") or "stub").strip().lower()
    observation = validate_observation(raw.get("observation"))
    provider_model = str(raw.get("provider_model") or raw.get("model") or inscribed_id).strip()
    base_url = str(raw.get("base_url") or "").strip().rstrip("/")
    env_key = str(raw.get("env_key") or "").strip()
    rpm = int(raw.get("rpm") or 60)
    rpd = int(raw.get("rpd") or 500)
    opponent = raw.get("opponent")
    opponent_id = str(opponent).strip() if opponent else None
    color_raw = raw.get("agent_color")
    agent_color = str(color_raw).strip().lower() if color_raw else None
    if agent_color not in {None, "white", "black"}:
        raise ValueError(f"invalid agent_color '{agent_color}'")
    jpeg_raw = raw.get("jpeg_max_side")
    jpeg_max_side = int(jpeg_raw) if jpeg_raw is not None else None
    kind = validate_kind(raw.get("kind"))
    puzzle_rating_min = raw.get("puzzle_rating_min")
    puzzle_rating_max = raw.get("puzzle_rating_max")
    puzzle_theme_raw = raw.get("puzzle_theme")
    identify_rating_min = raw.get("identify_rating_min")
    identify_rating_max = raw.get("identify_rating_max")
    return SlotConfig(
        inscribed_id=inscribed_id,
        provider=provider,
        observation=normalize_observation(observation),
        provider_model=provider_model,
        base_url=base_url,
        env_key=env_key,
        rpm=max(1, rpm),
        rpd=max(1, rpd),
        kind=kind,
        opponent=opponent_id,
        agent_color=agent_color,
        jpeg_max_side=jpeg_max_side,
        puzzle_rating_min=int(puzzle_rating_min) if puzzle_rating_min is not None else None,
        puzzle_rating_max=int(puzzle_rating_max) if puzzle_rating_max is not None else None,
        puzzle_theme=str(puzzle_theme_raw).strip() if puzzle_theme_raw else None,
        identify_rating_min=int(identify_rating_min) if identify_rating_min is not None else None,
        identify_rating_max=int(identify_rating_max) if identify_rating_max is not None else None,
    )


def load_runner_config(path: Path | None = None) -> RunnerConfig:
    config_path = path or default_config_path()
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("runner config must be a JSON object")
    slots_raw = payload.get("slots") or []
    if not isinstance(slots_raw, list):
        raise ValueError("runner config slots must be a list")
    slots = [_parse_slot(item) for item in slots_raw if isinstance(item, dict)]
    return RunnerConfig(
        version=int(payload.get("version") or 1),
        max_concurrent_games=max(1, int(payload.get("max_concurrent_games") or 1)),
        harness_base_url=_resolve_harness_base(payload.get("harness_base_url")),
        slots=slots,
        source_path=config_path,
    )
