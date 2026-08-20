"""Shared puzzle corpus import for agent_http and runner tests."""

from __future__ import annotations

from typing import Any, Dict, List

import chess

from chess_harness.puzzle_import import PuzzleImporter


def puzzle_row(
    puzzle_id: str,
    moves: List[str],
    rating: int = 1500,
    themes: str = "opening",
    game_url: str = "https://lichess.org/x",
) -> Dict[str, str]:
    return {
        "PuzzleId": puzzle_id,
        "FEN": chess.STARTING_FEN,
        "Moves": " ".join(moves),
        "Rating": str(rating),
        "RatingDeviation": "75",
        "Popularity": "90",
        "NbPlays": "5000",
        "Themes": themes,
        "GameUrl": game_url,
        "OpeningTags": "test",
        "DailyDate": "2024-01-01",
    }


def import_test_puzzles() -> None:
    PuzzleImporter().import_rows(
        [
            puzzle_row(
                "pz-a",
                ["e2e4", "e7e5", "g1f3", "g8f6", "f1c4"],
                rating=1500,
                themes="opening",
                game_url="https://lichess.org/a",
            ),
            puzzle_row(
                "pz-b",
                ["d2d4", "d7d5", "c2c4"],
                rating=1200,
                themes="opening",
                game_url="https://lichess.org/b",
            ),
            puzzle_row(
                "pz-c",
                ["c2c4", "e7e5", "g1f3"],
                rating=1800,
                themes="mateIn2",
                game_url="https://lichess.org/c",
            ),
        ]
    )
