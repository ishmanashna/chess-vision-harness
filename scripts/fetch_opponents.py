#!/usr/bin/env python3
"""Download Stockfish and MinimalChess binaries into bin/."""

from __future__ import annotations

import platform
import shutil
import sys
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BIN_DIR = ROOT / "bin"
OPP_DIR = BIN_DIR / "opponents"

STOCKFISH_RELEASE = "sf_17.1"
STOCKFISH_ASSETS = {
    "Windows": {
        "url": f"https://github.com/official-stockfish/Stockfish/releases/download/{STOCKFISH_RELEASE}/stockfish-windows-x86-64-avx2.zip",
        "kind": "zip",
        "exe_glob": "stockfish*.exe",
        "dest": BIN_DIR / "stockfish-windows-x86-64.exe",
    },
    "Linux": {
        "url": f"https://github.com/official-stockfish/Stockfish/releases/download/{STOCKFISH_RELEASE}/stockfish-ubuntu-x86-64-avx2.tar",
        "kind": "tar",
        "exe_glob": "stockfish*",
        "dest": BIN_DIR / "stockfish",
    },
    "Darwin": {
        "url": f"https://github.com/official-stockfish/Stockfish/releases/download/{STOCKFISH_RELEASE}/stockfish-macos-x86-64-avx2.tar",
        "kind": "tar",
        "exe_glob": "stockfish*",
        "dest": BIN_DIR / "stockfish",
    },
}

MINIMALCHESS_DOWNLOADS = [
    {
        "url": "https://github.com/lithander/MinimalChessEngine/releases/download/v0.2/MinimalChess.0.2.Windows.zip",
        "version": "0.2",
    },
    {
        "url": "https://github.com/lithander/MinimalChessEngine/releases/download/v0.3/MinimalChess.0.3.Windows.zip",
        "version": "0.3",
    },
]


def _download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"  fetch {url}")
    urllib.request.urlretrieve(url, dest)


def _find_binary(root: Path, pattern: str) -> Path:
    matches = sorted(root.rglob(pattern))
    if not matches:
        raise FileNotFoundError(f"No binary matching {pattern!r} under {root}")
    return matches[0]


def _install_minimalchess(zip_path: Path, version: str) -> None:
    if version == "0.2":
        out = OPP_DIR / "minimalchess-0.2.exe"
        if out.exists():
            print(f"  skip {out.relative_to(ROOT)} (exists)")
            return
        with zipfile.ZipFile(zip_path) as zf:
            exe = next(n for n in zf.namelist() if n.endswith(".exe"))
            with zf.open(exe) as src, open(out, "wb") as dst:
                shutil.copyfileobj(src, dst)
        print(f"  -> {out.relative_to(ROOT)}")
        return

    out_dir = OPP_DIR / "minimalchess-0.3"
    target = out_dir / "minimalchess-0.3.exe"
    if target.exists():
        print(f"  skip {target.relative_to(ROOT)} (exists)")
        return
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(out_dir)
    exe = next(out_dir.rglob("*.exe"))
    if exe != target:
        if target.exists():
            target.unlink()
        exe.rename(target)
    pst_src = next((p for p in out_dir.rglob("pst") if p.is_dir()), None)
    if pst_src and pst_src.parent != out_dir:
        shutil.move(str(pst_src), str(out_dir / "pst"))
    print(f"  -> {target.relative_to(ROOT)}")


def _install_stockfish(tmp: Path) -> None:
    system = platform.system()
    spec = STOCKFISH_ASSETS.get(system)
    if spec is None:
        print(f"  skip Stockfish auto-download on {system} — set STOCKFISH_PATH manually")
        return

    dest: Path = spec["dest"]
    if dest.exists():
        print(f"  skip {dest.relative_to(ROOT)} (exists)")
        return

    archive = tmp / Path(spec["url"]).name
    _download(spec["url"], archive)

    if spec["kind"] == "zip":
        extract_dir = tmp / "stockfish-zip"
        extract_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(extract_dir)
        src = _find_binary(extract_dir, spec["exe_glob"])
    else:
        extract_dir = tmp / "stockfish-tar"
        extract_dir.mkdir(parents=True, exist_ok=True)
        with tarfile.open(archive) as tf:
            tf.extractall(extract_dir, filter="data")
        src = _find_binary(extract_dir, spec["exe_glob"])

    shutil.copy2(src, dest)
    if system != "Windows":
        dest.chmod(dest.stat().st_mode | 0o111)
    print(f"  -> {dest.relative_to(ROOT)}")


def _install_minimalchess_all(tmp: Path) -> None:
    if platform.system() != "Windows":
        print("  skip MinimalChess on non-Windows (Windows builds only)")
        return
    OPP_DIR.mkdir(parents=True, exist_ok=True)
    for item in MINIMALCHESS_DOWNLOADS:
        zip_path = tmp / f"minimalchess-{item['version']}.zip"
        _download(item["url"], zip_path)
        _install_minimalchess(zip_path, item["version"])


def main() -> int:
    BIN_DIR.mkdir(parents=True, exist_ok=True)
    print("Downloading engine binaries...")
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        _install_stockfish(tmp)
        _install_minimalchess_all(tmp)
    print("Done. Run: chess-harness opponents verify")
    return 0


if __name__ == "__main__":
    sys.exit(main())
