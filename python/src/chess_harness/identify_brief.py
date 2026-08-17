"""Paste-ready agent brief for the board-identification flow (/api/v1/identify)."""

from __future__ import annotations

from .agent_board_text import render_board_text_channel

__all__ = ["render_identify_brief"]


def render_identify_brief(base_url: str, attempt_id: str, api_key: str) -> str:
    """Self-contained agent prompt: identify only, answer schema, PNG and
    board.txt, hard no-moves rule, review after completion."""
    base = base_url.rstrip("/")
    auth = f"Authorization: Bearer {api_key}"
    board_url = f"{base}/api/v1/identify/{attempt_id}/board"
    board_text_url = f"{base}/api/v1/identify/{attempt_id}/board.txt"
    answer_url = f"{base}/api/v1/identify/{attempt_id}/answer"
    review_url = f"{base}/api/v1/identify/{attempt_id}/review"
    abandon_url = f"{base}/api/v1/identify/{attempt_id}/abandon"

    return f"""You are identifying a chess position in the Chess Vision Harness over HTTP.
Fair agent chess benchmark with image-first position input. Cheating invalidates the attempt.

Attempt ID: {attempt_id}
API base: {base}

Auth header (every request):
  {auth}

## Continuous loop

This is a perpetual identification run: after reviewing a finished attempt,
start the next one immediately with the SAME api key (it keeps your attempts
grouped into one chain for spectators):

POST {base}/api/v1/identify/start  (no body, same auth header)
  -> the response returns the new attempt's board_url, board_text_url,
     answer_url, review_url, and abandon_url — switch to those and keep going.
- Keep going indefinitely: identify -> review -> start -> identify. Only stop
  if the start response says no eligible position remains (pool exhausted).
- If start returns 404, the pool is exhausted — stop the loop.
- After each attempt, report your accuracy from the review together with the
  result (correct or failed).
- Idle timeout: 30 minutes without submitting an answer auto-abandons the
  attempt (no rating), same limit as ladder games.

## Task — identify ONLY. No moves.

You are shown a chess board image. Look at it and report where every piece
(and only the pieces) sits. You must NOT play a move, evaluate the position,
or reason about the game.

## Answer schema (exact)

Submit a JSON body listing ONLY occupied squares, each value a color letter
(``w`` or ``b``) plus a piece letter (``K Q R B N P``):

    POST {answer_url}
    Content-Type: application/json
    {{ "pieces": {{ "a1": "wR", "e8": "bK", "g1": "wN", ... }} }}

- Keys are absolute squares; a1 is the bottom-left square of the image.
- Values are uppercase piece letters: K king, Q queen, R rook, B bishop,
  N knight, P pawn.
- Every occupied square must appear; empty squares must not.
- The schema is validated exactly: legal squares, legal piece codes, no extra
  or duplicate pieces. A malformed answer is rejected (HTTP 400) without
  ending the attempt — resubmit a well-formed one.

## Play loop

1. Read both board channels before answering:
   - GET {board_url}
     Response is image/png — open and read this image before answering.
     The board is always white at bottom with absolute square labels (a1 is bottom-left).
     Your color does not flip it.
   - Compact text board (authenticated):
{render_board_text_channel(board_text_url, auth)}
     No FEN and no machine-readable answer beyond the visible board.

2. POST {answer_url} with the placement JSON above.
   - Submission is final: the attempt is scored immediately and ends.
   - Result ``correct`` means the placement matched exactly; ``failed`` means
     any square/color/type was wrong.

After the attempt ends: GET {review_url}
  - Your submitted placement, the true placement, per-square errors, score,
    accuracy, and difficulty are revealed only after submission.

Optional abandon: POST {abandon_url} (no body) — no review.

## Rules

- Read both the board PNG and authenticated board.txt before answering.
- The true placement and position difficulty are never exposed before you
  submit — never attempt to derive them from JSON.
- Do NOT read harness files on disk or call legacy /api/games/* endpoints.
- Do NOT use chess engines or scripts to generate or check the placement.

## Examples

# Board PNG
curl.exe -s -H "{auth}" "{board_url}" -o board.png

# Board text (same live position; do not skip)
curl.exe -s -H "{auth}" "{board_text_url}"

# Submit placement (final — no retry)
curl.exe -s -X POST -H "{auth}" -H "Content-Type: application/json" -d "{{\\"pieces\\": {{\\"e2\\": \\"wP\\", \\"e7\\": \\"bP\\"}}}}" "{answer_url}"

# Review (only after submission)
curl.exe -s -H "{auth}" "{review_url}"
"""