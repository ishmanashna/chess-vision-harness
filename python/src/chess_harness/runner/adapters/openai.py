"""OpenAI-compatible chat adapter for move selection."""

from __future__ import annotations

import json
import os
import re
from typing import Any, Callable, Dict, List, Optional, Tuple

from ...agent_http.transport import DEFAULT_USER_AGENT, decode_json, request_with_retries
from ...models import OBSERVATION_TEXT, normalize_observation
from .images import png_to_jpeg_data_url

TransportFn = Callable[[str, str, Dict[str, str], Optional[bytes]], Tuple[int, Dict[str, str], bytes]]

_UCI_RE = re.compile(r"\b([a-h][1-8][a-h][1-8][qrbn]?)\b", re.IGNORECASE)
_MAX_IDLE_SLEEP_SEC = 120.0


def parse_move_from_text(text: str) -> str:
    """Extract the first UCI-like token from model output."""
    if not text:
        return "invalid"
    match = _UCI_RE.search(text.strip())
    if match:
        return match.group(1).lower()
    token = text.strip().split()[0]
    return token if token else "invalid"


def parse_placement_from_text(text: str) -> Dict[str, str]:
    """Extract a pieces mapping from model JSON output."""
    if not text:
        return {}
    raw = text.strip()
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        raw = raw[start : end + 1]
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if not isinstance(payload, dict):
        return {}
    pieces = payload.get("pieces", payload)
    if not isinstance(pieces, dict):
        return {}
    out: Dict[str, str] = {}
    for square, code in pieces.items():
        if isinstance(square, str) and isinstance(code, str):
            out[square.strip()] = code.strip()
    return out


class OpenAIAdapter:
    provider = "openai"

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        env_key: str,
        observation: str,
        transport: TransportFn,
        jpeg_max_side: Optional[int] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.env_key = env_key
        self.observation = normalize_observation(observation)
        self._transport = transport
        self.jpeg_max_side = jpeg_max_side

    def _api_key(self) -> str:
        key = os.getenv(self.env_key, "").strip()
        if not key:
            raise RuntimeError(f"missing provider env {self.env_key}")
        return key

    def _chat(self, messages: List[Dict[str, Any]]) -> str:
        url = f"{self.base_url}/chat/completions"
        body = json.dumps(
            {
                "model": self.model,
                "messages": messages,
                "temperature": 0.2,
                "max_tokens": 32,
            }
        ).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {self._api_key()}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": DEFAULT_USER_AGENT,
        }
        status, resp_headers, content = request_with_retries(
            self._transport, "POST", url, headers, body
        )
        if status == 429:
            retry_after = resp_headers.get("Retry-After") or resp_headers.get("retry-after")
            if retry_after:
                try:
                    delay = min(float(retry_after), _MAX_IDLE_SLEEP_SEC)
                except ValueError:
                    delay = 0.0
                if delay > 0:
                    import time

                    time.sleep(delay)
            raise RuntimeError("provider rate limited")
        payload = decode_json(content) if content else {}
        if status >= 400:
            message = str(payload.get("error", {}).get("message") or payload.get("error") or content)
            raise RuntimeError(message)
        choices = payload.get("choices") or []
        if not choices:
            raise RuntimeError("empty provider response")
        message = choices[0].get("message") or {}
        return str(message.get("content") or "")

    def _messages(self, *, board_text: str, board_png: Optional[bytes]) -> List[Dict[str, Any]]:
        system = (
            "You are playing chess. Reply with exactly one move in UCI format "
            "(e.g. e2e4). No explanation."
        )
        if self.observation == OBSERVATION_TEXT or board_png is None:
            user_content: Any = f"Position (board.txt):\n{board_text}\n\nYour move (UCI only):"
            return [{"role": "system", "content": system}, {"role": "user", "content": user_content}]
        data_url = png_to_jpeg_data_url(board_png, max_side=self.jpeg_max_side)
        user_content = [
            {"type": "text", "text": f"Position (board.txt):\n{board_text}\n\nYour move (UCI only):"},
            {"type": "image_url", "image_url": {"url": data_url}},
        ]
        return [{"role": "system", "content": system}, {"role": "user", "content": user_content}]

    def choose_move(self, *, board_text: str, board_png: Optional[bytes] = None) -> str:
        text = self._chat(self._messages(board_text=board_text, board_png=board_png))
        return parse_move_from_text(text)

    def _placement_messages(
        self, *, board_text: str, board_png: Optional[bytes]
    ) -> List[Dict[str, Any]]:
        system = (
            "You identify chess piece placement. Reply with JSON only: "
            '{"pieces": {"e4": "wP", "e8": "bK", ...}} using wP/wK/bQ codes '
            "for occupied squares only."
        )
        if self.observation == OBSERVATION_TEXT or board_png is None:
            user_content: Any = (
                f"Position (board.txt):\n{board_text}\n\n"
                "Reply with JSON pieces mapping only:"
            )
            return [{"role": "system", "content": system}, {"role": "user", "content": user_content}]
        data_url = png_to_jpeg_data_url(board_png, max_side=self.jpeg_max_side)
        user_content = [
            {
                "type": "text",
                "text": (
                    f"Position (board.txt):\n{board_text}\n\n"
                    "Reply with JSON pieces mapping only:"
                ),
            },
            {"type": "image_url", "image_url": {"url": data_url}},
        ]
        return [{"role": "system", "content": system}, {"role": "user", "content": user_content}]

    def choose_placement(
        self, *, board_text: str, board_png: Optional[bytes] = None
    ) -> Dict[str, str]:
        text = self._chat(self._placement_messages(board_text=board_text, board_png=board_png))
        return parse_placement_from_text(text)

    def probe(self, *, board_text: str, board_png: Optional[bytes] = None) -> None:
        self._chat(self._messages(board_text=board_text, board_png=board_png))
