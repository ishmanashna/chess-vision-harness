# Opponent binaries

Engine binaries are **not committed to git**. Install with:

```bash
python scripts/fetch_opponents.py
python play.py opponents verify
```

## Layout (after fetch)

```
bin/
  stockfish-windows-x86-64.exe   # Windows — Stockfish 17.1 (GPL-3)
  stockfish                      # Linux/macOS — from fetch script
  opponents/
    patricia_v2.exe
    minimalchess-0.2.exe
    minimalchess-0.3/minimalchess-0.3.exe
    toledo-uci.js                # requires Node.js
```

Catalog: `opponents.json` at project root.

## Platform notes

| OS | Stockfish | Tiny engines |
|----|-----------|--------------|
| Windows | Auto-download (sf_17.1 avx2 zip) | Auto-download |
| Linux | Auto-download (ubuntu avx2 tar) or `apt install stockfish` | Set `STOCKFISH_PATH`; Patricia/MinimalChess are Windows builds |
| macOS | Auto-download (macos avx2 tar) | Windows `.exe` opponents not available |

Override with `STOCKFISH_PATH` if you use a system install.

## Licenses

See `bin/opponents/LICENSES.md` and root `NOTICE.md`.
