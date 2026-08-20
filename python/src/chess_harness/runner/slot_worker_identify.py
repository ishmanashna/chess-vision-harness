"""Play one identify attempt for a configured slot."""

from __future__ import annotations

from typing import Any, Dict

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
        client.identify_abandon(attempt_id)
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


def play_identify_attempt(
    client: AgentHttpClient,
    adapter: MoveAdapter,
    slot: SlotConfig,
    quota: QuotaTracker,
    logger: RunnerLog,
    *,
    max_answer_tries: int = 5,
) -> Dict[str, Any]:
    """Run one identify attempt: start, answer once, review after end."""
    if not quota.allow():
        return {"ok": False, "reason": "quota"}

    started = client.start_identify(
        rating_min=slot.identify_rating_min,
        rating_max=slot.identify_rating_max,
    )
    attempt_id = str(started.get("attempt_id") or "")
    obs_mode = slot.observation
    logger.write(
        "identify_started",
        game_id=attempt_id,
        model=slot.inscribed_id,
        provider=slot.provider,
    )

    observation_payload = client.fetch_identify_observation(attempt_id, obs_mode)
    board_text = observation_payload["board_text"]
    board_png = observation_payload.get("board_png")
    if obs_mode == OBSERVATION_TEXT:
        board_png = None

    status = "active"
    result = None
    tries = 0

    while status == "active" and tries < max_answer_tries:
        if not quota.allow():
            reason = quota.stop("rpm_or_rpd")
            _abandon_attempt(client, attempt_id, logger, slot, event="identify_abandon_quota")
            logger.write(
                "slot_stopped",
                game_id=attempt_id,
                model=slot.inscribed_id,
                provider=slot.provider,
                quota=reason,
            )
            return {"ok": False, "reason": reason, "attempt_id": attempt_id}

        try:
            pieces = adapter.choose_placement(board_text=board_text, board_png=board_png)
        except Exception as exc:
            logger.write(
                "provider_error",
                game_id=attempt_id,
                model=slot.inscribed_id,
                provider=slot.provider,
                error=str(exc),
            )
            _abandon_attempt(client, attempt_id, logger, slot, event="identify_abandon_error")
            return {"ok": False, "reason": "provider_error", "attempt_id": attempt_id}

        quota.record()
        tries += 1

        try:
            answered = client.identify_answer(attempt_id, pieces)
        except AgentHttpError as exc:
            if exc.status in {400, 422}:
                continue
            logger.write(
                "identify_answer_rejected",
                game_id=attempt_id,
                model=slot.inscribed_id,
                provider=slot.provider,
                error=str(exc),
            )
            _abandon_attempt(client, attempt_id, logger, slot, event="identify_abandon_error")
            return {"ok": False, "reason": "answer_error", "attempt_id": attempt_id}

        status = str(answered.get("status") or "active")
        result = answered.get("result")

    if status == "active":
        _abandon_attempt(client, attempt_id, logger, slot, event="identify_abandon_timeout")
        return {"ok": False, "reason": "timeout", "attempt_id": attempt_id}

    review = client.identify_review(attempt_id)
    logger.write(
        "identify_finished",
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
