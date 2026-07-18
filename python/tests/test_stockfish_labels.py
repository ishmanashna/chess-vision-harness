import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from chess_harness.elo import format_skill_label, format_stockfish_label


def test_stockfish_label_negative_skill():
    assert format_stockfish_label(-5) == "Stockfish 17.1 (Skill -5)"
    assert format_stockfish_label(-1) == "Stockfish 17.1 (Skill -1)"


def test_stockfish_label_positive_skill():
    assert format_stockfish_label(5) == "Stockfish 17.1 (Skill 5)"


def test_skill_label_no_depth():
    assert format_skill_label(-5) == "Skill -5"
    assert "depth" not in format_skill_label(-5)
    assert format_skill_label(10) == "Skill 10"
