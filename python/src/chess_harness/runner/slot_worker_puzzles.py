"""Play one puzzle attempt for a configured slot."""

from __future__ import annotations

from typing import Any, Dict, Optional

from ..agent_http import AgentHttpClient, AgentHttpError
from ..models import OBSERVATION_TEXT
from .adapters.base import MoveAdapter
from .config import SlotConfig
from .log import RunnerLog
from .quota import QuotaTracker


def _abandon_attempt(
    client: AgentHttpClient,
    attempt_id: str,
    logger: RunnerLog,
    slot: SlotConfig,
    *,
    event: str,
) -> None:
    try:
        client.puzzle_abandon(attempt_id)
        logger.write(
            event,
            game_id=attempt_id,
            model=slot.inscribed_id,
            provider=slot.provider,
            quota="exhausted",
        )
    except AgentHttpError as exc:
        logger.write(
            "abandon_failed",
            game_id=attempt_id,
            model=slot.inscribed_id,
            provider=slot.provider,
            error=str(exc),
        )


def play_puzzle_attempt(
    client: AgentHttpClient,
    adapter: MoveAdapter,
    slot: SlotConfig,
    quota: QuotaTracker,
    logger: RunnerLog,
    *,
    max_moves: int = 40,
) -> Dict[str, Any]:
    """Run one puzzle attempt: start, moves until finished, review after end."""
    if not quota.allow():
        return {"ok": False, "reason": "quota"}

    started = client.start_puzzle(
        rating_min=slot.puzzle_rating_min,
        rating_max=slot.puzzle_rating_max,
        theme=slot.puzzle_theme,
    )
    attempt_id = str(started.get("attempt_id") or "")
    obs_mode = slot.observation
    logger.write(
        "puzzle_started",
        game_id=attempt_id,
        model=slot.inscribed_id,
        provider=slot.provider,
        extra={"puzzle_id": started.get("puzzle_id")},
    )

    status = "active"
    result = None
    moves_played = 0

    while status == "active" and moves_played < max_moves:
        if not quota.allow():
            reason = quota.stop("rpm_or_rpd")
            _abandon_attempt(client, attempt_id, logger, slot, event="puzzle_abandon_quota")
            logger.write(
                "slot_stopped",
                game_id=attempt_id,
                model=slot.inscribed_id,
                provider=slot.provider,
                quota=reason,
            )
            return {"ok": False, "reason": reason, "attempt_id": attempt_id}

        observation_payload = client.fetch_puzzle_observation(attempt_id, obs_mode)
        board_text = observation_payload["board_text"]
        board_png = observation_payload.get("board_png")
        if obs_mode == OBSERVATION_TEXT:
            board_png = None

        try:
            move = adapter.choose_move(board_text=board_text, board_png=board_png)
        except Exception as exc:
            logger.write(
                "provider_error",
                game_id=attempt_id,
                model=slot.inscribed_id,
                provider=slot.provider,
                error=str(exc),
            )
            _abandon_attempt(client, attempt_id, logger, slot, event="puzzle_abandon_error")
            return {"ok": False, "reason": "provider_error", "attempt_id": attempt_id}

        quota.record()

        try:
            moved = client.puzzle_move(attempt_id, move)
        except AgentHttpError as exc:
            logger.write(
                "puzzle_move_rejected",
                game_id=attempt_id,
                model=slot.inscribed_id,
                provider=slot.provider,
                error=str(exc),
                extra={"move": move},
            )
            _abandon_attempt(client, attempt_id, logger, slot, event="puzzle_abandon_error")
            return {"ok": False, "reason": "move_error", "attempt_id": attempt_id, "move": move}

        status = str(moved.get("status") or "active")
        result = moved.get("result")
        moves_played = int(moved.get("moves_played") or moves_played + 1)

    if status == "active":
        _abandon_attempt(client, attempt_id, logger, slot, event="puzzle_abandon_timeout")
        return {"ok": False, "reason": "timeout", "attempt_id": attempt_id}

    review = client.puzzle_review(attempt_id)
    logger.write(
        "puzzle_finished",
        game_id=attempt_id,
        model=slot.inscribed_id,
        provider=slot.provider,
        extra={"result": result, "review_result": review.get("result")},
    )
    return {
        "ok": True,
        "attempt_id": attempt_id,
        "result": result,
        "status": status,
        "review": review,
    }
