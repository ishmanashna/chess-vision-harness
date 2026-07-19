#!/usr/bin/env bash
# Report disk usage for the harness games directory.
# Usage: ./deploy/games_disk_usage.sh
#        CHESS_HARNESS_DIR=/var/lib/chess-harness ./deploy/games_disk_usage.sh

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DATA_DIR="${CHESS_HARNESS_DIR:-$ROOT/.chess_harness}"
GAMES_DIR="$DATA_DIR/games"

if [[ ! -d "$GAMES_DIR" ]]; then
	echo "Games directory not found: $GAMES_DIR"
	exit 1
fi

count="$(find "$GAMES_DIR" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | wc -l | tr -d ' ')"
bytes="$(du -sb "$GAMES_DIR" 2>/dev/null | awk '{print $1}')"
mb="$(awk "BEGIN {printf \"%.2f\", $bytes / 1048576}")"

echo "Data dir:  $DATA_DIR"
echo "Games dir: $GAMES_DIR"
echo "Game dirs: $count"
echo "Total:     ${mb} MB (${bytes} bytes)"
