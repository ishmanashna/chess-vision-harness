"""Tests for localhost puzzle-set panel (Phase 8)."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import chess
import pytest

from chess_harness.puzzle_import import import_puzzle_csv
from chess_harness.puzzle_set import (
    build_puzzle_preview_payload,
    build_puzzle_set_payload,
    render_puzzle_preview_board_png,
)
from chess_harness.puzzle_store import PuzzleStore
from chess_harness.puzzle_attempt import PuzzleAttemptStore
from chess_harness.identify_attempt import IdentifyAttemptStore

FORBIDDEN_ROW_KEYS = frozenset(
    {"solution_moves", "display_fen", "fen", "corpus_fen", "correct_pieces", "moves"}
)


def _row(
    puzzle_id: str,
    fen: str,
    moves: list[str],
    rating: int = 1500,
    themes: str = "mateIn2",
) -> dict[str, str]:
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


def _make_store(tmp_path: Path, rows: list[dict[str, str]]) -> PuzzleStore:
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


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_puzzle_set_includes_all_imported_rows(tmp_path):
    fen = chess.STARTING_FEN
    store = _make_store(
        tmp_path,
        [
            _row("easy", fen, ["e2e4", "e7e5"], rating=550),
            _row("hard", fen, ["d2d4", "d7d5"], rating=1600),
        ],
    )
    payload = build_puzzle_set_payload(
        puzzles=store,
        puzzle_attempts=PuzzleAttemptStore(tmp_path / "pz.json"),
        identify_attempts=IdentifyAttemptStore(tmp_path / "iz.json"),
    )
    summary = payload["summary"]
    assert summary["total"] == 2
    assert summary["never_attempted"] == 2
    assert summary["buckets"]["under_600"] == 1
    assert summary["buckets"]["1500_plus"] == 1
    assert len(payload["puzzles"]) == 2
    by_id = {row["id"]: row for row in payload["puzzles"]}
    assert by_id["easy"]["puzzle_attempts"] == 0
    assert by_id["hard"]["identify_attempts"] == 0


def test_puzzle_set_row_stats_and_watch_links(tmp_path):
    fen = chess.STARTING_FEN
    store = _make_store(tmp_path, [_row("pz-a", fen, ["e2e4", "e7e5"], rating=900)])
    _write(
        tmp_path / "pz.json",
        {
            "version": 1,
            "attempts": {
                "old": {
                    "attempt_id": "pz-old",
                    "puzzle_id": "pz-a",
                    "status": "finished",
                    "result": "failed",
                    "started_at": "2026-08-01T10:00:00+00:00",
                },
                "new": {
                    "attempt_id": "pz-new",
                    "puzzle_id": "pz-a",
                    "status": "finished",
                    "result": "correct",
                    "started_at": "2026-08-02T10:00:00+00:00",
                },
            },
        },
    )
    _write(
        tmp_path / "iz.json",
        {
            "version": 1,
            "attempts": {
                "bi-1": {
                    "attempt_id": "bi-1",
                    "puzzle_id": "pz-a",
                    "status": "finished",
                    "started_at": "2026-08-03T10:00:00+00:00",
                    "score": {"accuracy": 0.75, "full_position": False},
                }
            },
        },
    )
    payload = build_puzzle_set_payload(
        puzzles=store,
        puzzle_attempts=PuzzleAttemptStore(tmp_path / "pz.json"),
        identify_attempts=IdentifyAttemptStore(tmp_path / "iz.json"),
    )
    row = payload["puzzles"][0]
    assert row["puzzle_attempts"] == 2
    assert row["puzzle_solves"] == 1
    assert row["puzzle_solve_rate"] == pytest.approx(0.5)
    assert row["identify_attempts"] == 1
    assert row["identify_mean_accuracy"] == pytest.approx(0.75)
    assert row["watch_puzzle"] == "/p/pz-new"
    assert row["watch_identify"] == "/i/bi-1"
    assert payload["summary"]["never_attempted"] == 0


def test_puzzle_set_payload_has_no_secrets(tmp_path):
    fen = chess.STARTING_FEN
    store = _make_store(tmp_path, [_row("secret", fen, ["e2e4", "e7e5"])])
    payload = build_puzzle_set_payload(
        puzzles=store,
        puzzle_attempts=PuzzleAttemptStore(tmp_path / "pz.json"),
        identify_attempts=IdentifyAttemptStore(tmp_path / "iz.json"),
    )
    blob = json.dumps(payload)
    assert "solution_moves" not in blob
    assert "display_fen" not in blob
    for row in payload["puzzles"]:
        assert not FORBIDDEN_ROW_KEYS.intersection(row)


def test_puzzle_set_api_loopback_only(spectator_client):
    client = spectator_client
    denied = client.get("/api/puzzle-set")
    assert denied.status_code == 403
    ok = client.get("/api/puzzle-set", headers={"Host": "127.0.0.1:8765"})
    assert ok.status_code == 200
    body = ok.json()
    assert "summary" in body and "puzzles" in body


def test_puzzle_set_page_loopback_only(spectator_client):
    client = spectator_client
    denied = client.get("/puzzle-set")
    assert denied.status_code == 404
    ok = client.get("/puzzle-set", headers={"Host": "127.0.0.1:8765"})
    assert ok.status_code == 200
    assert "Imported puzzle set" in ok.text
    assert "/js/puzzle-set.js" in ok.text


def test_puzzle_preview_payload_computes_placement(tmp_path):
    fen = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1"
    store = _make_store(tmp_path, [_row("preview-me", fen, ["e7e5", "g1f3"], rating=1100)])
    payload = build_puzzle_preview_payload("preview-me", puzzles=store)
    assert payload is not None
    assert payload["id"] == "preview-me"
    assert payload["difficulty"] == 1100
    assert payload["side_to_move"] == "white"
    assert payload["solution_moves"] == ["g1f3"]
    assert payload["placement"]["e4"] == "wP"
    assert payload["placement"]["e5"] == "bP"
    assert payload["board_url"] == "/api/puzzle-set/preview-me/preview/board.png"
    png = render_puzzle_preview_board_png("preview-me", puzzles=store)
    assert png and png[:8] == b"\x89PNG\r\n\x1a\n"


def test_puzzle_preview_api_loopback_only(spectator_client, tmp_path, monkeypatch):
    fen = chess.STARTING_FEN
    store = _make_store(tmp_path, [_row("pz-prev", fen, ["e2e4", "e7e5"])])
    monkeypatch.setattr(
        "chess_harness.puzzle_set.PuzzleStore",
        lambda *args, **kwargs: store,
    )
    client = spectator_client
    denied = client.get("/api/puzzle-set/pz-prev/preview")
    assert denied.status_code == 403
    ok = client.get(
        "/api/puzzle-set/pz-prev/preview",
        headers={"Host": "127.0.0.1:8765"},
    )
    assert ok.status_code == 200
    body = ok.json()
    assert body["id"] == "pz-prev"
    assert body["placement"]["e4"] == "wP"
    board = client.get(
        "/api/puzzle-set/pz-prev/preview/board.png",
        headers={"Host": "127.0.0.1:8765"},
    )
    assert board.status_code == 200
    assert board.headers["content-type"].startswith("image/png")


def test_puzzle_preview_page_loopback_only(spectator_client, tmp_path, monkeypatch):
    fen = chess.STARTING_FEN
    store = _make_store(tmp_path, [_row("pz-shell", fen, ["e2e4", "e7e5"])])
    monkeypatch.setattr(
        "chess_harness.puzzle_set.PuzzleStore",
        lambda *args, **kwargs: store,
    )
    client = spectator_client
    denied = client.get("/puzzle-set/pz-shell")
    assert denied.status_code == 404
    ok = client.get("/puzzle-set/pz-shell", headers={"Host": "127.0.0.1:8765"})
    assert ok.status_code == 200
    assert 'data-puzzle-id="pz-shell"' in ok.text
    assert "/js/puzzle-set-preview.js" in ok.text


def test_puzzle_preview_unknown_id_404(spectator_client):
    client = spectator_client
    missing = client.get(
        "/api/puzzle-set/does-not-exist/preview",
        headers={"Host": "127.0.0.1:8765"},
    )
    assert missing.status_code == 404
