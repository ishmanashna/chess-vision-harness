"""Board-identification attempt HTTP helpers for AgentHttpClient."""

from __future__ import annotations

from typing import Any, Dict, Optional
from urllib.parse import urlencode

from ..models import OBSERVATION_TEXT, normalize_observation


class IdentifyHttpMixin:
    """Mixin: POST /api/v1/identify/* play surface."""

    def start_identify(
        self,
        *,
        rating_min: Optional[int] = None,
        rating_max: Optional[int] = None,
    ) -> Dict[str, Any]:
        params: Dict[str, str] = {}
        if rating_min is not None:
            params["rating_min"] = str(rating_min)
        if rating_max is not None:
            params["rating_max"] = str(rating_max)
        query = f"?{urlencode(params)}" if params else ""
        return self._request("POST", f"/api/v1/identify/start{query}")

    def identify_board_png(self, attempt_id: str) -> bytes:
        return self._request(
            "GET",
            f"/api/v1/identify/{attempt_id}/board",
            accept="image/png",
            raw=True,
        )

    def identify_board_text(self, attempt_id: str) -> str:
        content = self._request(
            "GET",
            f"/api/v1/identify/{attempt_id}/board.txt",
            accept="text/plain",
            raw=True,
        )
        return content.decode("utf-8")

    def fetch_identify_observation(self, attempt_id: str, observation: str) -> Dict[str, Any]:
        mode = normalize_observation(observation)
        out: Dict[str, Any] = {"board_text": self.identify_board_text(attempt_id)}
        if mode != OBSERVATION_TEXT:
            out["board_png"] = self.identify_board_png(attempt_id)
        return out

    def identify_answer(self, attempt_id: str, pieces: Dict[str, str]) -> Dict[str, Any]:
        return self._request(
            "POST",
            f"/api/v1/identify/{attempt_id}/answer",
            json_body={"pieces": pieces},
        )

    def identify_review(self, attempt_id: str) -> Dict[str, Any]:
        return self._request("GET", f"/api/v1/identify/{attempt_id}/review")

    def identify_abandon(self, attempt_id: str) -> Dict[str, Any]:
        return self._request("POST", f"/api/v1/identify/{attempt_id}/abandon")
