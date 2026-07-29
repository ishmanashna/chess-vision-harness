"""Tests for shared game id minting."""

from __future__ import annotations

import re

from chess_harness.game_ids import new_game_id

_GAME_ID_RE = re.compile(r"^game-[A-Za-z0-9_-]{16,}$")


def test_new_game_id_high_entropy():
    ids = {new_game_id() for _ in range(50)}
    assert len(ids) == 50
    for game_id in ids:
        assert _GAME_ID_RE.match(game_id), game_id
