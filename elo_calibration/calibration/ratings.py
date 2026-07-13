"""Per-game ELO ladder for engine calibration."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from chess_harness.opponents import Opponent, get_catalog
from chess_harness.rating_math import k_factor, update_elo as rating_update_elo

DEFAULT_FLOATING_ELO = 500.0
DEFAULT_K_FACTOR = 48


def expected_score(white_elo: float, black_elo: float) -> float:
    return 1.0 / (1.0 + math.pow(10, (black_elo - white_elo) / 400.0))


def is_anchor(opponent: Opponent) -> bool:
    """Stockfish catalog tiers are fixed reference ratings."""
    return opponent.type == "stockfish"


def white_score_from_result(result: str) -> float:
    if result == "1-0":
        return 1.0
    if result == "0-1":
        return 0.0
    return 0.5


@dataclass
class RatingUpdate:
    opponent_id: str
    elo_before: float
    elo_after: float
    elo_delta: float
    games_played: int


@dataclass
class GameRecord:
    game_index: int
    white_id: str
    black_id: str
    result: str
    white_elo_before: float
    black_elo_before: float
    updates: List[RatingUpdate] = field(default_factory=list)
    ts: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class CalibrationLadder:
    """Floating ratings for non-Stockfish engines; Stockfish stays at catalog ELO."""

    floating_start: float = DEFAULT_FLOATING_ELO
    k_factor: int = DEFAULT_K_FACTOR
    ratings: Dict[str, float] = field(default_factory=dict)
    games_played: Dict[str, int] = field(default_factory=dict)
    history: List[Dict[str, Any]] = field(default_factory=list)
    game_log: List[GameRecord] = field(default_factory=list)

    def _catalog(self):
        return get_catalog()

    def _opponent(self, opponent_id: str) -> Opponent:
        return self._catalog().get(opponent_id)

    def initial_rating(self, opponent_id: str) -> float:
        opp = self._opponent(opponent_id)
        if is_anchor(opp):
            return float(opp.elo)
        return self.floating_start

    def ensure_player(self, opponent_id: str) -> None:
        if opponent_id not in self.ratings:
            self.ratings[opponent_id] = self.initial_rating(opponent_id)
            self.games_played[opponent_id] = 0

    def get_rating(self, opponent_id: str) -> float:
        self.ensure_player(opponent_id)
        return self.ratings[opponent_id]

    def record_game(self, white_id: str, black_id: str, result: str) -> GameRecord:
        self.ensure_player(white_id)
        self.ensure_player(black_id)
        white_elo = self.ratings[white_id]
        black_elo = self.ratings[black_id]
        white_score = white_score_from_result(result)

        updates: List[RatingUpdate] = []
        white_opp = self._opponent(white_id)
        black_opp = self._opponent(black_id)

        if not is_anchor(white_opp):
            exp = expected_score(white_elo, black_elo)
            k = k_factor(self.games_played[white_id])
            after = white_elo + k * (white_score - exp)
            updates.append(
                RatingUpdate(
                    opponent_id=white_id,
                    elo_before=white_elo,
                    elo_after=after,
                    elo_delta=after - white_elo,
                    games_played=self.games_played[white_id] + 1,
                )
            )
            self.ratings[white_id] = after
            self.games_played[white_id] += 1

        if not is_anchor(black_opp):
            exp = expected_score(black_elo, white_elo)
            k = k_factor(self.games_played[black_id])
            after = black_elo + k * ((1.0 - white_score) - exp)
            updates.append(
                RatingUpdate(
                    opponent_id=black_id,
                    elo_before=black_elo,
                    elo_after=after,
                    elo_delta=after - black_elo,
                    games_played=self.games_played[black_id] + 1,
                )
            )
            self.ratings[black_id] = after
            self.games_played[black_id] += 1

        record = GameRecord(
            game_index=len(self.game_log) + 1,
            white_id=white_id,
            black_id=black_id,
            result=result,
            white_elo_before=white_elo,
            black_elo_before=black_elo,
            updates=updates,
        )
        self.game_log.append(record)
        self.history.append(
            {
                "game_index": record.game_index,
                "white": white_id,
                "black": black_id,
                "result": result,
                "ratings": dict(self.ratings),
            }
        )
        return record

    def floating_players(self) -> List[str]:
        return sorted(
            oid for oid in self.ratings if not is_anchor(self._opponent(oid))
        )

    def anchor_players(self) -> List[str]:
        return sorted(oid for oid in self.ratings if is_anchor(self._opponent(oid)))

    def prune_removed_opponents(self) -> List[str]:
        """Drop ladder rows for opponent ids no longer in the catalog."""
        catalog = self._catalog()
        removed: List[str] = []
        for oid in list(self.ratings):
            if catalog.try_get(oid) is None:
                self.ratings.pop(oid, None)
                self.games_played.pop(oid, None)
                removed.append(oid)
        return removed

    def rating_table(self) -> List[Dict[str, Any]]:
        rows = []
        catalog = self._catalog()
        for oid in sorted(self.ratings):
            opp = catalog.try_get(oid)
            if opp is None:
                continue
            rows.append(
                {
                    "id": oid,
                    "elo": round(self.ratings[oid]),
                    "elo_exact": round(self.ratings[oid], 2),
                    "games": self.games_played.get(oid, 0),
                    "anchor": is_anchor(opp),
                    "catalog_elo": opp.elo,
                }
            )
        return rows

    def stabilization_hint(self, window: int = 10) -> Dict[str, Any]:
        """Rough volatility over the last N games per floating player."""
        if len(self.history) < 2:
            return {"window": window, "players": {}}
        recent = self.history[-window:]
        vol: Dict[str, List[float]] = {}
        for entry in recent:
            for oid, elo in entry["ratings"].items():
                if is_anchor(self._opponent(oid)):
                    continue
                vol.setdefault(oid, []).append(elo)
        summary = {}
        for oid, series in vol.items():
            if len(series) < 2:
                summary[oid] = {"delta_range": 0.0, "games_in_window": len(series)}
                continue
            summary[oid] = {
                "delta_range": round(max(series) - min(series), 1),
                "games_in_window": len(series),
                "latest": round(series[-1]),
            }
        return {"window": window, "players": summary}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "floating_start": self.floating_start,
            "k_factor": self.k_factor,
            "ratings": {k: round(v, 2) for k, v in self.ratings.items()},
            "games_played": dict(self.games_played),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CalibrationLadder":
        ladder = cls(
            floating_start=float(data.get("floating_start", DEFAULT_FLOATING_ELO)),
            k_factor=int(data.get("k_factor", DEFAULT_K_FACTOR)),
        )
        for oid, elo in data.get("ratings", {}).items():
            ladder.ratings[oid] = float(elo)
        ladder.games_played = {k: int(v) for k, v in data.get("games_played", {}).items()}
        return ladder

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "CalibrationLadder":
        if not path.exists():
            return cls()
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def append_game_log(self, path: Path, record: GameRecord) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "game_index": record.game_index,
            "ts": record.ts,
            "white": record.white_id,
            "black": record.black_id,
            "result": record.result,
            "white_elo_before": record.white_elo_before,
            "black_elo_before": record.black_elo_before,
            "updates": [
                {
                    "opponent_id": u.opponent_id,
                    "elo_before": round(u.elo_before, 2),
                    "elo_after": round(u.elo_after, 2),
                    "elo_delta": round(u.elo_delta, 2),
                    "games_played": u.games_played,
                }
                for u in record.updates
            ],
        }
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload) + "\n")
