"""Tests for shared ladder display."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from chess_harness.ladder_display import format_opponent_ladder_cli, render_calibration_html
from chess_harness.opponents import get_catalog

from conftest import LOW_OPPONENT


def test_opponent_ladder_cli_lists_catalog_ids():
    text = format_opponent_ladder_cli(get_catalog())
    assert LOW_OPPONENT in text
    assert "random" in text
    assert "inverse-sf:abyss" in text
    assert "Stockfish handicaps" in text
    assert "stockfish:0" in text
    assert "patricia" not in text.lower()
    assert "stockfish-handicap:blitz50" not in text
    assert "Skill -5" not in text


def test_calibration_html_phase2_slim():
    html = render_calibration_html()
    assert "Quality samples" in html
    assert "Play rating" not in html
    assert "A Q" not in html
    assert "B Acc" not in html
    assert "function fmtEstDelta" not in html
    assert "function fmtEstimatorHoldout" not in html
    assert "No champion set" not in html
    assert 'colspan="6"' in html
    assert "function parFieldId" in html
    assert 'name="${esc(parId)}"' in html
    assert "running" not in html
    assert " live</span>" in html
