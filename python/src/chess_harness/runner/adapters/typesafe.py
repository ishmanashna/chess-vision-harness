"""TypeSafe Jev (System One) adapter: Choice over legal UCI moves."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import chess

from ...agent_http.transport import DEFAULT_USER_AGENT, decode_json, request_with_retries
from .board_parse import pieces_from_board_text

TransportFn = Callable[
    [str, str, Dict[str, str], Optional[bytes]], Tuple[int, Dict[str, str], bytes]
]

_DEFAULT_BASE = "https://api.typesafe.ai/v1"
_DEFAULT_MODEL = "jev-latest"
_FALLBACK_KEY_PATHS = (
    Path(r"C:\Users\jordi\Desktop\coding stuff\keys\typesafe_api_key.txt"),
)


def board_from_board_text(board_text: str) -> chess.Board:
    """Rebuild a Board from harness board.txt.

    Castling and en passant are cleared — safer than inventing rights the
    text channel does not expose. Harness still validates the submitted UCI.
    """
    lines = [ln.rstrip() for ln in board_text.splitlines() if ln.strip()]
    if len(lines) < 9:
        raise ValueError("board_text too short to parse")

    header = lines[0].strip()
    files = list("hgfedcba") if header.startswith("h ") else list("abcdefgh")

    board = chess.Board(None)
    side = "white"
    for line in lines[1:]:
        parts = line.split()
        if not parts:
            continue
        low = line.lower()
        if low.startswith("side_to_move:") or low.startswith("side to move:"):
            side = parts[-1].strip().lower()
            continue
        if low.startswith("in_check:") or low.startswith("legend:"):
            continue
        if not parts[0].isdigit():
            continue
        rank = int(parts[0])
        for index, symbol in enumerate(parts[1:]):
            if symbol == "." or index >= len(files):
                continue
            square = chess.parse_square(files[index] + str(rank))
            board.set_piece_at(square, chess.Piece.from_symbol(symbol))

    board.turn = chess.WHITE if side.startswith("w") else chess.BLACK
    board.castling_rights = 0
    board.ep_square = None
    return board


def legal_uci(board: chess.Board) -> List[str]:
    moves = [move.uci() for move in board.legal_moves]
    if not moves:
        raise RuntimeError("no legal moves from reconstructed board")
    return moves


def pick_choice(answer: Dict[str, Any], legal: List[str]) -> str:
    legal_set = set(legal)
    chosen = str(answer.get("choice") or "").strip().lower()
    if chosen in legal_set:
        return chosen
    probs = answer.get("probabilities") or {}
    if isinstance(probs, dict) and probs:
        ranked = sorted(
            (
                (str(k).lower(), float(v))
                for k, v in probs.items()
                if str(k).lower() in legal_set
            ),
            key=lambda kv: kv[1],
            reverse=True,
        )
        if ranked:
            return ranked[0][0]
    return legal[0]


class TypesafeAdapter:
    """Jev via TypeSafe System One — code owns legal moves; model picks among them."""

    provider = "typesafe"

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        env_key: str,
        transport: TransportFn,
        observation: str = "text",
        jpeg_max_side: Optional[int] = None,
        spirit: Optional[str] = None,
        duplicate_board: bool = False,
    ):
        self.base_url = (base_url or _DEFAULT_BASE).rstrip("/")
        if self.base_url.endswith("/systemone"):
            self.base_url = self.base_url[: -len("/systemone")]
        self.model = model or _DEFAULT_MODEL
        self.env_key = env_key or "TYPESAFE_API_KEY"
        self.observation = observation
        self._transport = transport
        self.jpeg_max_side = jpeg_max_side
        self.spirit = (spirit or "").strip() or None
        self.duplicate_board = bool(duplicate_board)
        self.last_raw: Optional[Dict[str, Any]] = None
        self.last_usage: Optional[Dict[str, Any]] = None

    def _api_key(self) -> str:
        key = os.getenv(self.env_key, "").strip()
        if key:
            return key
        for path in _FALLBACK_KEY_PATHS:
            try:
                if path.is_file():
                    text = path.read_text(encoding="utf-8").strip()
                    if text:
                        return text.splitlines()[0].strip()
            except OSError:
                continue
        raise RuntimeError(
            f"missing provider env {self.env_key} (and no fallback key file)"
        )

    def _systemone(self, *, state: Any, questions: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.base_url}/systemone"
        body = json.dumps(
            {"state": state, "model": self.model, "questions": questions},
            ensure_ascii=False,
        ).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {self._api_key()}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": DEFAULT_USER_AGENT,
        }
        status, _resp_headers, content = request_with_retries(
            self._transport, "POST", url, headers, body
        )
        payload = decode_json(content) if content else {}
        if status == 429:
            raise RuntimeError("typesafe rate limited")
        if status >= 400:
            raise RuntimeError(f"typesafe HTTP {status}: {payload or content!r}")
        self.last_raw = payload if isinstance(payload, dict) else None
        if isinstance(payload, dict):
            usage = payload.get("usage")
            self.last_usage = usage if isinstance(usage, dict) else None
        return payload if isinstance(payload, dict) else {}

    def choose_move(self, *, board_text: str, board_png: Optional[bytes] = None) -> str:
        del board_png  # v1 text-only; legal list comes from reconstructed board
        board = board_from_board_text(board_text)
        legal = legal_uci(board)
        side = "white" if board.turn == chess.WHITE else "black"
        criteria = {uci: None for uci in legal}
        shown = board_text
        if self.duplicate_board:
            shown = board_text.rstrip() + "\n\n---\n\n" + board_text.lstrip()
        default_note = "Pick one legal UCI move."
        note = self.spirit or default_note
        state = {
            "task": "chess",
            "side_to_move": side,
            "board_text": shown,
            "note": note,
        }
        if self.duplicate_board:
            state["board_text_repeat"] = "same position shown twice"
        instructions = (
            f"You are playing chess as {side}. "
            "Choose the single best legal move from the criteria keys (UCI)."
        )
        if self.spirit:
            instructions = (
                f"You are playing chess as {side}. Follow the note. "
                "Choose the single best legal move from the criteria keys (UCI)."
            )
        questions = {
            "move": {
                "type": "choice",
                "instructions": instructions,
                "criteria": criteria,
            }
        }
        payload = self._systemone(state=state, questions=questions)
        answers = payload.get("answers") or {}
        answer = answers.get("move") or {}
        if not isinstance(answer, dict):
            answer = {}
        return pick_choice(answer, legal)

    def choose_placement(
        self, *, board_text: str, board_png: Optional[bytes] = None
    ) -> Dict[str, str]:
        """Ask Jev to label each square from board.txt (text-grid identify; no vision)."""
        del board_png
        piece_criteria = {
            "empty": "No piece on this square (dot in the grid)",
            "wP": "White pawn (P)",
            "wN": "White knight (N)",
            "wB": "White bishop (B)",
            "wR": "White rook (R)",
            "wQ": "White queen (Q)",
            "wK": "White king (K)",
            "bP": "Black pawn (p)",
            "bN": "Black knight (n)",
            "bB": "Black bishop (b)",
            "bR": "Black rook (r)",
            "bQ": "Black queen (q)",
            "bK": "Black king (k)",
        }
        state = {
            "task": "chess_board_identify",
            "board_text": board_text,
            "legend": (
                "Grid rows are ranks; header letters are files. "
                "White pieces are uppercase, black are lowercase, '.' is empty. "
                "Square names are absolute (a1 is always a1)."
            ),
        }
        pieces: Dict[str, str] = {}
        for rank in "87654321":
            questions: Dict[str, Any] = {}
            for file in "abcdefgh":
                sq = f"{file}{rank}"
                questions[sq] = {
                    "type": "choice",
                    "instructions": (
                        f"What occupies square {sq}? Read board_text carefully. "
                        "Pick empty if the cell is a dot."
                    ),
                    "criteria": piece_criteria,
                }
            payload = self._systemone(state=state, questions=questions)
            answers = payload.get("answers") or {}
            for sq, ans in answers.items():
                if not isinstance(ans, dict):
                    continue
                choice = str(ans.get("choice") or "").strip()
                if choice and choice != "empty":
                    pieces[sq] = choice
        return pieces

    def probe(self, *, board_text: str, board_png: Optional[bytes] = None) -> None:
        del board_png
        self._systemone(
            state={"ping": "runner probe", "board_preview": board_text[:200]},
            questions={
                "ok": {
                    "type": "noul",
                    "instructions": "Is this a chess board description?",
                }
            },
        )