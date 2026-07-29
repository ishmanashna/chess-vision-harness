"""Shared high-entropy game id minting."""

from __future__ import annotations

import secrets

__all__ = ["new_game_id"]


def new_game_id() -> str:
    """Mint an unguessable game id."""
    return f"game-{secrets.token_urlsafe(16)}"
