"""Tests for `puzzles fetch`: zstd streaming, rating filter, slice/cap logic.

All tests use a synthetic in-memory compressed stream — no network access.
"""

from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Any, Dict, List

import zstandard

from chess_harness.puzzle_fetch import (
    collect_rows,
    fetch_puzzles,
    write_rows_csv,
)
from chess_harness.puzzle_validate import LICHESS_FIELDS

FIELDS = list(LICHESS_FIELDS)


def _csv_text(rows: List[Dict[str, Any]]) -> str:
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=FIELDS)
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue()


def _compress(text: str) -> bytes:
    return zstandard.ZstdCompressor(level=3).compress(text.encode())


def _row(puzzle_id: str, rating: int) -> Dict[str, str]:
    return {
        "PuzzleId": puzzle_id,
        "FEN": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
        "Moves": "e2e4 e7e5",
        "Rating": str(rating),
        "RatingDeviation": "75",
        "Popularity": "90",
        "NbPlays": "1000",
        "Themes": "mateIn2",
        "GameUrl": "https://lichess.org/abc",
        "OpeningTags": "opening",
        "DailyDate": "2024-01-01",
    }


def _make_rows(n: int, ratings) -> List[Dict[str, str]]:
    return [_row(f"p{i:05d}", ratings[i % len(ratings)]) for i in range(n)]


def test_collect_rows_filters_and_slices():
    rows = _make_rows(100, ratings=[1000, 1400, 1600, 1200])
    compressed = _compress(_csv_text(rows))
    result = collect_rows([compressed], count=25, max_rating=1300)
    assert result["rows"]
    assert len(result["rows"]) == 25
    assert all(int(r["Rating"]) <= 1300 for r in result["rows"])
    assert not result["capped"]
    assert result["scanned"] > 0


def test_collect_rows_chunked_stream_matches_single():
    rows = _make_rows(200, ratings=[1000, 1400, 1600, 1200])
    compressed = _compress(_csv_text(rows))
    chunk_size = max(1, len(compressed) // 7)
    chunks = [
        compressed[i : i + chunk_size] for i in range(0, len(compressed), chunk_size)
    ]
    assert len(chunks) > 1
    result = collect_rows(chunks, count=40, max_rating=1300)
    single = collect_rows([compressed], count=40, max_rating=1300)
    assert result["rows"] == single["rows"]
    assert all(int(r["Rating"]) <= 1300 for r in result["rows"])


def test_collect_rows_cap_reports_shortfall():
    rows = _make_rows(200, ratings=[1000, 1400])
    compressed = _compress(_csv_text(rows))
    tiny = max(8, len(compressed) // 3)
    result = collect_rows([compressed], count=500, max_rating=1300, max_bytes=tiny)
    assert len(result["rows"]) < 500
    assert result["capped"]


def test_collect_rows_handles_skippable_frame_prefix():
    rows = _make_rows(30, ratings=[1100])
    compressed = _compress(_csv_text(rows))
    prefixed = b"\x50\x2a\x4d\x18" + b"\x00\x00\x00\x00" + compressed
    result = collect_rows([prefixed], count=10, max_rating=1300)
    assert len(result["rows"]) == 10


def test_write_rows_csv_roundtrip():
    rows = _make_rows(12, ratings=[1000, 1400])
    path = Path(__file__).parent / "tmp_fetch_out.csv"
    try:
        write_rows_csv(rows, path)
        with open(path, newline="", encoding="utf-8") as stream:
            reader = csv.DictReader(stream)
            assert reader.fieldnames == FIELDS
            loaded = list(reader)
        assert len(loaded) == 12
        assert loaded[0]["PuzzleId"] == rows[0]["PuzzleId"]
    finally:
        path.unlink(missing_ok=True)


def test_fetch_puzzles_writes_csv(monkeypatch):
    from chess_harness import puzzle_fetch

    rows = _make_rows(50, ratings=[1000, 1400])
    compressed = _compress(_csv_text(rows))

    monkeypatch.setattr(
        puzzle_fetch,
        "_download",
        lambda url, max_bytes: [compressed],
    )
    out = Path(__file__).parent / "tmp_fetch_out.csv"
    try:
        result = fetch_puzzles(count=20, max_rating=1300, out=out)
        assert result["out"] == str(out)
        assert len(result["rows"]) == 20
        assert out.exists()
    finally:
        out.unlink(missing_ok=True)


def test_fetch_puzzles_defaults_none_max_bytes(monkeypatch):
    from chess_harness import puzzle_fetch

    rows = _make_rows(10, ratings=[1100])
    compressed = _compress(_csv_text(rows))

    monkeypatch.setattr(
        puzzle_fetch,
        "_download",
        lambda url, max_bytes: [compressed],
    )
    result = fetch_puzzles(count=5, max_rating=1300, max_bytes=None)
    assert len(result["rows"]) == 5
