"""Parent orchestration routes: draft -> approve -> launch scoped child games.

Drafting never starts a game. An explicit approval (parent API key or
operator) is required before launch, and launch is the only step that calls
GameService. Child-side scoped credentials are minted BEFORE game creation so
their fingerprints bind to game sides at creation time.
"""

from __future__ import annotations

import os
import secrets
from typing import Any, Callable, Dict, Optional

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .activity_audit import record_activity
from .agent_brief import public_base_url, render_agent_brief, render_agent_brief_avaa
from .api_limits import ApiLimitEnforcer, AuthContext, client_ip, key_fingerprint
from .api_keys import ApiKeyStore
from .calibration_auth import host_is_loopback
from .child_credentials import ChildCredentialStore
from .game_service import GameService
from .game_types import GAME_TYPE_AGENT_VS_AGENT
from .models import ModelRegistry
from .orchestrations import (
    ORCH_CHILD_VS_CHILD,
    ORCH_CHILD_VS_ENGINE,
    ORCH_PARENT_VS_CHILD,
    ORCH_SELF_VS_ENGINE,
    OrchestrationError,
    OrchestrationStore,
)
from .scope_auth import reject_scoped_auth

__all__ = ["register_orchestration_routes"]

_ORCH_SECRET_ENV = "CHESS_HARNESS_ORCHESTRATION_SECRET"
_ORCH_SECRET_HEADER = "X-Chess-Harness-Orchestration-Secret"

_AVA_MODES = (ORCH_PARENT_VS_CHILD, ORCH_CHILD_VS_CHILD)


class OrchestrationSideBody(BaseModel):
    kind: str = Field(..., min_length=1, max_length=16)
    model_id: Optional[str] = Field(None, min_length=1, max_length=64)
    role: Optional[str] = Field(None, min_length=1, max_length=16)


class CreateOrchestrationBody(BaseModel):
    mode: str = Field(..., min_length=1, max_length=32)
    white: OrchestrationSideBody
    black: OrchestrationSideBody
    engine_opponent: Optional[str] = Field(None, min_length=1, max_length=64)


def _side_spec(body_side: OrchestrationSideBody) -> Dict[str, Any]:
    spec: Dict[str, Any] = {"kind": body_side.kind.strip()}
    if body_side.model_id:
        spec["model_id"] = body_side.model_id.strip()
    if body_side.role:
        spec["role"] = body_side.role.strip()
    return spec


def _operator_allowed(request: Request, err: Callable[[int, str], JSONResponse]):
    if host_is_loopback(request):
        return None
    configured = os.environ.get(_ORCH_SECRET_ENV, "").strip()
    provided = request.headers.get(_ORCH_SECRET_HEADER, "").strip()
    if configured and provided and secrets.compare_digest(configured, provided):
        return None
    return err(
        403,
        "Orchestration approval is only available to the parent or on localhost "
        "with the orchestration secret",
    )


def _parent_auth(
    record: Dict[str, Any],
    raw_authorization: Optional[str],
) -> Optional[AuthContext]:
    """Resolve the AuthContext only when the bearer belongs to the parent model."""
    if not raw_authorization or not raw_authorization.lower().startswith("bearer "):
        return None
    raw = raw_authorization[7:].strip()
    model_id = ApiKeyStore().verify(raw)
    if not model_id or model_id != record.get("parent_model_id"):
        return None
    return AuthContext(model_id=model_id, key_fingerprint=key_fingerprint(raw))


def _authorized(
    record: Dict[str, Any],
    request: Request,
    raw_authorization: Optional[str],
    err: Callable[[int, str], JSONResponse],
) -> Optional[JSONResponse]:
    """Parent's own API key approves; otherwise the operator gate applies."""
    if _parent_auth(record, raw_authorization) is not None:
        return None
    return _operator_allowed(request, err)


def _require_inscribed(model_id: str, err: Callable[[int, str], JSONResponse]):
    registry = ModelRegistry()
    if not registry.is_inscribed(model_id):
        return err(400, f"Model '{model_id}' is not inscribed")
    return None


