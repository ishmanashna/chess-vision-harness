"""Play one AvE game for a configured slot."""

from __future__ import annotations

import time
from typing import Any, Dict, Optional

from ..agent_http import AgentHttpClient, AgentHttpError
from ..models import OBSERVATION_TEXT
from .adapters.base import MoveAdapter
from .config import SlotConfig
from .log import RunnerLog
from .quota import QuotaTracker


def _finish_live_game(client: AgentHttpClient, game_id: str, logger: RunnerLog, slot: SlotConfig) -> None:
    try:
        client.resign(game_id)
        logger.write(
            "resign_quota",
            game_id=game_id,
            model=slot.inscribed_id,
            provider=slot.provider,
            quota="exhausted",
        )
    except AgentHttpError as exc:
        logger.write(
            "resign_failed",
            game_id=game_id,
            model=slot.inscribed_id,
            provider=slot.provider,
            error=str(exc),
        )


def play_game(
    client: AgentHttpClient,
    adapter: MoveAdapter,
    slot: SlotConfig,
    quota: QuotaTracker,
    logger: RunnerLog,
    *,
    game_id: Optional[str] = None,
    observation: Optional[str] = None,
    poll_sleep_sec: float = 0.05,
    max_wait_loops: int = 400,
    max_agent_plies: Optional[int] = None,
) -> Dict[str, Any]:
    """Run the AvE loop until the game finishes or the slot quota stops."""
    obs_mode = observation or slot.observation
    if not game_id:
        if not quota.allow():
            return {"ok": False, "reason": "quota"}
        created = client.create_game(
            opponent=slot.opponent,
            agent_color=slot.agent_color,
            persist=True,
        )
        game_id = str(created.get("game_id") or "")
        obs_mode = created.get("observation") or obs_mode
        logger.write(
            "game_created",
            game_id=game_id,
            model=slot.inscribed_id,
            provider=slot.provider,
        )

    loops = 0
    agent_plies = 0
    while loops < max_wait_loops:
        loops += 1
        status = client.status(game_id)
        if status.get("game_over"):
            client.pgn(game_id)
            logger.write(
                "game_finished",
                game_id=game_id,
                model=slot.inscribed_id,
                provider=slot.provider,
                extra={"result": status.get("result")},
            )
            entries = [entry for entry in client.load_queue() if entry.game_id != game_id]
            client.save_queue(entries)
            return {"ok": True, "game_id": game_id, "result": status.get("result")}

        if not status.get("your_turn"):
            time.sleep(poll_sleep_sec)
            continue

        if not quota.allow():
            reason = quota.stop("rpm_or_rpd")
            _finish_live_game(client, game_id, logger, slot)
            logger.write(
                "slot_stopped",
                game_id=game_id,
                model=slot.inscribed_id,
                provider=slot.provider,
                quota=reason,
            )
            entries = [entry for entry in client.load_queue() if entry.game_id != game_id]
            client.save_queue(entries)
            return {"ok": False, "reason": reason, "game_id": game_id}

        observation_payload = client.fetch_observation(game_id, obs_mode)
        board_text = observation_payload["board_text"]
        board_png = observation_payload.get("board_png")
        if obs_mode == OBSERVATION_TEXT:
            board_png = None

        try:
            move = adapter.choose_move(board_text=board_text, board_png=board_png)
        except Exception as exc:
            logger.write(
                "provider_error",
                game_id=game_id,
                model=slot.inscribed_id,
                provider=slot.provider,
                error=str(exc),
            )
            _finish_live_game(client, game_id, logger, slot)
            return {"ok": False, "reason": "provider_error", "game_id": game_id}

        quota.record()

        try:
            moved = client.move(game_id, move)
        except AgentHttpError as exc:
            logger.write(
                "move_rejected",
                game_id=game_id,
                model=slot.inscribed_id,
                provider=slot.provider,
                error=str(exc),
                extra={"move": move},
            )
            _finish_live_game(client, game_id, logger, slot)
            return {"ok": False, "reason": "illegal_move", "game_id": game_id, "move": move}

        if not moved.get("ok"):
            logger.write(
                "move_rejected",
                game_id=game_id,
                model=slot.inscribed_id,
                provider=slot.provider,
                error=str(moved.get("error") or "move failed"),
                extra={"move": move},
            )
            _finish_live_game(client, game_id, logger, slot)
            return {"ok": False, "reason": "illegal_move", "game_id": game_id, "move": move}

        agent_plies += 1
        if max_agent_plies is not None and agent_plies >= max_agent_plies:
            _finish_live_game(client, game_id, logger, slot)
            status_after = client.status(game_id)
            entries = [entry for entry in client.load_queue() if entry.game_id != game_id]
            client.save_queue(entries)
            return {
                "ok": True,
                "game_id": game_id,
                "result": status_after.get("result"),
                "reason": "max_agent_plies",
            }

        if moved.get("game_over"):
            client.pgn(game_id)
            logger.write(
                "game_finished",
                game_id=game_id,
                model=slot.inscribed_id,
                provider=slot.provider,
                extra={"result": moved.get("result")},
            )
            entries = [entry for entry in client.load_queue() if entry.game_id != game_id]
            client.save_queue(entries)
            return {"ok": True, "game_id": game_id, "result": moved.get("result")}

    logger.write(
        "game_timeout",
        game_id=game_id,
        model=slot.inscribed_id,
        provider=slot.provider,
        error="max_wait_loops",
    )
    _finish_live_game(client, game_id, logger, slot)
    return {"ok": False, "reason": "timeout", "game_id": game_id}
