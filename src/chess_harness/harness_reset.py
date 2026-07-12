"""Operator-only harness maintenance (reset, legacy cleanup)."""

from __future__ import annotations

import shutil

from .game_manager import GameManager
from .models import ModelRegistry
from .paths import resolve_base_dir


def harness_reset(*, confirm: bool = False) -> int:
    """
    Wipe runtime harness data: all games, results, inscribed models, legacy elo.json.

    Does not touch opponents, Stockfish, or version-controlled config outside models.json.
    """
    if not confirm:
        print("This permanently wipes:")
        print("  - all games in .chess_harness/games/")
        print("  - results.jsonl")
        print("  - all inscribed models in models.json")
        print("  - legacy elo.json (if present)")
        print()
        print("Re-run with --yes to confirm:")
        print("  python play.py harness reset --yes")
        return 1

    gm = GameManager()
    if gm.games_dir.exists():
        for game_dir in gm.games_dir.iterdir():
            if game_dir.is_dir():
                shutil.rmtree(game_dir)

    gm.results_file.parent.mkdir(parents=True, exist_ok=True)
    gm.results_file.write_text("", encoding="utf-8")

    ModelRegistry().clear_all()

    legacy_elo = resolve_base_dir() / "elo.json"
    if legacy_elo.exists():
        legacy_elo.unlink()

    print("Harness reset complete.")
    print("  games: 0")
    print("  results: cleared")
    print("  models: none inscribed")
    return 0
