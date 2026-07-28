"""
Opponent catalog: tiny UCI engines (CCRL-rated) and Stockfish UCI_Elo tiers.
"""

from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from .paths import project_root, resolve_opponents_file


STOCKFISH_ELO_MIN = 1320
STOCKFISH_ELO_MAX = 3190
STOCKFISH_SKILL_MAX = 20


def stockfish_skill_to_elo(skill: int) -> int:
    """Map Stockfish UCI skill level 0–20 to official UCI_Elo range."""
    if not 0 <= skill <= STOCKFISH_SKILL_MAX:
        raise ValueError(f"Stockfish skill must be 0–{STOCKFISH_SKILL_MAX}")
    return round(STOCKFISH_ELO_MIN + skill * (STOCKFISH_ELO_MAX - STOCKFISH_ELO_MIN) / STOCKFISH_SKILL_MAX)


LaunchCommand = Union[str, List[str]]


@dataclass(frozen=True)
class Opponent:
    id: str
    display_name: str
    type: str  # "uci" | "uci_elo" | "uci_harness" | "stockfish" | "stockfish_harness" | "inverse_sf" | "random"
    elo: int
    binary: Optional[str] = None
    command: Optional[List[str]] = None
    uci_elo: Optional[int] = None
    skill_level: Optional[int] = None
    rating_source: str = "ccrl"
    ccrl_name: Optional[str] = None
    harness: Optional[Dict[str, Any]] = None
    inverse: Optional[Dict[str, Any]] = None
    rating_note: Optional[str] = None
    enabled: bool = True

    def format_label(self) -> str:
        """Public label for spectator/PGN, e.g. 'MinimalChess 0.2 (909)'."""
        return f"{self.display_name} ({self.elo})"

    def resolve_binary_path(self) -> Path:
        if not self.binary:
            raise ValueError(f"Opponent {self.id} has no binary path")
        path = Path(self.binary)
        if not path.is_absolute():
            path = project_root() / path
        return path

    def resolve_launch_command(self) -> LaunchCommand:
        """UCI process argv: executable path or command list (e.g. node script)."""
        if self.command:
            resolved: List[str] = []
            for part in self.command:
                candidate = Path(part)
                if not candidate.is_absolute() and candidate.suffix in {".exe", ".js", ".bat", ".cmd"}:
                    resolved.append(str(project_root() / part))
                else:
                    resolved.append(part)
            return resolved
        return str(self.resolve_binary_path())


def _parse_opponent(raw: Dict[str, Any]) -> Opponent:
    return Opponent(
        id=raw["id"],
        display_name=raw["display_name"],
        type=raw["type"],
        elo=int(raw["elo"]),
        binary=raw.get("binary"),
        command=raw.get("command"),
        uci_elo=raw.get("uci_elo"),
        skill_level=raw.get("skill_level"),
        rating_source=raw.get("rating_source", "ccrl"),
        ccrl_name=raw.get("ccrl_name"),
        harness=raw.get("harness"),
        inverse=raw.get("inverse"),
        rating_note=raw.get("rating_note"),
        enabled=bool(raw.get("enabled", True)),
    )


