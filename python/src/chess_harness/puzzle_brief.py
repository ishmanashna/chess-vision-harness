"""Paste-ready agent brief for the puzzle solving flow (/api/v1/puzzles)."""

from __future__ import annotations

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

- A puzzle was selected at random from the imported corpus, filtered by any
  requested rating band and theme. The selected puzzle's actual difficulty
  and themes stay hidden until the attempt ends.
- Attempts are unlimited (no rating cap), separate from your game Elo, and
  never create PGNs. A few concurrent attempts per key are allowed.
- Idle timeout: 30 minutes without a move auto-abandons the attempt (no
  rating change), same limit as ladder games.

## Play loop

Repeat until the move response says the attempt is finished:

1. Read the live board position before every move:
   - Preferred: GET {board_url}
     Response is image/png — open and read this image before every move.
     The board is always white at bottom with absolute square labels (a1 is bottom-left).
   - Also valid (authenticated): GET {board_text_url}
     Same board as eight compact rows; no FEN, no solution, no move list.
     Prefer the PNG for vision; text is always allowed when authenticated.

2. POST {move_base}/{{move}}
   - Put the move in the URL path (UCI or SAN). Example: .../move/g1f3
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

- Read the position from the board PNG (preferred) or authenticated board.txt — both are valid.
- The solution and hidden puzzle metadata are never exposed before the
  attempt ends — never attempt to derive them from JSON.
- Do NOT read harness files on disk or call legacy /api/games/* endpoints.
- Do NOT use chess engines or scripts to pick moves or list legal moves.

## Examples

# Board PNG (preferred)
curl.exe -s -H "{auth}" "{board_url}" -o puzzle.png

# Board text (authenticated; also valid)
curl.exe -s -H "{auth}" "{board_text_url}"

# Move (g1f3) — move is in the path, empty body
curl.exe -s -X POST -H "{auth}" "{move_base}/g1f3"

# Review (only after the attempt ends)
curl.exe -s -H "{auth}" "{review_url}"
"""
