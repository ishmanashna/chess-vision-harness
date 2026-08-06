"""Idempotent import of the Lichess standard puzzle CSV into the runtime store.

Import flow:

- read + validate every row (see ``puzzle_validate``),
- apply the Lichess setup convention (stored FEN -> displayed FEN),
- merge into the indexed dataset under ``$CHESS_HARNESS_DIR/puzzles/`` keyed by
  PuzzleId — re-importing the same dataset replaces only the affected rows and
  never rewrites unrelated rows or attempt history,
- write a runtime manifest (version, source, license, counts).

Puzzle rows are imported content (Lichess CC0) and are NEVER committed to the
repository; only ``config/puzzles_manifest.json`` is version-controlled.
"""

from __future__ import annotations

import csv
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import filelock

from .paths import (
    resolve_puzzle_dataset_file,
    resolve_puzzle_manifest_file,
    resolve_puzzles_content_manifest,
)
from .puzzle_validate import PuzzleRow, validate_row

__all__ = [
    "PuzzleImporter",
    "import_puzzle_csv",
    "write_content_manifest",
    "dataset_version_default",
]

DATA_VERSION = 1
DEFAULT_LICENSE = "CC0-1.0"
DEFAULT_SOURCE_URL = "https://database.lichess.org/"


class PuzzleImporter:
    """Imports and merges puzzle rows idempotently into the runtime store."""

    def __init__(
        self,
        dataset_path: Optional[Path] = None,
        manifest_path: Optional[Path] = None,
    ):
        self.dataset_path = dataset_path or resolve_puzzle_dataset_file()
        self.manifest_path = manifest_path or resolve_puzzle_manifest_file()
        self._lock = filelock.FileLock(str(self.dataset_path) + ".lock", timeout=30)

    def _load_dataset(self) -> Dict[str, Any]:
        if not self.dataset_path.exists():
            return {"version": DATA_VERSION, "puzzles": {}}
        try:
            data = json.loads(self.dataset_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"version": DATA_VERSION, "puzzles": {}}
        if not isinstance(data, dict) or not isinstance(data.get("puzzles"), dict):
            return {"version": DATA_VERSION, "puzzles": {}}
        return data

    def _save_dataset(self, data: Dict[str, Any]) -> None:
        self.dataset_path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(
            prefix=f"{self.dataset_path.name}.", dir=self.dataset_path.parent
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(data, stream, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp_name, self.dataset_path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)

    def import_rows(
        self,
        rows: Iterable[Dict[str, Any]],
        *,
        source_url: Optional[str] = None,
        source_name: Optional[str] = None,
        dataset_version: Optional[str] = None,
        max_rows: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Merge rows into the dataset; returns an import summary."""
        accepted: List[PuzzleRow] = []
        rejected: List[str] = []
        seen: set[str] = set()

        limited = 0
        for row in rows:
            if max_rows and limited >= max_rows:
                break
            limited += 1
            try:
                parsed = validate_row(row)
            except Exception as exc:
                rejected.append(str(exc))
                continue
            if parsed.puzzle_id in seen:
                rejected.append(f"duplicate PuzzleId: {parsed.puzzle_id}")
                continue
            seen.add(parsed.puzzle_id)
            accepted.append(parsed)

        now = datetime.now(timezone.utc).isoformat()

        with self._lock:
            data = self._load_dataset()
            puzzles = data.setdefault("puzzles", {})
            added = 0
            updated = 0
            unchanged = 0
            for pz in accepted:
                record = pz.to_dict()
                existing = puzzles.get(pz.puzzle_id)
                if existing is None:
                    puzzles[pz.puzzle_id] = record
                    added += 1
                elif existing.get("fen") == record.get("fen") and existing.get(
                    "solution_moves"
                ) == record.get("solution_moves"):
                    unchanged += 1
                else:
                    puzzles[pz.puzzle_id] = record
                    updated += 1
            self._save_dataset(data)

        manifest = {
            "description": "Chess Vision Harness puzzle dataset",
            "version": data.get("version", DATA_VERSION),
            "dataset_version": dataset_version or dataset_version_default(),
            "source_url": source_url or DEFAULT_SOURCE_URL,
            "source_name": source_name or "Lichess open database (puzzles)",
            "license": DEFAULT_LICENSE,
            "imported_at": now,
            "counts": {
                "total": len(data.get("puzzles", {})),
                "added": added,
                "updated": updated,
                "unchanged": unchanged,
                "rejected": len(rejected),
            },
            "rejections": rejected[:200],
        }
        self._write_manifest(manifest)
        write_content_manifest()
        return manifest

    def _write_manifest(self, manifest: Dict[str, Any]) -> None:
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        self.manifest_path.write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )

    def load_manifest(self) -> Dict[str, Any]:
        if not self.manifest_path.exists():
            return {}
        try:
            return json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def count(self) -> int:
        return len(self._load_dataset().get("puzzles", {}))


def import_puzzle_csv(
    csv_path: str | Path,
    *,
    max_rows: Optional[int] = None,
    source_url: Optional[str] = None,
    source_name: Optional[str] = None,
    dataset_version: Optional[str] = None,
    dataset_path: Optional[Path] = None,
    manifest_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Import a CSV file; returns the import summary/manifest. Idempotent."""
    importer = PuzzleImporter(dataset_path=dataset_path, manifest_path=manifest_path)
    with open(csv_path, newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames:
            raise ValueError(f"CSV has no header: {csv_path}")
        missing = [
            f
            for f in ("PuzzleId", "FEN", "Moves", "Rating")
            if f not in reader.fieldnames
        ]
        if missing:
            raise ValueError(
                f"CSV is missing required columns {missing}: {csv_path}"
            )
        rows = [raw for raw in reader]
    return importer.import_rows(
        rows[: max_rows] if max_rows is not None else rows,
        source_url=source_url,
        source_name=source_name,
        dataset_version=dataset_version,
    )


def write_content_manifest(
    dataset_version: Optional[str] = None,
    source_url: Optional[str] = None,
    source_name: Optional[str] = None,
) -> Path:
    """Rewrite the committed content manifest (config/puzzles_manifest.json)."""
    path = resolve_puzzles_content_manifest()
    path.parent.mkdir(parents=True, exist_ok=True)
    content = {
        "description": "Chess Vision Harness committed content manifest",
        "license": DEFAULT_LICENSE,
        "source_url": source_url or DEFAULT_SOURCE_URL,
        "source_name": source_name or "Lichess open database (puzzles)",
        "dataset_version": dataset_version or "unknown",
        "note": "Puzzle rows are NOT committed. Import with: chess-harness puzzles import <file.csv>",
    }
    path.write_text(json.dumps(content, indent=2) + "\n", encoding="utf-8")
    return path


def dataset_version_default() -> str:
    """Default dataset version label (ISO date of import)."""
    return datetime.now(timezone.utc).strftime("%Y%m%d")