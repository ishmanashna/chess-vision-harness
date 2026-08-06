"""Game-scoped participant authentication for orchestrated child agents.

Child credentials bind a single game_id and an enumerated subscope
(status | board | board.txt | move | resign | pgn). Route-level enforcement
asserts the requested action is inside the bound game and the credential's
scopes BEFORE any GameService call. Normal model-scoped API keys fall through
to the existing participant rules unchanged.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from fastapi.responses import JSONResponse

from .api_limits import AuthContext
from .game_service import GameService

__all__ = [
    "reject_scoped_auth",
    "require_scoped_game_participant",
]

# Actions that child scopes may grant. Everything else (create, imagine,
# chat, draw, follow-up) is rejected for scoped credentials.
SCOPED_ACTIONS = ("status", "board", "board.txt", "move", "resign", "pgn")


def reject_scoped_auth(
    auth: AuthContext,
    err: Callable[[int, str], JSONResponse],
    message: str = "Scoped child credentials cannot create games",
) -> Optional[JSONResponse]:
    """Reject a scoped credential outright (creation/registration routes)."""
    if auth.scoped is not None:
        return err(403, message)
    return None


def _scoped_color(
    service: GameService,
    game_id: str,
    auth: AuthContext,
    err: Callable[[int, str], JSONResponse],
) -> JSONResponse | tuple[AuthContext, str]:
    """Resolve the side the scoped credential plays, verifying the binding."""
    from .avaa import is_avaa_state, participant_color
    from .game_types import is_human_vs_agent_state

    cred = auth.scoped or {}
    state = service.game_manager.load_state(game_id)
    if state is None:
        return err(404, f"Game {game_id} not found")
    if state.get("status") != "in_progress":
        return err(403, "Credential expired: game is over")

    model_id = auth.model_id
    expected_side = cred.get("side")
    if is_avaa_state(state):
        color = participant_color(state, model_id, auth.key_fingerprint)
        if color is None or (expected_side and color != expected_side):
            return err(401, "API key does not match this game")
        return auth, color

    if is_human_vs_agent_state(state):
        if model_id != state.get("model_name"):
            return err(401, "API key does not match this game")
        color = state.get("agent_color", "WHITE")
        if expected_side and color != expected_side:
            return err(401, "API key does not match this game")
        return auth, color

    game_model = state.get("model_name")
    if game_model != model_id:
        return err(401, "API key does not match this game")
    color = state.get("agent_color", "WHITE")
    if expected_side and color != expected_side:
        return err(401, "API key does not match this game")
    return auth, color


def require_scoped_game_participant(
    service: GameService,
    game_id: str,
    action: str,
    auth: AuthContext,
    err: Callable[[int, str], JSONResponse],
) -> JSONResponse | tuple[AuthContext, str]:
    """Assert the credential is bound to this game and grants the action."""
    if auth.scoped is None:
        from .avaa_api import require_game_participant

        return require_game_participant(service, game_id, auth, err)

    cred: Dict[str, Any] = auth.scoped or {}
    bound_game = cred.get("game_id")
    if bound_game != game_id:
        return err(403, "Credential is scoped to a different game")
    if action not in cred.get("scopes", []):
        return err(403, f"Credential does not grant '{action}'")
    return _scoped_color(service, game_id, auth, err)
