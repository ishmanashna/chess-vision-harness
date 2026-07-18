# Third-party engines and licenses

The **Chess Vision Harness** application code is licensed under the MIT License (see [`docs/LICENSE.md`](docs/LICENSE.md)).

Running games downloads separate chess engine binaries. Those engines are **not**
covered by the MIT license. You are responsible for complying with each engine's
license when you download, run, or redistribute binaries.

| Component | License | How obtained |
|-----------|---------|--------------|
| Stockfish 17.1 | GPL-3.0 | `python scripts/fetch_opponents.py` or [official releases](https://github.com/official-stockfish/Stockfish/releases) |
| MinimalChess 0.2 / 0.3 (optional) | MIT | `python scripts/fetch_opponents.py` (Windows); used only for backup harness rungs |

Per-engine details: [`bin/opponents/LICENSES.md`](../bin/opponents/LICENSES.md).

**GPL note:** Stockfish is GPL-licensed. If you distribute a package that
includes the Stockfish binary, GPL terms apply to that distribution. This
repository ships source code and download scripts only; binaries are gitignored.
