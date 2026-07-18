"""Smoke test for opponent speed benchmark script."""

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "benchmark_opponents.py"


def test_benchmark_random_opponent_smoke():
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--only",
            "random",
            "--moves",
            "3",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert "random" in result.stdout
