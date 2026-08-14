"""Spectator game view shell for /g/{game_id} (static HTML in public-site/g/)."""

from __future__ import annotations

from pathlib import Path

from .paths import project_root

__all__ = ["CM_CHESSBOARD_VERSION", "CM_CDN", "load_game_view_shell"]

CM_CHESSBOARD_VERSION = "8.7.2"
CM_CDN = f"https://cdn.jsdelivr.net/npm/cm-chessboard@{CM_CHESSBOARD_VERSION}"


def load_game_view_shell() -> str:
    """Return the static /g/ shell HTML (Phase 9c)."""
    path = project_root() / "public-site" / "g" / "index.html"
    return path.read_text(encoding="utf-8")
