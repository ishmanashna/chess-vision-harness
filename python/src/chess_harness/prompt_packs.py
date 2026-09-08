"""Prompt pack registry for local prompt-test games."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

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
    seat_packs: Optional[Tuple[str, ...]] = None


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
    seat_count = int(seats) if seats is not None else None
    raw_seat_packs = meta.get("seat_packs")
    seat_packs: Optional[Tuple[str, ...]] = None
    if raw_seat_packs is not None:
        if not isinstance(raw_seat_packs, list) or not raw_seat_packs:
            raise ValueError(f"prompt pack {pack_id}: seat_packs must be a non-empty list")
        seat_packs = tuple(str(item) for item in raw_seat_packs)
        if seat_count is not None and len(seat_packs) != seat_count:
            raise ValueError(
                f"prompt pack {pack_id}: seat_packs length must match seats"
            )
        for overlay_id in seat_packs:
            if overlay_id == pack_id:
                raise ValueError(f"prompt pack {pack_id}: seat_packs cannot include itself")
            if overlay_id not in packs:
                raise ValueError(f"Unknown prompt pack: {overlay_id}")
            overlay_kind = str(packs[overlay_id].get("kind") or "")
            if overlay_kind != "overlay":
                raise ValueError(
                    f"prompt pack {pack_id}: seat pack {overlay_id} must be overlay"
                )
    return PromptPack(
        id=pack_id,
        kind=str(meta["kind"]),
        seats=seat_count,
        body=body,
        body_hash=body_hash,
        title=str(meta.get("title") or pack_id),
        seat_packs=seat_packs,
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


def _rewrite_overlay_commands_for_committee(body: str, game_id: str, seat: int) -> str:
    """Point overlay 'send a move' lines at vote; never expose a legal-move list."""
    vote_cmd = f"chess-harness prompt-test vote {game_id} {seat}"
    return body.replace(f"chess-harness move {game_id}", vote_cmd).replace(
        f"python -m chess_harness move {game_id}", vote_cmd
    )


def _seat_overlay_body(pack: PromptPack, seat: int) -> str:
    if not pack.seat_packs:
        return ""
    if seat < 1 or seat > len(pack.seat_packs):
        raise ValueError(f"seat must be between 1 and {len(pack.seat_packs)}")
    return load_pack(pack.seat_packs[seat - 1]).body


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
    """Committee brief: rules, optional seat overlay (B/C/D), then vote protocol."""
    fill_kwargs = {
        "game_id": game_id,
        "board_path": board_path,
        "model_id": model_id,
        "prompt_pack": pack.id,
        "seat": seat,
    }
    rules = _fill_brief_placeholders(_committee_rules_text(), **fill_kwargs)
    overlay_src = _seat_overlay_body(pack, seat)
    sections = [rules]
    if overlay_src:
        overlay = _fill_brief_placeholders(overlay_src, **fill_kwargs)
        sections.append(_rewrite_overlay_commands_for_committee(overlay, game_id, seat))
    protocol = _fill_brief_placeholders(pack.body, **fill_kwargs)
    sections.append(protocol)
    return "\n\n".join(sections)


def is_packed_state(state: Dict[str, Any]) -> bool:
    """True when a live game state carries a prompt-test pack tag."""
    return bool(state.get("prompt_pack"))


def is_packed_result_row(row: Dict[str, Any]) -> bool:
    """True when a results.jsonl row is from a prompt-test packed game."""
    return bool(row.get("prompt_pack"))
