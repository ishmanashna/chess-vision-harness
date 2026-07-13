"""Process-pool worker for parallel calibration games (Windows spawn-safe)."""

from __future__ import annotations


def play_match_worker(payload: dict) -> dict:
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    project = root.parent
    src = str(project / "src")
    if src not in sys.path:
        sys.path.insert(0, src)
    cal = str(root)
    if cal not in sys.path:
        sys.path.insert(0, cal)

    from calibration.game_loop import play_game
    from calibration.play_config import match_from_dict

    match = match_from_dict(payload)
    try:
        result = play_game(match)
        return {
            "white_id": match.white_id,
            "black_id": match.black_id,
            "result": result,
        }
    finally:
        from calibration.engine_player import release_all_engines

        release_all_engines()


def play_resilient_match_worker(payload: dict) -> dict:
    """Windows spawn-safe worker for continuous calibration games."""
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    project = root.parent
    src = str(project / "src")
    if src not in sys.path:
        sys.path.insert(0, src)
    cal = str(root)
    if cal not in sys.path:
        sys.path.insert(0, cal)

    from calibration.play_config import match_from_dict
    from calibration.resilient_game import play_game_resilient

    match = match_from_dict(payload)
    try:
        result = play_game_resilient(match)
        return {
            "white_id": match.white_id,
            "black_id": match.black_id,
            "result": result,
        }
    finally:
        from calibration.engine_player import release_all_engines

        release_all_engines()
