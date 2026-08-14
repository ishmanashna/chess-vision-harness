"""
Chess engine adapters: opponent play and full-strength eval.
"""

from __future__ import annotations

import chess.engine
import random
from collections import OrderedDict
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol, Union

from .inverse_sf import play_inverse_sf_move
from .opponents import Opponent, stockfish_skill_to_elo
from .paths import resolve_stockfish

LaunchCommand = Union[str, List[str]]

STOCKFISH_RATED_POOL = "__stockfish_rated__"
STOCKFISH_EVAL_POOL = "__stockfish_eval__"


class EngineProtocol(Protocol):
    def play(self, board, time_limit: float = 0.1, depth: Optional[int] = None, skill=None):
        ...

    def evaluate(self, board, depth: int = 10):
        ...

    def quit(self):
        ...


def _is_patricia(opponent: Opponent) -> bool:
    """Legacy: Patricia used Skill_Level UCI option (no longer in catalog)."""
    binary = opponent.binary or ""
    return "patricia" in binary.lower()


def _adapter_pool_key(opponent: Opponent) -> str:
    """One subprocess per binary/launch command (not per catalog id)."""
    if opponent.type in ("stockfish", "stockfish_harness"):
        return STOCKFISH_RATED_POOL
    if opponent.type == "inverse_sf":
        return STOCKFISH_EVAL_POOL
    if opponent.type == "random":
        return "random"
    launch = opponent.resolve_launch_command()
    if isinstance(launch, list):
        parts = []
        for part in launch:
            p = Path(part)
            parts.append(str(p.resolve() if p.suffix in {".exe", ".js"} else part))
        return "|".join(parts)
    return str(Path(launch).resolve())


def force_terminate_uci_engine(engine: Any) -> None:
    """Best-effort UCI shutdown; always try to kill the child process (Windows-safe)."""
    if engine is None:
        return
    try:
        engine.quit()
    except Exception:
        pass
    try:
        engine.terminate()
    except Exception:
        pass
    for attr in ("process", "_process", "proc"):
        proc = getattr(engine, attr, None)
        if proc is not None:
            try:
                if proc.poll() is None:
                    proc.kill()
            except Exception:
                pass
            return
    transport = getattr(engine, "_transport", None)
    if transport is not None:
        for attr in ("_popen", "process", "_process"):
            proc = getattr(transport, attr, None)
            if proc is not None:
                try:
                    if proc.poll() is None:
                        proc.kill()
                except Exception:
                    pass
                return


def configure_opponent_strength(engine, opponent: Opponent) -> Dict[str, Any]:
    """
    Single source of truth for UCI strength options (harness + elo_calibration/).
    Returns snapshot dict for logging.
    """
    if engine is None:
        raise RuntimeError("Engine not initialized")

    if opponent.type in ("stockfish", "stockfish_harness"):
        skill = opponent.skill_level if opponent.skill_level is not None else 0
        uci_elo = opponent.uci_elo if opponent.uci_elo is not None else opponent.elo
        cfg: Dict[str, Any] = {
            "UCI_LimitStrength": True,
            "UCI_Elo": uci_elo,
            "Skill Level": skill,
        }
        engine.configure(cfg)
        if opponent.harness:
            cfg["harness"] = dict(opponent.harness)
        return cfg

    if opponent.type == "uci_elo":
        uci_elo = opponent.uci_elo if opponent.uci_elo is not None else opponent.elo
        cfg = {"UCI_LimitStrength": True, "UCI_Elo": uci_elo}
        if opponent.skill_level is not None and _is_patricia(opponent):
            cfg["Skill_Level"] = opponent.skill_level
        engine.configure(cfg)
        return cfg

    if opponent.type == "inverse_sf":
        engine.configure({"UCI_LimitStrength": False})
        return {"UCI_LimitStrength": False, "inverse": dict(opponent.inverse or {})}

    # plain uci / uci_harness — no strength options
    return {}


