> **Archived snapshot (2026-07).** One-off move-time benchmark; Patricia/Toledo rows are historical. See `scripts/benchmark_opponent_move_times.py` to regenerate.

| Opponent | Type | Spawn ms | Move median ms | P95 ms | Games/hr est | Slow |
|----------|------|----------|----------------|--------|--------------|------|
| `random` | random | 0.0 | 0.1 | 0.2 | 356294.5 |  |
| `stockfish-handicap:depth4` | stockfish_harness | 717.7 | 5.2 | 18.3 | 3169.3 |  |
| `stockfish-handicap:depth4-noise10` | stockfish_harness | 733.5 | 5.7 | 29.5 | 3024.2 |  |
| `stockfish-handicap:depth6` | stockfish_harness | 506.2 | 15.7 | 52.5 | 2043.3 |  |
| `stockfish-handicap:depth8` | stockfish_harness | 512.0 | 38.9 | 78.6 | 993.5 |  |
| `minimalchess-0.2` | uci | 104.8 | 47.7 | 62.1 | 919.0 |  |
| `stockfish-handicap:blitz50` | stockfish_harness | 478.7 | 52.9 | 58.7 | 763.8 |  |
| `minimalchess-0.3` | uci | 112.2 | 55.1 | 92.1 | 796.8 |  |
| `stockfish-handicap:blitz100` | stockfish_harness | 501.8 | 102.4 | 111.1 | 413.9 |  |
| `stockfish-handicap:noise25` | stockfish_harness | 946.1 | 102.4 | 128.7 | 393.9 |  |
| `patricia:1000` | uci_elo | 28.3 | 102.8 | 109.1 | 436.2 |  |
| `patricia:1200` | uci_elo | 27.6 | 102.8 | 109.1 | 436.2 |  |
| `patricia:800` | uci_elo | 29.2 | 102.8 | 109.7 | 436.3 |  |
| `patricia:500` | uci_elo | 40.1 | 102.9 | 110.5 | 435.2 |  |
| `stockfish-handicap:noise10` | stockfish_harness | 747.3 | 104.2 | 113.3 | 396.2 |  |
| `stockfish-handicap:noise5` | stockfish_harness | 887.0 | 104.2 | 191.1 | 390.5 |  |
| `stockfish:17` | stockfish | 1409.4 | 104.2 | 120.5 | 369.3 |  |
| `stockfish:8` | stockfish | 1039.8 | 104.4 | 149.6 | 383.2 |  |
| `stockfish-handicap:noise20` | stockfish_harness | 911.4 | 104.5 | 115.0 | 388.4 |  |
| `stockfish:10` | stockfish | 990.7 | 105.2 | 112.9 | 382.8 |  |
| `stockfish:9` | stockfish | 994.2 | 105.2 | 139.9 | 382.7 |  |
| `stockfish:15` | stockfish | 906.7 | 105.6 | 176.3 | 384.8 |  |
| `stockfish:19` | stockfish | 1078.8 | 105.6 | 120.0 | 377.8 |  |
| `stockfish:2` | stockfish | 1012.1 | 105.6 | 137.8 | 380.5 |  |
| `stockfish-handicap:noise12` | stockfish_harness | 1500.0 | 105.7 | 162.1 | 361.5 |  |
| `stockfish:18` | stockfish | 795.8 | 105.8 | 123.5 | 388.9 |  |
| `stockfish:6` | stockfish | 861.1 | 106.4 | 133.7 | 384.1 |  |
| `stockfish:0` | stockfish | 1328.2 | 106.9 | 122.2 | 364.4 |  |
| `stockfish:11` | stockfish | 1077.0 | 107.2 | 122.4 | 372.9 |  |
| `stockfish:13` | stockfish | 1286.9 | 107.5 | 115.0 | 364.2 |  |
| `stockfish:20` | stockfish | 971.0 | 107.6 | 142.5 | 375.7 |  |
| `stockfish:5` | stockfish | 1205.9 | 107.8 | 125.5 | 366.1 |  |
| `stockfish-handicap:noise15` | stockfish_harness | 991.7 | 108.5 | 180.8 | 372.1 |  |
| `stockfish:16` | stockfish | 1111.7 | 108.6 | 139.7 | 367.3 |  |
| `stockfish:3` | stockfish | 1069.8 | 109.2 | 126.1 | 367.2 |  |
| `stockfish:1` | stockfish | 953.7 | 109.5 | 131.3 | 370.7 |  |
| `stockfish:14` | stockfish | 967.3 | 111.1 | 160.8 | 365.3 |  |
| `toledo` | uci | 74.4 | 112.3 | 145.8 | 397.3 |  |
| `stockfish:7` | stockfish | 904.2 | 114.8 | 124.8 | 356.9 |  |
| `stockfish:4` | stockfish | 1613.5 | 115.9 | 130.6 | 330.7 |  |
| `stockfish:12` | stockfish | 894.0 | 121.1 | 190.8 | 340.2 |  |
| `stockfish-handicap:depth10` | stockfish_harness | 605.1 | 189.6 | 245.4 | 228.2 |  |
| `stockfish-handicap:blitz200` | stockfish_harness | 717.2 | 205.5 | 215.6 | 209.8 |  |
| `stockfish-handicap:blitz350` | stockfish_harness | 1063.7 | 353.8 | 374.8 | 122.6 |  |
| `stockfish-handicap:blitz500` | stockfish_harness | 1014.3 | 511.2 | 526.9 | 85.9 | yes |
| `stockfish-handicap:depth12` | stockfish_harness | 689.0 | 729.0 | 1060.0 | 61.0 | yes |
| `stockfish-handicap:blitz800` | stockfish_harness | 1702.9 | 804.8 | 820.2 | 54.5 | yes |
| `stockfish-handicap:reference` | stockfish_harness | 1345.1 | 1005.9 | 1021.9 | 44.0 | yes |
| `stockfish-handicap:depth14` | stockfish_harness | 770.2 | 1151.3 | 1964.8 | 38.8 | yes |
| `stockfish-handicap:depth16` | stockfish_harness | 927.0 | 3565.2 | 6252.5 | 12.6 | yes |
| `stockfish-handicap:depth18` | stockfish_harness | 990.6 | 5693.9 | 8077.1 | 7.9 | yes |
