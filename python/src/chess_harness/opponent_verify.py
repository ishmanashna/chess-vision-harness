"""UCI smoke tests for catalog opponents."""

from __future__ import annotations

import chess
import sys

from .opponents import get_catalog


def verify_opponent(opponent_id: str) -> bool:
    catalog = get_catalog()
    opp = catalog.get(opponent_id)
    if not catalog._is_playable(opp):
        print(f"  SKIP {opponent_id}: not playable (binary missing)")
        return False

    from .engine import OpponentEngineManager

    mgr = OpponentEngineManager()
    board = chess.Board()
    try:
        result = mgr.play(opp, board, time_limit=0.5)
        move = result.move
        print(f"  OK   {opponent_id}: {move.uci()}")
        return True
    except Exception as e:
        print(f"  FAIL {opponent_id}: {e}")
        return False
    finally:
        mgr.release()


def verify_all_opponents() -> int:
    catalog = get_catalog()
    ok = 0
    fail = 0
    skip = 0
    print("Verifying opponents...")
    for opp in catalog.list_opponents():
        if not catalog._is_playable(opp):
            print(f"  SKIP {opp.id}: not playable")
            skip += 1
            continue
        if verify_opponent(opp.id):
            ok += 1
        else:
            fail += 1
    print(f"Done: {ok} ok, {fail} failed, {skip} skipped")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(verify_all_opponents())
