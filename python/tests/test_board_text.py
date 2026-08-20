"""Tests for compact live board text."""

from __future__ import annotations

import chess

from chess_harness.board_text import bottom_color_for_board, format_board_text


def test_format_board_text_initial_position():
    text = format_board_text(chess.Board())
    lines = text.splitlines()

    assert lines[0] == "  a b c d e f g h"
    assert lines[1] == "8 r n b q k b n r"
    assert lines[2] == "7 p p p p p p p p"
    assert lines[7] == "2 P P P P P P P P"
    assert lines[8] == "1 R N B Q K B N R"
    assert lines[9] == "side_to_move: white"
    assert lines[10] == "in_check: no"
    assert "White=uppercase" in lines[11]
    assert len(lines[1:9]) == 8
    assert all(len(line.split()) == 9 for line in lines[1:9])


def test_format_board_text_names_empty_squares_and_orientation():
    board = chess.Board("8/3p4/8/4K3/8/8/8/4k3 w - - 0 1")
    text = format_board_text(board)

    assert "8 . . . . . . . ." in text
    assert "7 . . . p . . . ." in text
    assert "5 . . . . K . . ." in text
    assert "1 . . . . k . . ." in text
    assert "side_to_move: white" in text
    assert "fen" not in text.lower()
    assert "legal" not in text.lower()


def test_bottom_color_for_board():
    white_turn = chess.Board()
    black_turn = chess.Board(
        "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1"
    )
    assert bottom_color_for_board(white_turn) == "white"
    assert bottom_color_for_board(black_turn) == "black"


def test_format_board_text_black_at_bottom():
    board = chess.Board(
        "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1"
    )
    text = format_board_text(board, bottom_color="black")
    lines = text.splitlines()

    assert lines[0] == "  h g f e d c b a"
    assert lines[1] == "1 R N B K Q B N R"
    assert lines[8] == "8 r n b k q b n r"
    assert lines[9] == "side_to_move: black"
    assert all(len(line.split()) == 9 for line in lines[1:9])
