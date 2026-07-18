# Opponent binaries

Only **Stockfish** is required. Install with:

```bash
python scripts/fetch_opponents.py
chess-harness opponents verify
```

Legacy third-party engines (Patricia, MinimalChess, Toledo) were removed from the ladder. If old binaries remain:

```bash
python scripts/remove_legacy_opponent_binaries.py
```

## Layout (after fetch)

```
bin/
  stockfish-windows-x86-64.exe   # Windows — Stockfish 17.1 (GPL-3)
  stockfish                      # Linux/macOS — from fetch script
```

Catalog: `opponents.json` at project root (Stockfish harness + inverse modes only).

## Platform notes

| OS | Stockfish |
|----|-----------|
| Windows | Auto-download (sf_17.1 avx2 zip) |
| Linux | Auto-download (ubuntu avx2 tar) or `apt install stockfish` |
| macOS | Auto-download (macos avx2 tar) |

Override with `STOCKFISH_PATH` if you use a system install.

## Licenses

See root `NOTICE.md` (Stockfish GPL-3).