def _side_brief(
    state: Dict[str, Any],
    game_id: str,
    raw_key: str,
    side: str,
    is_ava: bool,
) -> str:
    from .models import ModelRegistry, normalize_observation

    registry = ModelRegistry()
    if not is_ava:
        model_id = state.get("model_name") or ""
        obs = normalize_observation(state.get("observation"))
        if not state.get("observation") and model_id:
            obs = registry.observation_for(str(model_id))
        return render_agent_brief(
            public_base_url(), game_id, raw_key, observation=obs
        )
    opponent = (
        state.get("black_display_name")
        if side == "WHITE"
        else state.get("white_display_name")
    ) or "Opponent"
    obs_key = "white_observation" if side == "WHITE" else "black_observation"
    return render_agent_brief_avaa(
        public_base_url(),
        game_id,
        raw_key,
        side.lower(),
        str(opponent),
        observation=normalize_observation(state.get(obs_key)),
    )


def _task_envelope(
    state: Dict[str, Any],
    game_id: str,
    raw_key: str,
    side: str,
    is_ava: bool,
    spec: Dict[str, Any],
) -> Dict[str, Any]:
    """Structured envelope: role, game, API base, credential, opponent, brief."""
    return {
        "role": spec.get("role"),
        "side": side.upper(),
        "game_id": game_id,
        "api_base": public_base_url(),
        "api_key": raw_key,
        "opponent": (
            state.get("black_display_name")
            if side == "WHITE"
            else state.get("white_display_name")
        )
        if is_ava
        else "Engine",
        "brief": _side_brief(state, game_id, raw_key, side, is_ava),
    }


def _live_game_state(
    svc: GameService, game_id: Optional[str]
) -> Optional[Dict[str, Any]]:
    """Parent-visible live game state for an orchestrated game (no secrets)."""
    if not game_id:
        return None
    state = svc.game_manager.load_state(game_id) or {}
    if not state:
        return None
    moves = state.get("moves") or []
    return {
        "game_id": game_id,
        "status": state.get("status"),
        "result": state.get("result"),
        "game_type": state.get("game_type"),
        "move_count": len(moves),
        "turn": "WHITE" if len(moves) % 2 == 0 else "BLACK",
        "white_joined": bool(state.get("white_joined")),
        "black_joined": bool(state.get("black_joined")),
        "both_sides_joined": bool(state.get("white_joined")) and bool(
            state.get("black_joined")
        ),
        "white_display_name": state.get("white_display_name"),
        "black_display_name": state.get("black_display_name"),
    }


def _status_payload(
    record: Dict[str, Any], svc: GameService
) -> Dict[str, Any]:
    """Parent status: approval, tasks, brief availability, join/turn/finish.

    Child credential keys are never included; briefs are only the availability
    flags, not the rendered prompts (those were handed over once at launch).
    """
    payload: Dict[str, Any] = {
        "orchestration_id": record["orchestration_id"],
        "parent_model_id": record.get("parent_model_id"),
        "mode": record.get("mode"),
        "approval_state": record.get("approval_state"),
        "engine_opponent": record.get("engine_opponent"),
        "created_at": record.get("created_at"),
        "approved_at": record.get("approved_at"),
        "launched_at": record.get("launched_at"),
        "game_id": record.get("game_id"),
        "game_type": record.get("game_type"),
        "error": record.get("error"),
        "result": record.get("result"),
        "participants": {},
    }
    for color, spec in (record.get("participants") or {}).items():
        entry: Dict[str, Any] = {
            "side": color.upper(),
            "kind": spec.get("kind"),
            "role": spec.get("role"),
            "model_id": spec.get("model_id") if spec.get("kind") == "model" else None,
            "task_id": spec.get("task_id"),
            "status": spec.get("status"),
            "brief_available": bool(spec.get("status") in ("issued", "ready", "joined")),
        }
        if spec.get("kind") == "engine":
            entry["engine_opponent"] = record.get("engine_opponent")
        payload["participants"][color] = entry
    payload["game"] = _live_game_state(svc, record.get("game_id"))
    return payload


