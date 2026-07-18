#!/usr/bin/env python3
"""Run root layout, line-limit check, TypeScript, full pytest, and ESLint."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYTHON = ROOT / "python"
FRONTEND = ROOT / "frontend"


def run(title: str, argv: list[str], *, cwd: Path = ROOT) -> int:
    print(f"\n=== {title} ===")
    print(" ".join(argv))
    completed = subprocess.run(argv, cwd=cwd)
    return int(completed.returncode)


def npm_cmd() -> str:
    return "npm.cmd" if sys.platform == "win32" else "npm"


def npx_cmd() -> str:
    return "npx.cmd" if sys.platform == "win32" else "npx"


def ensure_node_deps() -> int:
    if not (FRONTEND / "node_modules").is_dir():
        return run("npm install", [npm_cmd(), "install"], cwd=FRONTEND)
    return 0


def main() -> int:
    code = 0
    for title, argv, cwd in [
        ("Clean root", [sys.executable, str(ROOT / "scripts" / "check_clean_root.py")], ROOT),
        ("Line limit (≤300)", [sys.executable, str(ROOT / "scripts" / "check_line_limits.py")], ROOT),
    ]:
        rc = run(title, argv, cwd=cwd)
        if rc != 0:
            code = rc

    rc = ensure_node_deps()
    if rc != 0:
        return rc

    for title, argv, cwd in [
        ("TypeScript", [npx_cmd(), "tsc", "--noEmit", "--pretty", "false"], FRONTEND),
        ("Tests (full pytest)", [sys.executable, "-m", "pytest"], PYTHON),
        ("ESLint", [npx_cmd(), "eslint", ".", "--max-warnings", "0"], FRONTEND),
    ]:
        rc = run(title, argv, cwd=cwd)
        if rc != 0:
            code = rc

    print("\n=== quality_gate summary ===")
    if code == 0:
        print("All checks passed.")
    else:
        print("One or more checks failed.")
    return code


if __name__ == "__main__":
    if shutil.which(npm_cmd()) is None and shutil.which("npm") is None:
        print("npm is required for TypeScript and ESLint steps.", file=sys.stderr)
        sys.exit(1)
    sys.exit(main())
