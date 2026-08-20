"""Puzzle attempt HTTP helpers for AgentHttpClient."""

from __future__ import annotations

from typing import Any, Dict, Optional
from urllib.parse import urlencode

from ..models import OBSERVATION_TEXT, normalize_observation


class PuzzleHttpMixin:
    """Mixin: POST /api/v1/puzzles/* play surface."""

    def start_puzzle(
        self,
        *,
        rating_min: Optional[int] = None,
        rating_max: Optional[int] = None,
        theme: Optional[str] = None,
    ) -> Dict[str, Any]:
        params: Dict[str, str] = {}
        if rating_min is not None:
            params["rating_min"] = str(rating_min)
        if rating_max is not None:
            params["rating_max"] = str(rating_max)
        if theme:
            params["theme"] = theme
        query = f"?{urlencode(params)}" if params else ""
        return self._request("POST", f"/api/v1/puzzles/start{query}")

    def puzzle_board_png(self, attempt_id: str) -> bytes:
        return self._request(
            "GET",
            f"/api/v1/puzzles/{attempt_id}/board",
            accept="image/png",
            raw=True,
        )

    def puzzle_board_text(self, attempt_id: str) -> str:
        content = self._request(
            "GET",
            f"/api/v1/puzzles/{attempt_id}/board.txt",
            accept="text/plain",
            raw=True,
        )
        return content.decode("utf-8")

    def fetch_puzzle_observation(self, attempt_id: str, observation: str) -> Dict[str, Any]:
        mode = normalize_observation(observation)
        out: Dict[str, Any] = {"board_text": self.puzzle_board_text(attempt_id)}
        if mode != OBSERVATION_TEXT:
            out["board_png"] = self.puzzle_board_png(attempt_id)
        return out

    def puzzle_move(self, attempt_id: str, uci: str) -> Dict[str, Any]:
        uci = (uci or "").strip()
        return self._request("POST", f"/api/v1/puzzles/{attempt_id}/move/{uci}")

    def puzzle_review(self, attempt_id: str) -> Dict[str, Any]:
        return self._request("GET", f"/api/v1/puzzles/{attempt_id}/review")

    def puzzle_abandon(self, attempt_id: str) -> Dict[str, Any]:
        return self._request("POST", f"/api/v1/puzzles/{attempt_id}/abandon")
