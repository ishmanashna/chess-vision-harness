"""Per-side play and harness options for calibration games."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class PlayConfig:
    """How one engine plays a single move (and optional Stockfish harness tweaks)."""

    movetime_ms: int = 100
    depth: Optional[int] = None
    random_move_pct: float = 0.0

    @classmethod
    def from_dict(cls, raw: Optional[Dict[str, Any]], defaults: "PlayConfig") -> "PlayConfig":
        if not raw:
            return PlayConfig(
                movetime_ms=defaults.movetime_ms,
                depth=defaults.depth,
                random_move_pct=defaults.random_move_pct,
            )
        return PlayConfig(
            movetime_ms=int(raw.get("movetime_ms", defaults.movetime_ms)),
            depth=raw.get("depth", defaults.depth),
            random_move_pct=float(raw.get("random_move_pct", defaults.random_move_pct)),
        )


@dataclass
class MatchConfig:
    """One scheduled game between two catalog opponents."""

    white_id: str
    black_id: str
    max_plies: int = 200
    start_fen: str = "startpos"
    white: PlayConfig = field(default_factory=PlayConfig)
    black: PlayConfig = field(default_factory=PlayConfig)

    def to_dict(self) -> Dict[str, Any]:
        def pc(p: PlayConfig) -> Dict[str, Any]:
            return {
                "movetime_ms": p.movetime_ms,
                "depth": p.depth,
                "random_move_pct": p.random_move_pct,
            }

        return {
            "white_id": self.white_id,
            "black_id": self.black_id,
            "max_plies": self.max_plies,
            "start_fen": self.start_fen,
            "white": pc(self.white),
            "black": pc(self.black),
        }


def match_from_dict(raw: Dict[str, Any]) -> MatchConfig:
    def pc(d: Dict[str, Any]) -> PlayConfig:
        return PlayConfig(
            movetime_ms=int(d.get("movetime_ms", 100)),
            depth=d.get("depth"),
            random_move_pct=float(d.get("random_move_pct", 0.0)),
        )

    return MatchConfig(
        white_id=raw["white_id"],
        black_id=raw["black_id"],
        max_plies=int(raw.get("max_plies", 200)),
        start_fen=raw.get("start_fen", "startpos"),
        white=pc(raw.get("white", {})),
        black=pc(raw.get("black", {})),
    )
