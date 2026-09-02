"""Local prompt-test helpers (overlay start, committee thread, briefs)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .board_controller import BoardController
from .commands import cmd_new
from .game_ids import new_game_id
from .game_manager import GameBusyError, GameManager
from .paths import resolve_base_dir
from .prompt_packs import (
    PromptPack,
    is_committee_state,
    load_pack,
    render_committee_brief,
    render_overlay_brief,
)

__all__ = [
    "cmd_prompt_test_say",
    "cmd_prompt_test_start",
    "cmd_prompt_test_thread",
    "cmd_prompt_test_vote",
    "parse_packs_list",
]


def parse_packs_list(packs_str: str) -> List[str]:
    """Parse comma-separated pack ids; preserve order; reject empty tokens."""
    if not packs_str.strip():
        raise ValueError("--packs must not be empty")
    pack_ids: List[str] = []
    for part in packs_str.split(","):
        token = part.strip()
        if not token:
            raise ValueError("empty pack id in --packs list")
        pack_ids.append(token)
    if not pack_ids:
        raise ValueError("--packs must not be empty")
    return pack_ids


def _game_manager() -> GameManager:
    return GameManager()


def _controller() -> BoardController:
    gm = _game_manager()
    return BoardController(gm)


def _thread_root(game_id: str) -> Path:
    return resolve_base_dir() / "prompt_test" / game_id


def _ply_path(game_id: str) -> Path:
    return _thread_root(game_id) / "ply.json"


def _thread_path(game_id: str) -> Path:
    return _thread_root(game_id) / "thread.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _agent_ply_index(state: Dict[str, Any]) -> int:
    """Completed agent plies (0 before the first agent move is played)."""
    moves = state.get("moves") or []
    agent_is_white = state.get("agent_color") == "WHITE"
    count = 0
    for index in range(len(moves)):
        agent_move = (index % 2 == 0) if agent_is_white else (index % 2 == 1)
        if agent_move:
            count += 1
    return count


def _load_current_ply(game_id: str) -> int:
    path = _ply_path(game_id)
    if not path.is_file():
        return 0
    data = json.loads(path.read_text(encoding="utf-8"))
    return int(data.get("ply", 0))


def _save_current_ply(game_id: str, ply: int) -> None:
    root = _thread_root(game_id)
    root.mkdir(parents=True, exist_ok=True)
    _ply_path(game_id).write_text(json.dumps({"ply": ply}), encoding="utf-8")


def _default_thread_data() -> Dict[str, Any]:
    return {"notes": [], "votes": [], "status": "open"}


def _load_thread_data(game_id: str) -> Dict[str, Any]:
    path = _thread_path(game_id)
    if not path.is_file():
        return _default_thread_data()
    data = json.loads(path.read_text(encoding="utf-8"))
    data.setdefault("notes", [])
    data.setdefault("votes", [])
    data.setdefault("status", "open")
    return data


def _save_thread_data(game_id: str, data: Dict[str, Any]) -> None:
    root = _thread_root(game_id)
    root.mkdir(parents=True, exist_ok=True)
    _thread_path(game_id).write_text(json.dumps(data, indent=2), encoding="utf-8")


def _committee_seats(state: Dict[str, Any]) -> int:
    pack = load_pack(str(state["prompt_pack"]))
    return int(pack.seats or 3)


def _validate_seat(state: Dict[str, Any], seat: int) -> Optional[str]:
    seats = _committee_seats(state)
    if seat < 1 or seat > seats:
        return f"seat must be between 1 and {seats}"
    return None


def _ply_entries(entries: List[Dict[str, Any]], ply: int) -> List[Dict[str, Any]]:
    return [entry for entry in entries if int(entry.get("ply", -1)) == ply]


def _thread_response(
    game_id: str,
    state: Dict[str, Any],
    *,
    data: Optional[Dict[str, Any]] = None,
    ok: bool = True,
    error: Optional[str] = None,
) -> Dict[str, Any]:
    ply = _load_current_ply(game_id)
    thread_data = data if data is not None else _load_thread_data(game_id)
    response: Dict[str, Any] = {
        "ok": ok,
        "game_id": game_id,
        "ply": ply,
        "seats": _committee_seats(state),
        "notes": _ply_entries(thread_data.get("notes", []), ply),
        "votes": _ply_entries(thread_data.get("votes", []), ply),
        "status": thread_data.get("status", "open"),
    }
    if error is not None:
        response["error"] = error
    return response


def _ensure_committee_game(game_id: str) -> tuple[Optional[Dict[str, Any]], Optional[str]]:
    state = _game_manager().load_state(game_id)
    if not state:
        return None, f"Game {game_id} not found"
    if not is_committee_state(state):
        return None, "not a committee game"
    return state, None


def _game_over_error(state: Dict[str, Any]) -> Optional[str]:
    if state.get("status") == "in_progress":
        return None
    return f"Game is already over: {state.get('result')}"


def _advance_played_ply_if_needed(
    game_id: str, thread_data: Dict[str, Any], state: Dict[str, Any]
) -> Dict[str, Any]:
    """After a successful majority play, advance to the next ply on thread read."""
    if thread_data.get("status") != "played":
        return thread_data
    if state.get("status") != "in_progress":
        return thread_data
    ply = _load_current_ply(game_id)
    _clear_ply_thread(thread_data, ply)
    _save_current_ply(game_id, ply + 1)
    thread_data["status"] = "open"
    _save_thread_data(game_id, thread_data)
    return thread_data


def cmd_prompt_test_thread(game_id: str) -> Dict[str, Any]:
    """Return the committee thread for the current ply."""
    state, error = _ensure_committee_game(game_id)
    if state is None:
        return {"ok": False, "error": error}
    thread_data = _advance_played_ply_if_needed(
        game_id, _load_thread_data(game_id), state
    )
    return _thread_response(game_id, state, data=thread_data)


def cmd_prompt_test_say(game_id: str, seat: int, text: str) -> Dict[str, Any]:
    """Post a discussion note for a committee seat on the current ply."""
    gm = _game_manager()
    ctrl = _controller()
    try:
        with gm.game_lock(game_id):
            state = gm.load_state(game_id)
            if not state:
                return {"ok": False, "error": f"Game {game_id} not found"}
            if not is_committee_state(state):
                return {"ok": False, "error": "not a committee game"}
            over = _game_over_error(state)
            if over:
                return {"ok": False, "error": over}

            seat_error = _validate_seat(state, seat)
            if seat_error:
                return {"ok": False, "error": seat_error}

            ply = _load_current_ply(game_id)
            if ply != _agent_ply_index(state):
                return {"ok": False, "error": "wrong ply"}

            thread_data = _load_thread_data(game_id)
            if thread_data.get("status") == "played":
                return {"ok": False, "error": "wrong ply"}

            thread_data.setdefault("notes", []).append(
                {
                    "seat": seat,
                    "ply": ply,
                    "text": text,
                    "ts": _utc_now(),
                }
            )
            _save_thread_data(game_id, thread_data)

            ctrl._touch_activity(state)
            if not gm.save_state(game_id, state):
                return {"ok": False, "error": "Failed to save game state"}

            return _thread_response(game_id, state, data=thread_data)
    except GameBusyError as exc:
        return {"ok": False, "error": str(exc)}


def _clear_ply_thread(thread_data: Dict[str, Any], ply: int) -> None:
    thread_data["notes"] = [
        note for note in thread_data.get("notes", []) if int(note.get("ply", -1)) != ply
    ]
    thread_data["votes"] = [
        vote for vote in thread_data.get("votes", []) if int(vote.get("ply", -1)) != ply
    ]


def _votes_for_ply(thread_data: Dict[str, Any], ply: int) -> List[Dict[str, Any]]:
    return _ply_entries(thread_data.get("votes", []), ply)


def cmd_prompt_test_vote(game_id: str, seat: int, uci: str) -> Dict[str, Any]:
    """Record a committee vote; majority on the current ply plays via AvE executor."""
    gm = _game_manager()
    ctrl = _controller()
    try:
        with gm.game_lock(game_id):
            state = gm.load_state(game_id)
            if not state:
                return {"ok": False, "error": f"Game {game_id} not found"}
            if not is_committee_state(state):
                return {"ok": False, "error": "not a committee game"}
            over = _game_over_error(state)
            if over:
                return {"ok": False, "error": over}

            seat_error = _validate_seat(state, seat)
            if seat_error:
                return {"ok": False, "error": seat_error}

            ply = _load_current_ply(game_id)
            if ply != _agent_ply_index(state):
                return {"ok": False, "error": "wrong ply"}

            thread_data = _load_thread_data(game_id)
            status = thread_data.get("status", "open")
            if status == "played":
                return {"ok": False, "error": "wrong ply"}

            current_votes = _votes_for_ply(thread_data, ply)
            current_votes = [vote for vote in current_votes if int(vote.get("seat", -1)) != seat]
            current_votes.append(
                {
                    "seat": seat,
                    "ply": ply,
                    "uci": uci,
                    "ts": _utc_now(),
                }
            )
            other_votes = [
                vote
                for vote in thread_data.get("votes", [])
                if int(vote.get("ply", -1)) != ply
            ]
            thread_data["votes"] = other_votes + current_votes

            ctrl._touch_activity(state)
            if not gm.save_state(game_id, state):
                return {"ok": False, "error": "Failed to save game state"}

            majority_uci: Optional[str] = None
            counts: Dict[str, int] = {}
            for vote in current_votes:
                move = str(vote["uci"])
                counts[move] = counts.get(move, 0) + 1
                if counts[move] >= 2:
                    majority_uci = move
                    break

            if majority_uci is not None:
                if status == "played":
                    return _thread_response(game_id, state, data=thread_data)

                move_result = ctrl._execute_ave_move_locked(game_id, state, majority_uci)
                if not move_result.get("ok"):
                    thread_data["status"] = "rejected"
                    _clear_ply_thread(thread_data, ply)
                    _save_thread_data(game_id, thread_data)
                    response = _thread_response(game_id, state, data=thread_data)
                    response["move_error"] = move_result.get("error")
                    return response

                thread_data["status"] = "played"
                _save_thread_data(game_id, thread_data)
                response = _thread_response(game_id, state, data=thread_data)
                response["move"] = majority_uci
                return response

            if len(current_votes) >= 3 and len({vote["uci"] for vote in current_votes}) == 3:
                thread_data["status"] = "tied"
                _save_thread_data(game_id, thread_data)
                return _thread_response(game_id, state, data=thread_data)

            thread_data["status"] = "open"
            _save_thread_data(game_id, thread_data)
            return _thread_response(game_id, state, data=thread_data)
    except GameBusyError as exc:
        return {"ok": False, "error": str(exc)}


def cmd_prompt_test_start(
    model_id: str,
    pack_ids: List[str],
    *,
    opponent: Optional[str] = None,
) -> Dict[str, Any]:
    """Create overlay or committee games and return filled agent briefs."""
    validated: List[PromptPack] = []
    for pack_id in pack_ids:
        try:
            validated.append(load_pack(pack_id))
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}

    games: List[Dict[str, Any]] = []
    for pack in validated:
        game_id = new_game_id()
        new_kwargs: Dict[str, Any] = {
            "game_id": game_id,
            "color": "white" if pack.kind == "committee" else None,
            "skill": None,
            "fen": None,
            "model_name": model_id,
            "force": True,
            "prompt_pack": pack.id,
        }
        if opponent is not None:
            new_kwargs["opponent"] = opponent
        created = cmd_new(**new_kwargs)
        if not created.get("ok"):
            return {
                "ok": False,
                "error": created.get("error", "failed to create game"),
            }

        if pack.kind == "committee":
            seat_count = int(pack.seats or 3)
            seats: List[Dict[str, Any]] = []
            for seat in range(1, seat_count + 1):
                seats.append(
                    {
                        "seat": seat,
                        "brief": render_committee_brief(
                            pack,
                            game_id=created["game_id"],
                            board_path=created["board_path"],
                            model_id=model_id,
                            seat=seat,
                        ),
                    }
                )
            _save_current_ply(created["game_id"], 0)
            _save_thread_data(created["game_id"], _default_thread_data())
            games.append(
                {
                    "game_id": created["game_id"],
                    "board_path": created["board_path"],
                    "model": model_id,
                    "prompt_pack": pack.id,
                    "kind": pack.kind,
                    "seats": seats,
                }
            )
            continue

        brief = render_overlay_brief(
            pack,
            game_id=created["game_id"],
            board_path=created["board_path"],
            model_id=model_id,
        )
        games.append(
            {
                "game_id": created["game_id"],
                "board_path": created["board_path"],
                "model": model_id,
                "prompt_pack": pack.id,
                "kind": pack.kind,
                "brief": brief,
            }
        )

    return {"ok": True, "games": games}
