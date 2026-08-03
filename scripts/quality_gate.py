#!/usr/bin/env python3
"""Run root layout, line-limit check, TypeScript, full pytest, and ESLint."""

from __future__ import annotations

import argparse
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


def git_status() -> str:
    result = subprocess.run(
        ["git", "status", "--short"], cwd=ROOT, capture_output=True, text=True, check=True
    )
    return result.stdout


def npm_cmd() -> str:
    return "npm.cmd" if sys.platform == "win32" else "npm"


def npx_cmd() -> str:
    return "npx.cmd" if sys.platform == "win32" else "npx"


def ensure_node_deps() -> int:
    if not (FRONTEND / "node_modules").is_dir():
        return run("npm install", [npm_cmd(), "install"], cwd=FRONTEND)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check-worktree",
        action="store_true",
        help="fail if tracked/untracked status changes during validation",
    )
    args = parser.parse_args()
    before_status = git_status() if args.check_worktree else None
    code = 0
    for title, argv, cwd in [
        ("Clean root", [sys.executable, str(ROOT / "scripts" / "check_clean_root.py")], ROOT),
        ("Line limit (<=300)", [sys.executable, str(ROOT / "scripts" / "check_line_limits.py")], ROOT),
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

    if args.check_worktree:
        after_status = git_status()
        if after_status != before_status:
            print("\n=== Worktree check FAILED ===")
            print("Validation changed repository status unexpectedly.")
            code = 1

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
