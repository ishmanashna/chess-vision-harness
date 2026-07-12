"""Thin wrapper around harness opponent engines."""

from __future__ import annotations

import chess

from chess_harness.engine import OpponentEngineManager, configure_opponent_strength
from chess_harness.opponents import get_catalog

from .play_config import PlayConfig


def _harness_override(config: PlayConfig) -> dict:
    override: dict = {}
    if config.depth is not None:
        override["depth"] = config.depth
    if config.movetime_ms != 100:
        override["movetime_ms"] = config.movetime_ms
    if config.random_move_pct > 0:
        override["random_move_pct"] = config.random_move_pct
    return override


class EnginePlayer:
    def __init__(
        self,
        opponent_id: str,
        config: PlayConfig | None = None,
        *,
        uci_timeout: float = 10.0,
    ):
        self.opponent_id = opponent_id
        self.config = config or PlayConfig()
        self.uci_timeout = uci_timeout
        self.catalog = get_catalog()
        self.opponent = self.catalog.get(opponent_id)
        self._mgr = OpponentEngineManager(uci_timeout=uci_timeout)

    def play(self, board: chess.Board) -> chess.Move:
        override = _harness_override(self.config)
        result = self._mgr.play(
            self.opponent,
            board,
            time_limit=self.config.movetime_ms / 1000.0,
            harness_override=override or None,
        )
        return result.move

    def configure_snapshot(self) -> dict:
        if self.opponent.type == "random":
            return {"type": "random"}
        adapter = self._mgr.get_adapter(self.opponent)
        snapshot = configure_opponent_strength(adapter.engine, self.opponent)
        if self.opponent.harness:
            snapshot["harness"] = dict(self.opponent.harness)
        return snapshot

    def release(self) -> None:
        self._mgr.release()
