"""Tests for the indexed puzzle store: selection, filters, exclusions."""

from __future__ import annotations

import csv
import random
from pathlib import Path
from typing import Dict, List

from chess_harness.puzzle_import import import_puzzle_csv
from chess_harness.puzzle_store import PuzzleStore


def _row(
    puzzle_id: str,
    fen: str,
    moves: List[str],
    rating: int = 1500,
    themes: str = "sacrifice",
) -> Dict[str, str]:
    return {
        "PuzzleId": puzzle_id,
        "FEN": fen,
        "Moves": " ".join(moves),
        "Rating": str(rating),
        "RatingDeviation": "75",
        "Popularity": "90",
        "NbPlays": "5000",
        "Themes": themes,
        "GameUrl": "https://lichess.org/abc",
        "OpeningTags": "sicilian",
        "DailyDate": "2024-01-01",
    }


def _make_store(tmp_path: Path, rows: List[Dict[str, str]]) -> PuzzleStore:
    csv_path = tmp_path / "puzzles.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    import_puzzle_csv(
        str(csv_path),
        dataset_path=tmp_path / "puzzles.json",
        manifest_path=tmp_path / "manifest.json",
    )
    return PuzzleStore(
        dataset_path=tmp_path / "puzzles.json",
        manifest_path=tmp_path / "manifest.json",
    )


def test_store_empty_returns_none(tmp_path):
    store = PuzzleStore(dataset_path=tmp_path / "none.json")
    assert store.count() == 0
    assert store.get("anything") is None
    assert store.random_puzzle() is None


def test_store_get_and_id_keyed(tmp_path):
    fen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
    store = _make_store(tmp_path, [_row("pz-a", fen, ["e2e4", "e7e5"])])
    assert store.count() == 1
    record = store.get("pz-a")
    assert record is not None
    assert record["puzzle_id"] == "pz-a"
    assert record["rating"] == 1500
    assert "solution_moves" in record
    assert store.get("missing") is None


def test_random_puzzle_honors_exclusions(tmp_path):
    fen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
    rows = [_row(f"p{i}", fen, ["e2e4", "e7e5"]) for i in range(5)]
    store = _make_store(tmp_path, rows)
    rng = random.Random(42)
    seen = set()
    for _ in range(200):
        choice = store.random_puzzle(rng=rng, exclusions=seen)
        if choice is None:
            break
        seen.add(choice["puzzle_id"])
    assert len(seen) == 5
    assert store.random_puzzle(exclusions=list(seen)) is None


def test_random_puzzle_rating_band(tmp_path):
    fen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
    rows = [
        _row("p0", fen, ["e2e4", "e7e5"], rating=1000),
        _row("p1", fen, ["d2d4", "d7d5"], rating=1500),
        _row("p2", fen, ["c2c4", "c7c5"], rating=2000),
    ]
    store = _make_store(tmp_path, rows)
    for seed in range(40):
        rng = random.Random(seed)
        picked = store.random_puzzle(rng=rng, rating_min=1400, rating_max=1600)
        assert picked is not None
        assert 1400 <= picked["rating"] <= 1600


def test_random_puzzle_theme_filter(tmp_path):
    fen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
    rows = [
        _row("mate", fen, ["e2e4"], themes="mateIn2"),
        _row("fork", fen, ["d2d4"], themes="fork"),
    ]
    store = _make_store(tmp_path, rows)
    for seed in range(40):
        picked = store.random_puzzle(rng=random.Random(seed), theme="fork")
        assert picked is not None
        assert "fork" in picked["themes"]


def test_manifest_filters_ranges(tmp_path):
    fen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
    store = _make_store(tmp_path, [_row("p", fen, ["e2e4", "e7e5"])])
    manifest = store.manifest()
    assert manifest["counts"]["total"] == 1
    assert manifest["license"] == "CC0-1.0"


def test_store_stats(tmp_path):
    fen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
    rows = [
        _row("a", fen, ["e2e4", "e7e5"], rating=1000, themes="mateIn2"),
        _row("b", fen, ["d2d4", "d7d5"], rating=2000, themes="mateIn2 fork"),
    ]
    store = _make_store(tmp_path, rows)
    stats = store.stats()
    assert stats["total"] == 2
    assert stats["average_rating"] == 1500.0
    assert stats["rating_min"] == 1000
    assert stats["rating_max"] == 2000
    assert stats["rating_median"] == 1500.0
    assert stats["buckets"]["1000_1200"] == 1
    assert stats["buckets"]["1200_1500"] == 0
    assert stats["buckets"]["1500_plus"] == 1
    assert stats["themes"]["mateIn2"] == 2
    assert stats["themes"]["fork"] == 1
