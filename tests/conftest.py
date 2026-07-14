"""Shared test constants and fixtures."""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"

sys.path.insert(0, str(ROOT / "src"))

STOCKFISH_BIN = ROOT / "bin" / "stockfish-windows-x86-64.exe"

os.environ.setdefault("STOCKFISH_PATH", str(STOCKFISH_BIN))
os.environ.setdefault("MODELS_FILE", str(FIXTURES / "models.json"))

DEFAULT_MODEL = "composer-2.5"

# Opponents in the committed catalog (updated when ladder is pruned)
LOW_OPPONENT = "stockfish-handicap:noise10"
MID_OPPONENT = "stockfish-handicap:noise22"
UNCALIBRATED_OPPONENT = "stockfish-handicap:noise7"
