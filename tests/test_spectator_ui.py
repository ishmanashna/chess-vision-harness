import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from chess_harness.spectator import _board_stack_labels, _eval_ui, _move_rows


def test_board_stack_labels_flipped_for_black_agent():
    labels = {"black": "Composer 2.5", "white": "Patricia 5 (800)"}
    stack = _board_stack_labels(labels, "BLACK")
    assert stack == {"top": "Patricia 5 (800)", "bottom": "Composer 2.5"}


def test_eval_ui_includes_stack_labels_for_black_agent():
    ui = _eval_ui(90, {"black": "Composer 2.5", "white": "Patricia 5 (800)"}, "BLACK")
    assert ui["top_label"] == "Patricia 5 (800)"
    assert ui["bottom_label"] == "Composer 2.5"


def test_eval_black_pct_white_ahead():
    ui = _eval_ui(90, {"black": "Engine", "white": "Agent"})
    assert float(ui["black_pct"].rstrip("%")) < 50
    assert ui["text"] == "+0.9"


def test_eval_black_pct_black_ahead():
    ui = _eval_ui(-460, {"black": "Engine", "white": "Agent"})
    assert float(ui["black_pct"].rstrip("%")) > 50
    assert ui["text"] == "-4.6"


def test_move_rows_san():
    state = {
        "start_fen": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
        "moves": ["e2e4", "e7e5", "g1f3"],
    }
    rows = _move_rows(state)
    assert rows == [
        {"num": 1, "white": "e4", "black": "e5"},
        {"num": 2, "white": "Nf3", "black": ""},
    ]


from conftest import LOW_OPPONENT


def test_leaderboard_uses_opponent_catalog():
    from chess_harness.ladder_display import render_leaderboard_html
    from chess_harness.elo import ELOLadder
    from chess_harness.paths import resolve_base_dir

    html = render_leaderboard_html(ELOLadder(base_dir=str(resolve_base_dir())))
    assert "Opponent Ladder" in html
    assert LOW_OPPONENT in html
    assert "random" in html
    assert "inverse-sf:abyss" in html
    assert "Stockfish handicaps" in html
    assert "stockfish:0" in html
    assert "patricia" not in html.lower()
    assert "stockfish-handicap:blitz50" not in html
    assert "Skill -5" not in html
    assert "Stockfish Reference" not in html