def merged_harness(opponent: Opponent, override: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    base = dict(opponent.harness or {})
    if override:
        base.update(override)
    return base


class UciEngineAdapter:
    """Generic UCI engine wrapper."""

    def __init__(self, launch_command: LaunchCommand, *, uci_timeout: float = 10.0):
        self.launch_command = launch_command
        self.uci_timeout = uci_timeout
        self.engine = None
        self._initialize_engine()

    def _initialize_engine(self):
        try:
            self.engine = chess.engine.SimpleEngine.popen_uci(
                self.launch_command, timeout=self.uci_timeout
            )
        except Exception as e:
            raise RuntimeError(f"Failed to initialize UCI engine ({self.launch_command}): {e}") from e

    def play(self, board, time_limit: float = 0.1, depth: Optional[int] = None, skill=None):
        if self.engine is None:
            raise RuntimeError("Engine not initialized")
        if depth is not None:
            wall = max(time_limit, 30.0)
            return self.engine.play(board, chess.engine.Limit(depth=depth, time=wall))
        return self.engine.play(board, chess.engine.Limit(time=time_limit))

    def evaluate(self, board, depth: int = 10):
        if self.engine is None or board.is_game_over():
            return None
        try:
            info = self.engine.analyse(board, chess.engine.Limit(depth=depth))
            return info["score"].white().score(mate_score=10000)
        except Exception:
            return None

    def quit(self):
        if self.engine is not None:
            engine = self.engine
            self.engine = None
            force_terminate_uci_engine(engine)

    def __del__(self):
        self.quit()


def play_opponent_move(
    adapter: UciEngineAdapter,
    opponent: Opponent,
    board,
    *,
    time_limit: float = 0.1,
    harness_override: Optional[Dict[str, Any]] = None,
):
    """Apply catalog harness (depth, movetime, random moves) then play."""
    harness = merged_harness(opponent, harness_override)
    random_pct = float(harness.get("random_move_pct", 0.0))
    if random_pct > 0 and random.random() < random_pct:
        move = random.choice(list(board.legal_moves))
        return chess.engine.PlayResult(move, None)

    depth = harness.get("depth")
    if harness.get("movetime_ms") is not None:
        time_limit = float(harness["movetime_ms"]) / 1000.0
    return adapter.play(board, time_limit=time_limit, depth=depth)


class RatedUciOpponentAdapter(UciEngineAdapter):
    """UCI engine with UCI_LimitStrength + UCI_Elo (Patricia, etc.)."""

    def __init__(
        self,
        launch_command: LaunchCommand,
        uci_elo: int,
        skill_level: Optional[int] = None,
        opponent: Optional[Opponent] = None,
        *,
        uci_timeout: float = 10.0,
    ):
        self.uci_elo = uci_elo
        self.skill_level = skill_level if skill_level is not None else 0
        self._opponent = opponent
        super().__init__(launch_command, uci_timeout=uci_timeout)
        self.configure_strength()

    def configure_strength(self) -> Dict[str, Any]:
        if self.engine is None:
            raise RuntimeError("Engine not initialized")
        if self._opponent is not None:
            return configure_opponent_strength(self.engine, self._opponent)
        cfg: Dict[str, Any] = {"UCI_LimitStrength": True, "UCI_Elo": self.uci_elo}
        if self.skill_level:
            cfg["Skill_Level"] = self.skill_level
        self.engine.configure(cfg)
        return cfg


class StockfishOpponentAdapter(RatedUciOpponentAdapter):
    """Stockfish configured as a rated opponent via UCI_LimitStrength + UCI_Elo."""

    def __init__(self, stockfish_path: Optional[str] = None, skill_level: int = 5, uci_elo: Optional[int] = None):
        self.skill_level = skill_level
        elo = uci_elo if uci_elo is not None else stockfish_skill_to_elo(skill_level)
        opp = Opponent(
            id=f"stockfish:{skill_level}",
            display_name="Stockfish 17.1",
            type="stockfish",
            elo=elo,
            uci_elo=elo,
            skill_level=skill_level,
            rating_source="stockfish_uci",
        )
        super().__init__(
            stockfish_path or resolve_stockfish(),
            uci_elo=elo,
            skill_level=skill_level,
            opponent=opp,
        )


class EvalEngineAdapter(UciEngineAdapter):
    """Full-strength Stockfish for position evaluation only."""

    def __init__(self, stockfish_path: Optional[str] = None):
        super().__init__(stockfish_path or resolve_stockfish())
        if self.engine is not None:
            self.engine.configure({"UCI_LimitStrength": False})


class OpponentEngineManager:
    """Spawn or reconfigure opponent engines; release() tears down all subprocesses."""

    def __init__(self, *, uci_timeout: float = 10.0):
        self.uci_timeout = uci_timeout
        self._current_id: Optional[str] = None
        self._adapters: OrderedDict[str, UciEngineAdapter] = OrderedDict()
        self._current_opponent: Optional[Opponent] = None

    def _spawn_adapter(self, opponent: Opponent) -> UciEngineAdapter:
        if opponent.type in ("stockfish", "stockfish_harness"):
            skill = opponent.skill_level if opponent.skill_level is not None else 0
            uci_elo = opponent.uci_elo if opponent.uci_elo is not None else opponent.elo
            return RatedUciOpponentAdapter(
                resolve_stockfish(),
                uci_elo=uci_elo,
                skill_level=skill,
                opponent=opponent,
                uci_timeout=self.uci_timeout,
            )
        if opponent.type == "inverse_sf":
            adapter = EvalEngineAdapter(resolve_stockfish())
            configure_opponent_strength(adapter.engine, opponent)
            return adapter
        if opponent.type == "uci_elo":
            uci_elo = opponent.uci_elo if opponent.uci_elo is not None else opponent.elo
            launch = opponent.resolve_launch_command()
            script = launch[-1] if isinstance(launch, list) else launch
            if not Path(script).exists():
                raise RuntimeError(
                    f"Opponent binary not found: {script}. "
                    f"Run scripts/fetch_opponents.py to download engines."
                )
            return RatedUciOpponentAdapter(
                launch, uci_elo=uci_elo, skill_level=opponent.skill_level, opponent=opponent,
                uci_timeout=self.uci_timeout,
            )
        if opponent.type in ("uci", "uci_harness"):
            launch = opponent.resolve_launch_command()
            script = launch[-1] if isinstance(launch, list) else launch
            if not Path(script).exists():
                raise RuntimeError(
                    f"Opponent binary not found: {script}. "
                    f"Run scripts/fetch_opponents.py to download engines."
                )
            return UciEngineAdapter(launch, uci_timeout=self.uci_timeout)
        raise ValueError(f"Unknown opponent type: {opponent.type}")

    def get_adapter(self, opponent: Opponent) -> UciEngineAdapter:
        if opponent.type == "random":
            raise ValueError("Random opponents do not use UCI adapters")

        pool_key = _adapter_pool_key(opponent)
        adapter = self._adapters.get(pool_key)
        if adapter is None:
            adapter = self._spawn_adapter(opponent)
            self._adapters[pool_key] = adapter
        else:
            self._adapters.move_to_end(pool_key)

        self._current_id = opponent.id
        self._current_opponent = opponent
        if opponent.type in ("stockfish", "stockfish_harness", "uci_elo", "inverse_sf"):
            configure_opponent_strength(adapter.engine, opponent)
        return adapter

    def live_adapter_count(self) -> int:
        return len(self._adapters)

    def trim(self, max_adapters: int) -> None:
        """Drop least-recently-used pooled adapters until at most max_adapters remain."""
        limit = max(0, int(max_adapters))
        while len(self._adapters) > limit:
            _key, adapter = self._adapters.popitem(last=False)
            adapter.quit()

    def release(self):
        for adapter in self._adapters.values():
            adapter.quit()
        self._adapters.clear()
        self._current_id = None
        self._current_opponent = None

    def play(
        self,
        opponent: Opponent,
        board,
        time_limit: float = 0.1,
        harness_override: Optional[Dict[str, Any]] = None,
    ):
        if opponent.type == "random":
            move = random.choice(list(board.legal_moves))
            return chess.engine.PlayResult(move, None)

        if opponent.type == "inverse_sf":
            adapter = self.get_adapter(opponent)
            move = play_inverse_sf_move(adapter.engine, board, opponent.inverse)
            return chess.engine.PlayResult(move, None)

        adapter = self.get_adapter(opponent)
        if opponent.type in ("stockfish", "stockfish_harness", "uci_elo"):
            configure_opponent_strength(adapter.engine, opponent)
        return play_opponent_move(
            adapter, opponent, board, time_limit=time_limit, harness_override=harness_override
        )


# Backward-compatible alias used by tests and MCP init
StockfishAdapter = StockfishOpponentAdapter
