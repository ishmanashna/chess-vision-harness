"""Tests for post-game move-quality analysis."""

import os
import sys

import chess
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from chess_harness.game_quality import (
    BLUNDER_WIN_PROB_LOSS,
    DEFAULT_QUALITY_DEPTH,
    THIN_MOVES_PER_SIDE,
    analyse_game,
    default_quality_depth,
    _move_accuracy,
    _win_percent,
)

STOCKFISH_BIN = os.path.join(
    os.path.dirname(__file__), "..", "bin", "stockfish-windows-x86-64.exe"
)


class ScriptedEval:
    """Position eval script keyed by half-move index (0 = start, before first move)."""

    def __init__(self, cp_by_index: dict[int, int]):
        self.cp_by_index = cp_by_index
        self._call = 0

    def __call__(self, board: chess.Board) -> int:
        idx = len(board.move_stack)
        self._call += 1
        return self.cp_by_index.get(idx, 0)


def test_win_percent_and_move_accuracy_constants():
    assert _win_percent(0) == 50.0
    assert _move_accuracy(50.0, 50.0) == 100.0
    # ~25% win-prob loss from equal → blunder tier
    wp0 = _win_percent(0)
    wp_bad = _win_percent(-600)
    acc = _move_accuracy(wp0, wp_bad)
    assert acc < 80.0
    assert (wp0 - wp_bad) / 100.0 > BLUNDER_WIN_PROB_LOSS


def test_perfect_game_high_accuracy():
    moves = ["e2e4", "e7e5", "g1f3", "b8c6", "f1c4", "g8f6"]
    result = analyse_game(moves, depth=8, eval_fn=ScriptedEval({}))
    assert result.quality_depth == 8
    assert result.quality_thin is True  # 3 moves per side
    assert result.white.accuracy == 100.0
    assert result.black.accuracy == 100.0
    assert result.white.acpl == 0.0
    assert result.white.blunder_rate == 0.0
    assert result.white.normalized_acpl == 0.0


def test_blunder_game_scores_lower():
    # White blunders every move; black stays even.
    cp = {
        0: 0,
        1: -600,
        2: -600,
        3: -1200,
        4: -1200,
        5: -1800,
    }
    moves = ["e2e4", "e7e5", "g1f3", "b8c6"]
    result = analyse_game(moves, depth=8, eval_fn=ScriptedEval(cp))

    assert result.white.accuracy is not None
    assert result.black.accuracy == 100.0
    assert result.white.accuracy < result.black.accuracy
    assert result.white.acpl > result.black.acpl
    assert result.white.blunder_rate > 0.0
    assert result.white.blunder_count >= 1


def test_quality_thin_short_game():
    moves = ["e2e4", "e7e5", "g1f3", "b8c6", "f1c4"]
    thin = analyse_game(moves, eval_fn=ScriptedEval({}))
    assert thin.quality_thin is True

    long_moves = [
        "e2e4", "e7e5", "g1f3", "b8c6", "f1b5", "a7a6",
        "b5a4", "b7b5", "a4b3", "g8f6",
    ]
    not_thin = analyse_game(long_moves, eval_fn=ScriptedEval({}))
    assert not_thin.quality_thin is False
    assert not_thin.white.move_count == THIN_MOVES_PER_SIDE


def test_quality_depth_from_argument_and_env(monkeypatch):
    monkeypatch.delenv("QUALITY_STOCKFISH_DEPTH", raising=False)
    assert default_quality_depth() == DEFAULT_QUALITY_DEPTH

    monkeypatch.setenv("QUALITY_STOCKFISH_DEPTH", "12")
    assert default_quality_depth() == 12

    result = analyse_game(["e2e4", "e7e5"], depth=15, eval_fn=ScriptedEval({}))
    assert result.quality_depth == 15


def test_pgn_input():
    pgn = (
        '[Event "Test"]\n'
        '[White "A"]\n[Black "B"]\n[Result "1-0"]\n\n'
        "1. e4 e5 2. Nf3 Nc6 *"
    )
    result = analyse_game(pgn, eval_fn=ScriptedEval({}))
    assert result.white.move_count == 2
    assert result.black.move_count == 2


@pytest.mark.skipif(not os.path.isfile(STOCKFISH_BIN), reason="Stockfish binary not available")
def test_live_stockfish_shallow():
    os.environ.setdefault("STOCKFISH_PATH", STOCKFISH_BIN)
    moves = ["e2e4", "e7e5", "g1f3", "b8c6", "f1c4", "f8c5"]
    result = analyse_game(moves, depth=6)
    assert result.quality_depth == 6
    assert result.white.accuracy is not None
    assert 0 <= result.white.accuracy <= 100
    assert result.white.acpl is not None
