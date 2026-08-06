"""Tests for puzzle CSV import: validation, Lichess convention, idempotency."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict, List

import pytest
import chess

from chess_harness.puzzle_import import PuzzleImporter, import_puzzle_csv
from chess_harness.puzzle_validate import (
    PuzzleValidationError,
    apply_lichess_setup,
    validate_row,
)
from chess_harness.puzzle_store import PuzzleStore


def _row(
    puzzle_id: str,
    fen: str,
    moves: List[str],
    rating: int = 1500,
    deviation: int = 75,
    popularity: int = 90,
    nb_plays: int = 5000,
    themes: str = "mateIn2 sacrifice",
    game_url: str = "https://lichess.org/abc",
    opening_tags: str = "sicilian",
    daily_date: str = "2024-01-01",
) -> Dict[str, str]:
    return {
        "PuzzleId": puzzle_id,
        "FEN": fen,
        "Moves": " ".join(moves),
        "Rating": str(rating),
        "RatingDeviation": str(deviation),
        "Popularity": str(popularity),
        "NbPlays": str(nb_plays),
        "Themes": themes,
        "GameUrl": game_url,
        "OpeningTags": opening_tags,
        "DailyDate": daily_date,
    }


def _legal_line(moves: List[str]) -> str:
    """Walk a UCI line from the starting position and return the ending FEN."""
    board = chess.Board()
    for move in moves:
        board.push_uci(move)
    return board.fen()


def _write_csv(path: Path, rows: List[Dict[str, str]]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


# ---------------------------------------------------------------- validation


def test_apply_lichess_setup_convention():
    fen = chess.STARTING_FEN
    display_fen, setup, solution = apply_lichess_setup(fen, ["e2e4", "e7e5", "g1f3"])
    assert setup == "e2e4"
    assert solution == ["e7e5", "g1f3"]
    expected = chess.Board(fen)
    expected.push_uci("e2e4")
    assert display_fen == expected.fen()
    assert chess.Board(display_fen).turn == chess.BLACK


def test_validate_row_normalizes_fields():
    row = _row(
        "puzzle-a",
        chess.STARTING_FEN,
        ["e2e4", "e7e5"],
        rating=1700,
        deviation=60,
        themes="mateIn1 short",
    )
    parsed = validate_row(row)
    assert parsed.puzzle_id == "puzzle-a"
    assert parsed.rating == 1700
    assert parsed.rating_deviation == 60
    assert parsed.themes == ["mateIn1", "short"]
    expected = chess.Board()
    expected.push_uci("e2e4")
    assert parsed.display_fen == expected.fen()
    assert parsed.solution_moves == ["e7e5"]


def test_validate_row_rejects_bad_fen():
    with pytest.raises(PuzzleValidationError):
        validate_row(_row("bad-fen", "not-a-fen", ["e2e4"]))


def test_validate_row_rejects_illegal_line():
    with pytest.raises(PuzzleValidationError):
        validate_row(_row("illegal", chess.STARTING_FEN, ["e2e4", "e7e5", "e4e5", "g8f6", "f6e4"]))


def test_validate_row_rejects_illegal_setup_move():
    with pytest.raises(PuzzleValidationError):
        validate_row(_row("bad-setup", chess.STARTING_FEN, ["e2e5"]))


def test_validate_row_rejects_bad_rating():
    with pytest.raises(PuzzleValidationError):
        validate_row(_row("bad-rating", chess.STARTING_FEN, ["e2e4"], rating=-5))


def test_validate_row_rejects_duplicate_ids():
    rows = [
        _row("dup-1", chess.STARTING_FEN, ["e2e4"]),
        _row("dup-1", chess.STARTING_FEN, ["d2d4"]),
    ]
    from chess_harness.puzzle_validate import validate_rows

    accepted, rejected = validate_rows(rows)
    assert len(accepted) == 1
    assert any("duplicate" in r for r in rejected)


# ------------------------------------------------------------------- importing


def _importer(tmp_path: Path) -> PuzzleImporter:
    return PuzzleImporter(
        dataset_path=tmp_path / "puzzles.json",
        manifest_path=tmp_path / "manifest.json",
    )


def _sample_rows() -> List[Dict[str, str]]:
    fen_a = _legal_line(["e2e4", "e7e5", "g1f3", "b8c6"])
    fen_b = _legal_line(["d2d4", "d7d5", "c2c4"])
    return [
        _row("puzzle-1", fen_a, ["f3e5", "d7d6", "e5f7"], rating=1600, themes="mateIn2"),
        _row("puzzle-2", fen_b, ["c7c5", "g1f3"], rating=1200, themes="fork"),
        _row("puzzle-3", chess.STARTING_FEN, ["e2e4", "e7e5"], rating=1800, themes="opening"),
    ]


def test_import_creates_indexed_dataset(tmp_path):
    csv_path = tmp_path / "puzzles.csv"
    _write_csv(csv_path, _sample_rows())

    manifest = import_puzzle_csv(
        str(csv_path),
        dataset_path=tmp_path / "puzzles.json",
        manifest_path=tmp_path / "manifest.json",
    )
    assert manifest["counts"]["total"] == 3
    assert manifest["counts"]["added"] == 3
    assert manifest["counts"]["rejected"] == 0
    assert manifest["license"] == "CC0-1.0"
    assert "source_url" in manifest
    assert "imported_at" in manifest
    assert manifest["dataset_version"]

    store = PuzzleStore(
        dataset_path=tmp_path / "puzzles.json",
        manifest_path=tmp_path / "manifest.json",
    )
    assert store.count() == 3
    record = store.get("puzzle-1")
    assert record is not None
    assert record["puzzle_id"] == "puzzle-1"
    assert record["display_fen"]
    assert record["solution_moves"]
    assert len(record["solution_moves"]) >= 1
    assert "fen" in record


def test_import_is_idempotent(tmp_path):
    csv_path = tmp_path / "puzzles.csv"
    _write_csv(csv_path, _sample_rows())

    first = import_puzzle_csv(
        str(csv_path),
        dataset_path=tmp_path / "puzzles.json",
        manifest_path=tmp_path / "manifest.json",
    )
    second = import_puzzle_csv(
        str(csv_path),
        dataset_path=tmp_path / "puzzles.json",
        manifest_path=tmp_path / "manifest.json",
    )
    assert first["counts"]["added"] == 3
    assert second["counts"]["added"] == 0
    assert second["counts"]["unchanged"] == 3
    assert second["counts"]["updated"] == 0
    assert second["counts"]["total"] == 3


def test_import_updates_changed_row(tmp_path):
    csv_path = tmp_path / "puzzles.csv"
    rows = _sample_rows()
    _write_csv(csv_path, rows)

    import_puzzle_csv(
        str(csv_path),
        dataset_path=tmp_path / "puzzles.json",
        manifest_path=tmp_path / "manifest.json",
    )
    modified = list(rows)
    modified[0] = dict(rows[0])
    modified[0]["Moves"] = "f3e5 d7d6"  # shorter solution
    _write_csv(csv_path, modified)
    manifest = import_puzzle_csv(
        str(csv_path),
        dataset_path=tmp_path / "puzzles.json",
        manifest_path=tmp_path / "manifest.json",
    )
    assert manifest["counts"]["updated"] == 1
    assert manifest["counts"]["unchanged"] == 2

    store = PuzzleStore(
        dataset_path=tmp_path / "puzzles.json",
        manifest_path=tmp_path / "manifest.json",
    )
    assert store.get("puzzle-1")["solution_moves"] == ["d7d6"]


def test_import_rejects_bad_rows_and_reports(tmp_path):
    csv_path = tmp_path / "puzzles.csv"
    rows = _sample_rows() + [_row("bad-row", "not-a-fen", ["e2e4"])]
    _write_csv(csv_path, rows)

    manifest = import_puzzle_csv(
        str(csv_path),
        dataset_path=tmp_path / "puzzles.json",
        manifest_path=tmp_path / "manifest.json",
    )
    assert manifest["counts"]["added"] == 3
    assert manifest["counts"]["rejected"] == 1
    assert any("FEN" in r or "fen" in r for r in manifest["rejections"])


def test_import_max_rows(tmp_path):
    csv_path = tmp_path / "puzzles.csv"
    _write_csv(csv_path, _sample_rows())
    manifest = import_puzzle_csv(
        str(csv_path),
        max_rows=2,
        dataset_path=tmp_path / "puzzles.json",
        manifest_path=tmp_path / "manifest.json",
    )
    assert manifest["counts"]["total"] == 2


def test_import_missing_required_column(tmp_path):
    csv_path = tmp_path / "puzzles.csv"
    lines = [
        "PuzzleId,FEN,Moves,RatingDeviation,Popularity,NbPlays,Themes,GameUrl,OpeningTags,DailyDate",
        "puzzle-x,r1bqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1,e2e4,75,90,5000,mateIn2,x,sicilian,2024-01-01",
    ]
    csv_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Rating"):
        import_puzzle_csv(
        str(csv_path),
        dataset_path=tmp_path / "puzzles.json",
        manifest_path=tmp_path / "manifest.json",
    )


def test_same_id_same_position_after_reimport(tmp_path):
    """The 'Done when' guarantee: same id -> same display position, even after a
    re-import that touches other rows."""
    csv_path = tmp_path / "puzzles.csv"
    _write_csv(csv_path, _sample_rows())
    import_puzzle_csv(
        str(csv_path),
        dataset_path=tmp_path / "puzzles.json",
        manifest_path=tmp_path / "manifest.json",
    )
    store = PuzzleStore(
        dataset_path=tmp_path / "puzzles.json",
        manifest_path=tmp_path / "manifest.json",
    )
    before = store.get("puzzle-2")["display_fen"]

    rows = _sample_rows() + [_row("extra-4", _legal_line(["b1c3", "b8c6"]), ["c3b5"])]
    _write_csv(csv_path, rows)
    import_puzzle_csv(
        str(csv_path),
        dataset_path=tmp_path / "puzzles.json",
        manifest_path=tmp_path / "manifest.json",
    )
    after = store.get("puzzle-2")["display_fen"]
    assert before == after
    assert store.get("extra-4")["puzzle_id"] == "extra-4"


# ------------------------------------------------------------------- content manifest


def test_content_manifest_committed_exists():
    from chess_harness.paths import resolve_puzzles_content_manifest

    path = resolve_puzzles_content_manifest()
    assert path.exists()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["license"] == "CC0-1.0"
    assert "lichess" in data["source_url"]


def test_puzzle_rows_not_in_repo(tmp_path):
    """Dataset lives under CHESS_HARNESS_DIR (or an explicit path), never the
    repository root."""
    csv_path = tmp_path / "puzzles.csv"
    _write_csv(csv_path, _sample_rows())
    import_puzzle_csv(
        str(csv_path),
        dataset_path=tmp_path / "puzzles.json",
        manifest_path=tmp_path / "manifest.json",
    )
    from chess_harness.paths import project_root, resolve_puzzles_dir

    assert not (project_root() / "puzzles.json").exists()
    # default runtime dir is under CHESS_HARNESS_DIR / .chess_harness
    assert resolve_puzzles_dir().name == "puzzles"
