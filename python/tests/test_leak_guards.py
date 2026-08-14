"""Unit tests for shared leak-guard helpers."""

from leak_guards import (
    assert_game_api_no_leaks,
    assert_identify_no_leak,
    assert_puzzle_no_leak,
)


def test_game_api_leak_guard_catches_forbidden_keys():
    try:
        assert_game_api_no_leaks({"ok": True, "board_fen": "x"})
        assert False, "expected assertion"
    except AssertionError as exc:
        assert "board_fen" in str(exc)


def test_game_api_leak_guard_allows_safe_payload():
    assert_game_api_no_leaks({"ok": True, "game_id": "g1", "your_turn": True})


def test_puzzle_leak_guard_nested():
    assert_puzzle_no_leak({"attempt_id": "p1", "status": "active"})
    try:
        assert_puzzle_no_leak({"rows": [{"solution_moves": ["e2e4"]}]})
        assert False, "expected assertion"
    except AssertionError as exc:
        assert "solution_moves" in str(exc)


def test_identify_leak_guard_catches_answer_keys():
    try:
        assert_identify_no_leak({"pieces": {"e4": "wP"}})
        assert False, "expected assertion"
    except AssertionError as exc:
        assert "pieces" in str(exc)
