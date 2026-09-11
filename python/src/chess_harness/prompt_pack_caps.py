"""Prompt-pack capability gates for F/G experiment tools."""

from __future__ import annotations

from typing import Any, Dict, FrozenSet

CAP_LEGAL = "legal"
CAP_IMAGINE = "imagine"

# Pack id → enabled capabilities. Adding pack H later only requires a row here.
_PACK_CAPS: Dict[str, FrozenSet[str]] = {
    "f": frozenset({CAP_LEGAL}),
    "g": frozenset({CAP_IMAGINE}),
}


def pack_capabilities(pack_id: str | None) -> FrozenSet[str]:
    if not pack_id:
        return frozenset()
    return _PACK_CAPS.get(str(pack_id), frozenset())


def pack_allows_capability(state: Dict[str, Any], capability: str) -> bool:
    return capability in pack_capabilities(state.get("prompt_pack"))


def reject_capability(capability: str) -> Dict[str, Any]:
    if capability == CAP_LEGAL:
        message = "chess-harness legal is not available for this game"
    elif capability == CAP_IMAGINE:
        message = "chess-harness imagine is not available for this game"
    else:
        message = f"capability {capability!r} is not available for this game"
    return {"ok": False, "error": message}
