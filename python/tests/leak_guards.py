"""Shared helpers for agent/observer API leak assertions."""

from __future__ import annotations

from typing import Any, Iterable

# Game agent HTTP surface must not expose position shortcuts.
GAME_API_FORBIDDEN_KEYS = frozenset({"fen", "board_fen", "moves", "start_fen"})

# Imagine error payloads must not echo raw image bytes.
IMAGINE_FORBIDDEN_KEYS = GAME_API_FORBIDDEN_KEYS | frozenset({"png_bytes"})

# Public puzzle watch: solution line is operator-visible; hide corpus internals.
PUZZLE_LEAK_KEYS = frozenset(
    {
        "board_fen",
        "start_fen",
        "puzzle_id",
    }
)

# Public identify watch: correct placement is operator-visible; hide submissions.
IDENTIFY_LEAK_KEYS = frozenset(
    {
        "pieces",
        "submitted_pieces",
        "per_square",
        "corpus_fen",
        "puzzle_id",
        "puzzle_rating",
        "board_fen",
        "solution_moves",
    }
)


def assert_no_keys(obj: Any, forbidden: Iterable[str], *, label: str = "leaked key") -> None:
    """Recursively assert *forbidden* keys are absent from nested JSON-like data."""
    forbidden_set = frozenset(forbidden)
    if isinstance(obj, dict):
        for key, value in obj.items():
            assert key not in forbidden_set, f"{label}: {key}"
            assert_no_keys(value, forbidden_set, label=label)
    elif isinstance(obj, list):
        for item in obj:
            assert_no_keys(item, forbidden_set, label=label)


def assert_game_api_no_leaks(obj: Any) -> None:
    assert_no_keys(obj, GAME_API_FORBIDDEN_KEYS, label="leaked game API key")


def assert_imagine_no_leaks(obj: Any) -> None:
    assert_no_keys(obj, IMAGINE_FORBIDDEN_KEYS, label="leaked imagine key")


def assert_puzzle_no_leak(obj: Any) -> None:
    assert_no_keys(obj, PUZZLE_LEAK_KEYS, label="leaked puzzle observer key")


def assert_identify_no_leak(obj: Any) -> None:
    assert_no_keys(obj, IDENTIFY_LEAK_KEYS, label="leaked identify key")