class OpponentCatalog:
    """Loaded opponents.json with ELO-weighted selection."""

    def __init__(self, path: Optional[Path] = None):
        self.path = path or resolve_opponents_file()
        self._data = self._load()
        self.matching = self._data.get("matching", {})
        self.opponents: List[Opponent] = [
            _parse_opponent(o) for o in self._data.get("opponents", [])
        ]
        self._by_id: Dict[str, Opponent] = {o.id: o for o in self.opponents}

    def _load(self) -> Dict[str, Any]:
        if not self.path.exists():
            raise FileNotFoundError(f"Opponent catalog not found: {self.path}")
        return json.loads(self.path.read_text(encoding="utf-8"))

    def get(self, opponent_id: str) -> Opponent:
        if opponent_id not in self._by_id:
            raise ValueError(f"Unknown opponent: {opponent_id}")
        return self._by_id[opponent_id]

    def try_get(self, opponent_id: str) -> Optional[Opponent]:
        return self._by_id.get(opponent_id)

    def list_opponents(self) -> List[Opponent]:
        return list(self.opponents)

    def list_eligible_opponents(self) -> List[Opponent]:
        return [o for o in self.opponents if self.is_eligible(o)]

    def is_eligible(self, opp: Opponent) -> bool:
        return opp.enabled and self._is_playable(opp)

    def set_enabled(self, opponent_id: str, enabled: bool) -> Opponent:
        found = False
        for raw in self._data.get("opponents", []):
            if raw.get("id") == opponent_id:
                if enabled:
                    raw.pop("enabled", None)
                else:
                    raw["enabled"] = False
                found = True
                break
        if not found:
            raise ValueError(f"Unknown opponent: {opponent_id}")
        self.path.write_text(json.dumps(self._data, indent=2) + "\n", encoding="utf-8")
        self._reload_from_disk()
        reload_catalog()
        return self.get(opponent_id)

    def _reload_from_disk(self) -> None:
        self._data = self._load()
        self.opponents = [_parse_opponent(o) for o in self._data.get("opponents", [])]
        self._by_id = {o.id: o for o in self.opponents}

    def reference_opponents(self) -> List[Opponent]:
        """Subset for spectator reference table (spread across ELO range)."""
        tiny = [o for o in self.opponents if o.type in (
            "uci", "uci_elo", "uci_harness", "stockfish_harness", "inverse_sf", "random"
        )]
        stockfish = [o for o in self.opponents if o.type == "stockfish"]
        # Sample stockfish at 0, 5, 10, 15, 20
        sf_ids = {f"stockfish:{s}" for s in (0, 5, 10, 15, 20)}
        sf_sample = [o for o in stockfish if o.id in sf_ids]
        return sorted(tiny + sf_sample, key=lambda o: o.elo)

    def select_by_elo(
        self,
        agent_elo: float,
        *,
        sigma_elo: Optional[float] = None,
        min_weight: Optional[float] = None,
        max_delta_elo: Optional[float] = None,
    ) -> Opponent:
        """Pick opponent weighted toward similar ELO (always, not just early games).

        Opponents farther than ``max_delta_elo`` get zero weight. If none remain
        in-band, fall back to the nearest eligible opponents only.
        """
        if not self.opponents:
            raise ValueError("Opponent catalog is empty")

        from .calibration_view import ladder_elo_for_opponent, merge_calibration_ratings

        sigma = float(sigma_elo if sigma_elo is not None else self.matching.get("sigma_elo", 150))
        floor_w = float(
            min_weight if min_weight is not None else self.matching.get("min_weight", 0.05)
        )
        max_delta = max_delta_elo
        if max_delta is None and "max_delta_elo" in self.matching:
            max_delta = float(self.matching["max_delta_elo"])
        calibration = merge_calibration_ratings()

        eligible: List[tuple[Opponent, float]] = []
        for opp in self.opponents:
            if not self.is_eligible(opp):
                continue
            delta = abs(ladder_elo_for_opponent(opp, calibration) - agent_elo)
            eligible.append((opp, delta))

        if not eligible:
            playable = [o for o in self.opponents if o.type == "stockfish" and o.enabled]
            if not playable:
                raise RuntimeError("No playable opponents in catalog")
            eligible = [
                (opp, abs(ladder_elo_for_opponent(opp, calibration) - agent_elo))
                for opp in playable
            ]

        in_band = (
            [(opp, delta) for opp, delta in eligible if delta <= max_delta]
            if max_delta is not None
            else list(eligible)
        )
        pool = in_band if in_band else sorted(eligible, key=lambda x: x[1])[:5]

        weights = [max(floor_w, math.exp(-delta / sigma)) for _opp, delta in pool]
        return random.choices([opp for opp, _ in pool], weights=weights, k=1)[0]

    @staticmethod
    def _is_playable(opp: Opponent) -> bool:
        if opp.type == "random":
            return True
        if opp.type in ("stockfish", "stockfish_harness"):
            return True
        if opp.type == "inverse_sf":
            return True
        if opp.type in ("uci", "uci_elo", "uci_harness"):
            if opp.command:
                script = Path(opp.command[-1])
                if not script.is_absolute():
                    script = project_root() / script
                return script.exists()
            if opp.binary:
                return opp.resolve_binary_path().exists()
        return False

    def resolve_opponent_id(
        self,
        opponent_id: Optional[str] = None,
        skill: Optional[int] = None,
        agent_elo: float = 500,
    ) -> str:
        """Resolve explicit opponent, legacy skill int, or ELO-weighted default."""
        if opponent_id:
            opp = self.get(opponent_id)
            if not opp.enabled:
                raise ValueError(f"Opponent '{opponent_id}' is disabled")
            return opponent_id
        if skill is not None:
            if skill < 0:
                raise ValueError(
                    "Negative Stockfish skills are removed. "
                    "Use a catalog opponent below 1320 ELO (e.g. stockfish-handicap:noise17, random)."
                )
            if skill > STOCKFISH_SKILL_MAX:
                raise ValueError(f"Skill level must be 0–{STOCKFISH_SKILL_MAX}")
            oid = f"stockfish:{skill}"
            opp = self.get(oid)
            if not opp.enabled:
                raise ValueError(f"Opponent '{oid}' is disabled")
            return oid
        return self.select_by_elo(agent_elo).id


_catalog: Optional[OpponentCatalog] = None


def get_catalog() -> OpponentCatalog:
    global _catalog
    if _catalog is None:
        _catalog = OpponentCatalog()
    return _catalog


def reload_catalog() -> None:
    global _catalog
    _catalog = None


def opponent_elo_from_result(game: Dict[str, Any], catalog: Optional[OpponentCatalog] = None) -> Optional[int]:
    """Resolve opponent ELO from a results.jsonl row (new or legacy)."""
    cat = catalog or get_catalog()
    oid = game.get("opponent_id")
    if oid:
        try:
            from .calibration_view import ladder_elo_for_opponent_id

            return ladder_elo_for_opponent_id(oid, cat)
        except ValueError:
            pass
    if game.get("opponent_elo") is not None:
        return int(game["opponent_elo"])
    opponent_model = game.get("opponent_model")
    if opponent_model:
        from .models import ModelRegistry

        registry = ModelRegistry()
        canonical = registry.normalize_result_model(opponent_model)
        if canonical:
            return round(registry.get_elo(canonical))
    skill = game.get("skill")
    if skill is not None:
        from .elo import LEGACY_SKILL_ELO

        if skill in LEGACY_SKILL_ELO:
            return LEGACY_SKILL_ELO[skill]
        if skill >= 0:
            try:
                return cat.get(f"stockfish:{skill}").elo
            except ValueError:
                return stockfish_skill_to_elo(skill)
    return None
