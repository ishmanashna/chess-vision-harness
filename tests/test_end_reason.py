import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from chess_harness.board_controller import BoardController


def test_format_end_reason_resignation():
    state = {"model_display_name": "Composer 2.5"}
    assert BoardController.format_end_reason("resignation", state) == "Composer 2.5 resigned"


def test_format_end_reason_inactivity():
    state = {"model_name": "mimo-v2.5"}
    assert BoardController.format_end_reason("inactivity", state) == "Inactivity timeout"
