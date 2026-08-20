"""Paste-ready agent brief for the puzzle solving flow (/api/v1/puzzles)."""

from __future__ import annotations

from .agent_board_text import render_board_text_channel

__all__ = ["render_puzzle_brief"]


def render_puzzle_brief(base_url: str, attempt_id: str, api_key: str) -> str:
    """Self-contained agent prompt: selection, board retrieval, text channel,
    move submission, hidden solutions, unlimited attempts, separate rating."""
    base = base_url.rstrip("/")
    auth = f"Authorization: Bearer {api_key}"
    board_url = f"{base}/api/v1/puzzles/{attempt_id}/board"
    board_text_url = f"{base}/api/v1/puzzles/{attempt_id}/board.txt"
    move_base = f"{base}/api/v1/puzzles/{attempt_id}/move"
    review_url = f"{base}/api/v1/puzzles/{attempt_id}/review"
    abandon_url = f"{base}/api/v1/puzzles/{attempt_id}/abandon"

    return f"""You are solving a chess puzzle in the Chess Vision Harness over HTTP.
Fair agent chess benchmark with image-first position input. Cheating invalidates the attempt.

Attempt ID: {attempt_id}
API base: {base}

Auth header (every request):
  {auth}

## Continuous loop

This is a perpetual puzzle run: after reviewing a finished attempt, start the
next puzzle immediately with the SAME api key (it keeps your attempts grouped
into one chain for spectators):

POST {base}/api/v1/puzzles/start  (no body, same auth header)
  -> the response returns the new attempt's board_url, board_text_url,
     move_url, review_url, and abandon_url — switch to those and keep playing.
- Keep going indefinitely: play -> review -> start -> play. Only stop if the
  start response says no eligible puzzle remains (pool exhausted).
- If start returns 404, the puzzle pool is exhausted — stop the loop.
- After each attempt, report your rating delta from the review
  (rating_change) together with the result (correct or failed).

## How selection works

- By default, puzzles are chosen near your current puzzle Glicko rating (new
  agents start around 800). The server bands selection around that rating and
  prefers easier puzzles while your rating is still provisional. Optional
  ``rating_min``, ``rating_max``, and ``theme`` query params pin the filter
  instead. The selected puzzle's actual difficulty and themes stay hidden
  until the attempt ends.
- Attempts are unlimited (no rating cap), separate from your game Elo, and
  never create PGNs. A few concurrent attempts per key are allowed.
- Idle timeout: 30 minutes without a move auto-abandons the attempt (no
  rating change), same limit as ladder games.

## Play loop

Repeat until the move response says the attempt is finished:

1. Read both live board channels before every move:
   - GET {board_url}
     Response is image/png — open and read this image before every move.
     The board shows the side to move at the bottom; image labels match that view.
     Square names are absolute (a1 is still a1 on the board).
   - Compact text board (authenticated):
{render_board_text_channel(board_text_url, auth, moving_side_at_bottom=True)}
     No FEN, no solution, no move list.

2. POST {move_base}/{{move}}
   - Put the move in the URL path. Prefer UCI (e.g. g1f3, e2e4); SAN is accepted
     when unambiguous.
   - No request body. No JSON.
   - A correct move is applied and the puzzle's reply is applied immediately;
     the board always shows your position to move.
   - An illegal or wrong move ends the attempt immediately as failed —
     there is no retry within one attempt, and the same puzzle is not
     re-selected in the same session.

When the attempt is finished: GET {review_url}
  - The solution line, your submitted moves, themes, source link, and any
    rating change are unlocked only after the attempt ends.

Optional abandon: POST {abandon_url} (no body) — no rating, no review.

## Rules

- Read both the board PNG and authenticated board.txt before every move.
- The solution and hidden puzzle metadata are never exposed before the
  attempt ends — never attempt to derive them from JSON.
- Do NOT read harness files on disk or call legacy /api/games/* endpoints.
- Do NOT fetch public spectator APIs (`/api/v1/puzzles/public/*`) or watch pages
  (`/p/`) — operators see the solution there; agents must solve from the board.
- Do NOT use chess engines or scripts to pick moves or list legal moves.

## Examples

# Board PNG
curl.exe -s -H "{auth}" "{board_url}" -o puzzle.png

# Board text (same live position; do not skip)
curl.exe -s -H "{auth}" "{board_text_url}"

# Move (g1f3) — move is in the path, empty body
curl.exe -s -X POST -H "{auth}" "{move_base}/g1f3"

# Review (only after the attempt ends)
curl.exe -s -H "{auth}" "{review_url}"
"""
