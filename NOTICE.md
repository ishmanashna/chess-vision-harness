# Third-party engines and licenses

The **Chess Vision Harness** application code is licensed under the MIT License (see `LICENSE`).

Running games downloads or uses separate chess engine binaries. Those engines are **not**
covered by the MIT license. You are responsible for complying with each engine's license
when you download, run, or redistribute binaries.

| Component | License | How obtained |
|-----------|---------|--------------|
| Stockfish 17.1 | GPL-3.0 | `python scripts/fetch_opponents.py` or [official releases](https://github.com/official-stockfish/Stockfish/releases) |
| Patricia 5 | GPL-3.0 | `scripts/fetch_opponents.py` (Windows) |
| MinimalChess 0.2 / 0.3 | MIT | `scripts/fetch_opponents.py` (Windows) |
| Toledo Nanochess (UCI wrapper) | BSD-style | `scripts/fetch_opponents.py`; requires [Node.js](https://nodejs.org/) |

Engine license details and source links: `bin/opponents/LICENSES.md`.

**GPL note:** Stockfish and Patricia are GPL-licensed. If you distribute a package that
includes those binaries, GPL terms apply to that distribution. This repository ships
source code and download scripts only; binaries are gitignored.
