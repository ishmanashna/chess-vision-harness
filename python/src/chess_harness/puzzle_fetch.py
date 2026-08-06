"""Fetch a low-rated slice of the Lichess standard puzzle dump (CC0).

The monthly dump (``https://database.lichess.org/lichess_db_puzzle.csv.zst``,
~300 MB) is streamed in, incrementally zstd-decoded, filtered to rows with
``Rating <= max_rating``, and written as a standard CSV with the same columns
as the dump. Download stops as soon as the requested row count is collected
or the safety byte cap is reached; the full dump is never materialized.

Remote content (CC0) is written to an operator-chosen path and is never
committed to the repository.
"""

from __future__ import annotations

import csv
import io
import urllib.request
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import zstandard

from .puzzle_validate import LICHESS_FIELDS

__all__ = [
    "DEFAULT_PUZZLE_URL",
    "DEFAULT_MAX_BYTES",
    "PuzzleFetchError",
    "collect_rows",
    "fetch_puzzles",
    "write_rows_csv",
]

DEFAULT_PUZZLE_URL = "https://database.lichess.org/lichess_db_puzzle.csv.zst"
DEFAULT_MAX_BYTES = 256 * 1024 * 1024  # 256 MiB compressed read cap
_DECODE_GRANULARITY = 8 * 1024 * 1024  # re-scan after this much compressed data
_REQUEST_CHUNK = 2 * 1024 * 1024
_HEADERS = {"User-Agent": "chess-vision-harness/0.2 (puzzle fetch)"}


class PuzzleFetchError(RuntimeError):
    """Remote fetch or decode failed."""


def _decode_prefix(compressed: bytes) -> str:
    """Decode a (possibly partial) zstd stream; returns a stable text prefix.

    Lichess' dump opens with a zstd skippable frame before the real frame, so
    single-shot ``decompress()`` can fail; the streaming reader handles it.
    """
    reader = zstandard.ZstdDecompressor().stream_reader(io.BytesIO(compressed))
    try:
        return reader.read().decode("utf-8", errors="replace")
    finally:
        reader.close()


class _SegmentScanner:
    """Parse a growing CSV text prefix, emitting only newly completed lines."""

    def __init__(self, max_rating: int):
        self.max_rating = max_rating
        self.header: Optional[List[str]] = None
        self.kept: List[Dict[str, Any]] = []
        self.scanned = 0
        self._lines_done = 0

    def feed(self, text: str) -> None:
        if not text:
            return
        lines = text.split("\n")
        countable = len(lines) - 1  # last element may be a partial tail line
        if countable <= self._lines_done:
            return
        for line in lines[self._lines_done : countable]:
            self.scanned += 1
            values = next(csv.reader([line]), [])
            if not values:
                continue
            if self.header is None:
                self.header = list(values)
                continue
            if len(values) < len(self.header):
                continue
            row = dict(zip(self.header, values))
            try:
                rating = int(row.get("Rating", ""))
            except (TypeError, ValueError):
                continue
            if self.max_rating is None or rating <= self.max_rating:
                self.kept.append(row)
        self._lines_done = countable


def collect_rows(
    compressed_source: Iterable[bytes],
    *,
    count: int,
    max_rating: int,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> Dict[str, Any]:
    """Stream-decode, filter and slice a compressed CSV source.

    Returns a summary dict: kept rows, rows scanned, compressed bytes read,
    and whether the safety cap was hit before the requested count.
    """
    scanner = _SegmentScanner(max_rating)
    buffer = bytearray()
    bytes_read = 0
    for chunk in compressed_source:
        buffer.extend(chunk)
        bytes_read += len(chunk)
        if bytes_read >= _DECODE_GRANULARITY or bytes_read >= max_bytes:
            scanner.feed(_decode_prefix(bytes(buffer)))
            if len(scanner.kept) >= count:
                break
        if bytes_read >= max_bytes:
            break
    if len(scanner.kept) < count and bytes_read > 0:
        scanner.feed(_decode_prefix(bytes(buffer)))
    return {
        "rows": scanner.kept[:count],
        "scanned": scanner.scanned,
        "bytes_read": bytes_read,
        "capped": bytes_read >= max_bytes and len(scanner.kept) < count,
    }


def _download(url: str, max_bytes: int) -> Iterable[bytes]:
    """Yield compressed data from the remote dump up to ``max_bytes``."""
    request = urllib.request.Request(url, headers=_HEADERS)
    try:
        with urllib.request.urlopen(request, timeout=60) as resp:
            remaining = max_bytes
            while remaining > 0:
                chunk = resp.read(min(_REQUEST_CHUNK, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk
    except OSError as exc:
        raise PuzzleFetchError(f"download failed for {url}: {exc}") from exc


def write_rows_csv(rows: Iterable[Dict[str, Any]], path: Path) -> None:
    """Write parsed rows as a standard Lichess-column CSV."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(LICHESS_FIELDS))
        writer.writeheader()
        writer.writerows(rows)


def fetch_puzzles(
    *,
    count: int = 500,
    max_rating: int = 1500,
    max_bytes: int = DEFAULT_MAX_BYTES,
    url: str = DEFAULT_PUZZLE_URL,
    out: Optional[Path] = None,
) -> Dict[str, Any]:
    """Fetch a low-rated slice; optionally write it as a CSV.

    Returns the :func:`collect_rows` summary plus the output path when given.
    """
    if max_bytes is None:
        max_bytes = DEFAULT_MAX_BYTES
    result = collect_rows(
        _download(url, max_bytes),
        count=count,
        max_rating=max_rating,
        max_bytes=max_bytes,
    )
    if out is not None and result["rows"]:
        write_rows_csv(result["rows"][:count], out)
        result["out"] = str(out)
    return result
