"""Shared test constants."""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

ROOT = Path(__file__).resolve().parent.parent
STOCKFISH_BIN = ROOT / "bin" / "stockfish-windows-x86-64.exe"

os.environ.setdefault("STOCKFISH_PATH", str(STOCKFISH_BIN))

DEFAULT_MODEL = "composer-2.5"
