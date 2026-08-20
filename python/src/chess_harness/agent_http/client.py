"""Headless /api/v1 play client for AvE, puzzle, and identify loops."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from ..models import OBSERVATION_TEXT, normalize_observation
from .client_identify import IdentifyHttpMixin
from .client_puzzles import PuzzleHttpMixin
from .queue import QueueEntry, default_queue_path, enqueue, load_queue, reconcile_queue, save_queue
from .transport import (
    DEFAULT_USER_AGENT,
    TransportFn,
    decode_json,
    request_with_retries,
    urllib_transport,
)

__all__ = ["AgentHttpClient", "DEFAULT_USER_AGENT"]


class AgentHttpError(RuntimeError):
    def __init__(self, status: int, message: str, payload: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.status = status
        self.payload = payload or {}


class AgentHttpClient(PuzzleHttpMixin, IdentifyHttpMixin):
    """Minimal durable client for POST /games and puzzle/identify play loops."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        model_id: str,
        user_agent: str = DEFAULT_USER_AGENT,
        transport: Optional[TransportFn] = None,
        queue_path: Optional[Path] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model_id = model_id
        self.user_agent = user_agent
        self._transport = transport or urllib_transport()
        self.queue_path = queue_path or default_queue_path()

    def _headers(self, *, accept: str = "application/json") -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "User-Agent": self.user_agent,
            "Accept": accept,
        }

    def _url(self, path: str) -> str:
        if not path.startswith("/"):
            path = "/" + path
        return f"{self.base_url}{path}"

    def _request(
        self,
        method: str,
        path: str,
        *,
        accept: str = "application/json",
        json_body: Optional[Dict[str, Any]] = None,
        raw: bool = False,
    ) -> Any:
        body = None
        headers = self._headers(accept=accept)
        if json_body is not None:
            import json

            body = json.dumps(json_body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        status, _resp_headers, content = request_with_retries(
            self._transport,
            method,
            self._url(path),
            headers,
            body,
        )
        if raw:
            if status >= 400:
                raise AgentHttpError(status, content.decode("utf-8", errors="replace"))
            return content
        payload = decode_json(content) if content else {}
        if status >= 400:
            message = str(payload.get("error") or content.decode("utf-8", errors="replace"))
            raise AgentHttpError(status, message, payload)
        return payload

    def list_games(self, *, include_finished: bool = False) -> Dict[str, Any]:
        query = "?include_finished=1" if include_finished else ""
        return self._request("GET", f"/api/v1/games{query}")

    def create_game(
        self,
        *,
        opponent: Optional[str] = None,
        agent_color: Optional[str] = None,
        persist: bool = True,
    ) -> Dict[str, Any]:
        body: Dict[str, Any] = {}
        if opponent:
            body["opponent"] = opponent
        if agent_color:
            body["agent_color"] = agent_color
        payload = self._request("POST", "/api/v1/games", json_body=body)
        game_id = str(payload.get("game_id") or "")
        if persist and game_id:
            enqueue(game_id, self.model_id, path=self.queue_path)
        return payload

    def status(self, game_id: str) -> Dict[str, Any]:
        return self._request("GET", f"/api/v1/games/{game_id}/status")

    def board_png(self, game_id: str) -> bytes:
        return self._request(
            "GET",
            f"/api/v1/games/{game_id}/board",
            accept="image/png",
            raw=True,
        )

    def board_text(self, game_id: str) -> str:
        content = self._request(
            "GET",
            f"/api/v1/games/{game_id}/board.txt",
            accept="text/plain",
            raw=True,
        )
        return content.decode("utf-8")

    def fetch_observation(self, game_id: str, observation: str) -> Dict[str, Any]:
        mode = normalize_observation(observation)
        out: Dict[str, Any] = {"board_text": self.board_text(game_id)}
        if mode != OBSERVATION_TEXT:
            out["board_png"] = self.board_png(game_id)
        return out

    def move(self, game_id: str, uci: str) -> Dict[str, Any]:
        uci = (uci or "").strip()
        return self._request("POST", f"/api/v1/games/{game_id}/move/{uci}")

    def resign(self, game_id: str) -> Dict[str, Any]:
        return self._request("POST", f"/api/v1/games/{game_id}/resign")

    def pgn(self, game_id: str) -> Dict[str, Any]:
        return self._request("GET", f"/api/v1/games/{game_id}/pgn")

    def load_queue(self) -> List[QueueEntry]:
        return load_queue(self.queue_path)

    def save_queue(self, entries: List[QueueEntry]) -> None:
        save_queue(entries, self.queue_path)

    def reconcile_queue(self) -> List[QueueEntry]:
        server = self.list_games().get("games") or []
        entries = reconcile_queue(self.load_queue(), server)
        self.save_queue(entries)
        return entries

    def resume_entries(self) -> List[QueueEntry]:
        """Reconcile persisted queue against live in-progress games."""
        return self.reconcile_queue()
