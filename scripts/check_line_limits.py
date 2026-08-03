#!/usr/bin/env python3
"""Fail if any coding source file exceeds the line limit (default 300)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Extensions treated as coding sources.
CODE_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"}

SKIP_DIR_NAMES = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "dist",
    "build",
    "bin",  # vendored engine binaries / trees
}


def iter_code_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in CODE_SUFFIXES:
            continue
        if any(part in SKIP_DIR_NAMES for part in path.parts):
            continue
        files.append(path)
    return sorted(files)


def count_lines(path: Path) -> int:
    # Count physical lines (including blanks), matching editor line numbers.
    text = path.read_text(encoding="utf-8", errors="replace")
    if text == "":
        return 0
    return text.count("\n") + (0 if text.endswith("\n") else 1)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--max-lines",
        type=int,
        default=300,
        help="Maximum allowed lines per coding file (default: 300)",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=ROOT,
        help="Repository root to scan",
    )
    args = parser.parse_args()
    root: Path = args.root.resolve()
    limit: int = args.max_lines

    violations: list[tuple[int, Path]] = []
    for path in iter_code_files(root):
        n = count_lines(path)
        if n > limit:
            violations.append((n, path.relative_to(root)))

    if not violations:
        print(f"Line limit OK (<={limit} lines, {len(list(iter_code_files(root)))} files scanned)")
        return 0

    print(f"Line limit FAILED - {len(violations)} file(s) over {limit} lines:\n")
    for n, rel in sorted(violations, key=lambda item: (-item[0], str(item[1]))):
        print(f"  {n:4d}  {rel.as_posix()}")
    print(
        "\nSplit by responsibility (see ARCHITECTURE.md). "
        "Do not shred into meaningless fragments to pass the check."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