def register_orchestration_routes(
    router: APIRouter,
    *,
    svc_fn: Callable[[], GameService],
    limits: ApiLimitEnforcer,
    err: Callable[[int, str], JSONResponse],
    new_game_id: Callable[[], str],
    auth_context: Callable[..., AuthContext],
    store_fn: Optional[Callable[[], OrchestrationStore]] = None,
    creds_fn: Optional[Callable[[], ChildCredentialStore]] = None,
) -> None:
    orch_store = store_fn or OrchestrationStore
    cred_store = creds_fn or ChildCredentialStore

    @router.post("/orchestrations")
    async def create_orchestration(
        body: CreateOrchestrationBody,
        auth: AuthContext = Depends(auth_context),
    ):
        denied = reject_scoped_auth(auth, err)
        if denied:
            return denied
        if not ModelRegistry().is_inscribed(auth.model_id):
            return err(400, f"Parent model '{auth.model_id}' is not inscribed")
        for side_body in (body.white, body.black):
            if side_body.kind == "model" and side_body.model_id:
                model_denied = _require_inscribed(side_body.model_id, err)
                if model_denied:
                    return model_denied
        try:
            record = orch_store().create(
                auth.model_id,
                body.mode.strip(),
                _side_spec(body.white),
                _side_spec(body.black),
                engine_opponent=body.engine_opponent,
            )
        except OrchestrationError as exc:
            return err(exc.status, exc.message)
        return {
            "ok": True,
            "orchestration_id": record["orchestration_id"],
            "approval_state": record["approval_state"],
            "mode": record["mode"],
        }

    @router.post("/orchestrations/{orchestration_id}/approve")
    async def approve_orchestration(
        orchestration_id: str,
        request: Request,
        authorization: Optional[str] = Header(None),
    ):
        record = orch_store().get(orchestration_id)
        if record is None:
            return err(404, "Orchestration not found")
        denied = _authorized(record, request, authorization, err)
        if denied:
            return denied
        try:
            record = orch_store().approve(orchestration_id)
        except OrchestrationError as exc:
            return err(exc.status, exc.message)
        return {
            "ok": True,
            "orchestration_id": record["orchestration_id"],
            "approval_state": record["approval_state"],
            "approved_at": record.get("approved_at"),
        }

    @router.post("/orchestrations/{orchestration_id}/launch")
    async def launch_orchestration(
        orchestration_id: str,
        request: Request,
        authorization: Optional[str] = Header(None),
    ):
        record = orch_store().get(orchestration_id)
        if record is None:
            return err(404, "Orchestration not found")
        denied = _authorized(record, request, authorization, err)
        if denied:
            return denied
        if record.get("approval_state") != "approved":
            return err(409, "Orchestration must be approved before launch")

        auth = _parent_auth(record, authorization) or AuthContext(
            model_id=record.get("parent_model_id") or "operator",
            key_fingerprint=key_fingerprint(authorization or "operator"),
        )

        engine_limit = limits.check_create_game(svc_fn(), auth)
        if engine_limit:
            return engine_limit

        mode = record["mode"]
        participants = record["participants"]
        is_ava = mode in _AVA_MODES
        game_id = new_game_id()

        raw_key = ""
        if authorization and authorization.lower().startswith("bearer "):
            raw_key = authorization[7:].strip()

        minted: Dict[str, str] = {}
        try:
            if is_ava:
                side_keys: Dict[str, str] = {}
                for side in ("white", "black"):
                    spec = participants[side]
                    if spec["kind"] != "model":
                        raise OrchestrationError(
                            400, f"{side} side must be a model for {mode}"
                        )
                    if spec["role"] == "child":
                        minted_result = cred_store().mint(
                            game_id, side.upper(), spec["model_id"]
                        )
                        minted[side.upper()] = minted_result["key"]
                        side_keys[side.upper()] = minted[side.upper()]
                    else:
                        if not raw_key:
                            raise OrchestrationError(
                                401, "Parent side requires an Authorization key"
                            )
                        side_keys[side.upper()] = raw_key
                result = svc_fn().new_agent_vs_agent_game(
                    game_id,
                    participants["white"]["model_id"],
                    participants["black"]["model_id"],
                    white_key_fp=key_fingerprint(side_keys["WHITE"]),
                    black_key_fp=key_fingerprint(side_keys["BLACK"]),
                )
            else:
                model_side = next(
                    (
                        (side, spec)
                        for side, spec in participants.items()
                        if spec["kind"] == "model"
                    ),
                    None,
                )
                if model_side is None:
                    raise OrchestrationError(400, f"{mode} needs a model side")
                side, spec = model_side
                color = "white" if side == "white" else "black"
                if spec["role"] == "child":
                    minted_result = cred_store().mint(
                        game_id, side.upper(), spec["model_id"]
                    )
                    minted[side.upper()] = minted_result["key"]
                result = svc_fn().new_game(
                    game_id,
                    color,
                    model_name=spec["model_id"],
                    opponent_id=record.get("engine_opponent"),
                )
        except OrchestrationError as exc:
            if minted:
                cred_store().revoke_game(game_id)
            orch_store().fail(orchestration_id, exc.message)
            return err(exc.status, exc.message)

        if not result.get("ok"):
            cred_store().revoke_game(game_id)
            message = result.get("error", "Failed to create game")
            orch_store().fail(orchestration_id, message)
            return err(400, message)

        limits.record_create_game(auth)
        resolved_id = str(result.get("game_id") or game_id)
        orch_store().launch(orchestration_id, resolved_id, result.get("game_type", ""))

        try:
            record_activity(
                "create_orchestration",
                model_id=auth.model_id,
                game_id=resolved_id,
                client_ip=client_ip(request),
                user_agent=request.headers.get("user-agent", ""),
            )
        except Exception:
            pass

        state = svc_fn().game_manager.load_state(resolved_id) or {}
        payload: Dict[str, Any] = {
            "ok": True,
            "orchestration_id": orchestration_id,
            "approval_state": "launched",
            "game_id": resolved_id,
            "game_type": result.get("game_type") or (
                GAME_TYPE_AGENT_VS_AGENT if is_ava else None
            ),
            "board_url": f"/api/v1/games/{resolved_id}/board",
        }
        for side in ("white", "black"):
            spec = participants[side]
            entry: Dict[str, Any] = {
                "side": side.upper(),
                "kind": spec["kind"],
                "role": spec["role"],
                "task_id": spec["task_id"],
            }
            if spec["kind"] == "model":
                entry["model_id"] = spec["model_id"]
                side_key = minted.get(side.upper()) or raw_key
                if side_key:
                    entry["api_key"] = side_key
                    entry["agent_brief"] = _side_brief(
                        state, resolved_id, side_key, side.upper(), is_ava
                    )
                    entry["envelope"] = _task_envelope(
                        state, resolved_id, side_key, side.upper(), is_ava, spec
                    )
            payload[side] = entry
        return payload

    @router.get("/orchestrations/{orchestration_id}")
    async def orchestration_status(
        orchestration_id: str,
        auth: AuthContext = Depends(auth_context),
    ):
        record = orch_store().get(orchestration_id)
        if record is None:
            return err(404, "Orchestration not found")
        if auth.scoped is not None and auth.model_id != record.get("parent_model_id"):
            return err(403, "Scoped credentials cannot read orchestration status")
        return {"ok": True, **_status_payload(record, svc_fn())}

    @router.get("/orchestrations")
    async def list_orchestrations(auth: AuthContext = Depends(auth_context)):
        denied = reject_scoped_auth(auth, err)
        if denied:
            return denied
        return {
            "ok": True,
            "orchestrations": orch_store().list_by_parent(auth.model_id),
        }
