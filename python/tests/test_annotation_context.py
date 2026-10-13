"""Claimable-draw context must not rewrite engine assessments."""
import chess

from chess_harness.annotation_context import apply_terminal_context
from chess_harness.game_quality import analyse_game


REPETITION_MOVES = ["g1f3", "g8f6", "f3g1", "f6g8"] * 2


def _artifact(moves, *, after_cp=0, color=None, start_fen=None):
    board = chess.Board(start_fen or chess.STARTING_FEN)
    plies = []
    for index, uci in enumerate(moves):
        mover = "white" if board.turn else "black"
        board.push_uci(uci)
        is_last = index == len(moves) - 1
        plies.append({
            "ply": index + 1,
            "uci": uci,
            "color": color if is_last and color else mover,
            "before": {"cp": 120, "mate": None},
            "after": {"cp": after_cp if is_last else 85, "mate": None},
            "loss_cp": 120,
            "loss_percent": 4.25,
            "label": "good",
        })
    return {
        "status": "complete",
        "plies": plies,
    }


def test_resignation_after_winning_move_gets_unclaimed_threefold_context_only():
    state = {
        "status": "finished",
        "result": "0-1",
        "end_reason": "resignation",
        "moves": REPETITION_MOVES,
    }
    board = chess.Board()
    for move in REPETITION_MOVES:
        board.push_uci(move)
    assert not board.is_game_over()
    assert board.can_claim_threefold_repetition()

    artifact = _artifact(REPETITION_MOVES)
    original = artifact["plies"][-1].copy()
    result = apply_terminal_context(state, artifact)

    assert result is artifact
    row = artifact["plies"][-1]
    assert row["terminal_context"] == {
        "kind": "unclaimed_draw",
        "reason": "threefold repetition",
        "game_result": "0-1",
        "display_symbol": "=",
    }
    for key in ("before", "after", "loss_cp", "loss_percent", "label"):
        assert row[key] == original[key]


def test_resignation_after_fifty_move_claim_is_contextualized():
    start_fen = "7k/8/8/8/8/8/8/R6K w - - 99 1"
    moves = ["a1a2"]
    board = chess.Board(start_fen)
    board.push_uci(moves[0])
    assert not board.is_game_over()
    assert board.can_claim_fifty_moves()

    state = {
        "status": "finished",
        "result": "1-0",
        "end_reason": "resignation",
        "start_fen": start_fen,
        "moves": moves,
    }
    artifact = _artifact(moves, color="white", start_fen=start_fen)
    apply_terminal_context(state, artifact)
    assert artifact["plies"][0]["terminal_context"]["reason"] == "fifty-move rule"


def test_nonresignations_and_other_resignations_do_not_gain_context():
    for end_reason, result, moves in (
        ("resignation", "0-1", REPETITION_MOVES[:-1]),  # White moved last, Black won.
        ("checkmate", "0-1", REPETITION_MOVES),
        ("resignation", "0-1", ["g1f3", "g8f6"]),  # No draw claim is available.
    ):
        state = {
            "status": "finished",
            "result": result,
            "end_reason": end_reason,
            "moves": moves,
        }
        artifact = _artifact(moves)
        apply_terminal_context(state, artifact)
        row = artifact["plies"][-1]
        assert "terminal_context" not in row
        assert row["after"]["cp"] == 0
        assert row["label"] == "good"


def test_pgn_result_header_does_not_turn_injected_engine_score_into_zero():
    pgn = '[Result "0-1"]\n\n1. Nf3 Nf6 0-1'
    artifact = analyse_game(pgn, eval_fn=lambda board: 275).move_analysis
    assert artifact["plies"][-1]["after"]["cp"] == 275

    state = {
        "status": "finished",
        "result": "0-1",
        "end_reason": "resignation",
        "moves": ["g1f3", "g8f6"],
    }
    apply_terminal_context(state, artifact)
    assert "terminal_context" not in artifact["plies"][-1]
    assert artifact["plies"][-1]["after"]["cp"] == 275
