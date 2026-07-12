# Opponent engine licenses

Binaries are downloaded by `scripts/fetch_opponents.py` (not committed to git).

| ID | Engine | ELO | License | Source |
|----|--------|-----|---------|--------|
| patricia:500–1200 | Patricia 5 (SSE) | 500–1200 | GPL-3.0 | [Adam-Kulju/Patricia](https://github.com/Adam-Kulju/Patricia) |
| minimalchess-0.2 | MinimalChess 0.2 | 909 (CCRL) | MIT | [lithander/MinimalChessEngine](https://github.com/lithander/MinimalChessEngine) |
| toledo | Toledo Nanochess (UCI wrapper) | 1017 (CCRL) | BSD-style | [ecrucru/toledo-uci](https://github.com/ecrucru/toledo-uci) |
| minimalchess-0.3 | MinimalChess 0.3 | 1439 (CCRL) | MIT | [lithander/MinimalChessEngine](https://github.com/lithander/MinimalChessEngine) |

Stockfish tiers (`stockfish:0`–`20`) use `bin/stockfish-windows-x86-64.exe` (GPL-3).

Patricia sub-1320 tiers use `UCI_LimitStrength` + `UCI_Elo` (author calibration).
Toledo requires [Node.js](https://nodejs.org/) on PATH.
