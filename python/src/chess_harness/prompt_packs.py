"""Prompt pack registry for local prompt-test games."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from .paths import project_root

__all__ = [
    "PromptPack",
    "assert_creatable",
    "is_committee_state",
    "is_packed_result_row",
    "is_packed_state",
    "load_pack",
    "pack_title",
    "render_committee_brief",
    "render_overlay_brief",
]


@dataclass(frozen=True)
class PromptPack:
    id: str
    kind: str
    seats: Optional[int]
    body: str
    body_hash: str
    title: str


def _packs_dir() -> Path:
    return project_root() / "config" / "prompt_packs"


def _load_index() -> Dict[str, Any]:
    path = _packs_dir() / "index.json"
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def load_pack(pack_id: str) -> PromptPack:
    index = _load_index()
    packs = index.get("packs", {})
    if pack_id not in packs:
        raise ValueError(f"Unknown prompt pack: {pack_id}")

    meta = packs[pack_id]
    body_path = _packs_dir() / f"{pack_id}.txt"
    body = body_path.read_text(encoding="utf-8")
    body_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()
    seats = meta.get("seats")
    return PromptPack(
        id=pack_id,
        kind=str(meta["kind"]),
        seats=int(seats) if seats is not None else None,
        body=body,
        body_hash=body_hash,
        title=str(meta.get("title") or pack_id),
    )


def pack_title(pack_id: str) -> str:
    """Display title from index when known; otherwise the pack id."""
    index = _load_index()
    meta = index.get("packs", {}).get(pack_id)
    if meta and meta.get("title"):
        return str(meta["title"])
    return pack_id


def assert_creatable(pack_id: str) -> PromptPack:
    return load_pack(pack_id)


def is_committee_state(state: Dict[str, Any]) -> bool:
    """True when a live game uses committee (vote-based) play."""
    return state.get("prompt_pack_kind") == "committee"


def _overlay_rules_text() -> str:
    path = _packs_dir() / "_rules.txt"
    return path.read_text(encoding="utf-8")


def _committee_rules_text() -> str:
    path = _packs_dir() / "_committee_rules.txt"
    return path.read_text(encoding="utf-8")


def _fill_brief_placeholders(
    text: str,
    *,
    game_id: str,
    board_path: str,
    model_id: str,
    prompt_pack: str,
    seat: Optional[int] = None,
) -> str:
    filled = (
        text.replace("{game_id}", game_id)
        .replace("{board_path}", board_path)
        .replace("{model_id}", model_id)
        .replace("{prompt_pack}", prompt_pack)
    )
    if seat is not None:
        filled = filled.replace("{seat}", str(seat))
    return filled


def render_overlay_brief(
    pack: PromptPack,
    *,
    game_id: str,
    board_path: str,
    model_id: str,
) -> str:
    """Overlay brief: shared rules block, then pack-specific turn instructions."""
    rules = _fill_brief_placeholders(
        _overlay_rules_text(),
        game_id=game_id,
        board_path=board_path,
        model_id=model_id,
        prompt_pack=pack.id,
    )
    body = _fill_brief_placeholders(
        pack.body,
        game_id=game_id,
        board_path=board_path,
        model_id=model_id,
        prompt_pack=pack.id,
    )
    return rules + "\n\n" + body


def render_committee_brief(
    pack: PromptPack,
    *,
    game_id: str,
    board_path: str,
    model_id: str,
    seat: int,
) -> str:
    """Committee brief: shared committee rules, then pack body, with seat filled."""
    rules = _fill_brief_placeholders(
        _committee_rules_text(),
        game_id=game_id,
        board_path=board_path,
        model_id=model_id,
        prompt_pack=pack.id,
        seat=seat,
    )
    body = _fill_brief_placeholders(
        pack.body,
        game_id=game_id,
        board_path=board_path,
        model_id=model_id,
        prompt_pack=pack.id,
        seat=seat,
    )
    return rules + "\n\n" + body


def is_packed_state(state: Dict[str, Any]) -> bool:
    """True when a live game state carries a prompt-test pack tag."""
    return bool(state.get("prompt_pack"))


def is_packed_result_row(row: Dict[str, Any]) -> bool:
    """True when a results.jsonl row is from a prompt-test packed game."""
    return bool(row.get("prompt_pack"))
