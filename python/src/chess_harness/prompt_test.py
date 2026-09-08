"""Local prompt-test helpers (overlay start, committee thread, briefs)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import chess

from .board_controller import BoardController
from .commands import cmd_new
from .elo import ELOLadder
from .game_ids import new_game_id
from .game_manager import GameBusyError, GameManager
from .opponents import get_catalog
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


def _agent_turn_index(state: Dict[str, Any]) -> int:
    """Completed agent moves (0 before the first agent move is played)."""
    moves = state.get("moves") or []
    agent_is_white = state.get("agent_color") == "WHITE"
    count = 0
    for index in range(len(moves)):
        agent_move = (index % 2 == 0) if agent_is_white else (index % 2 == 1)
        if agent_move:
            count += 1
    return count


def _default_thread_data() -> Dict[str, Any]:
    return {"messages": [], "votes": [], "status": "open", "turn": 0}


def _migrate_messages(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    if data.get("messages"):
        return list(data["messages"])
    notes = data.get("notes") or []
    migrated: List[Dict[str, Any]] = []
    for note in notes:
        entry = dict(note)
        entry.setdefault("kind", "say")
        migrated.append(entry)
    return migrated


def _load_thread_data(game_id: str) -> Dict[str, Any]:
    path = _thread_path(game_id)
    if not path.is_file():
        data = _default_thread_data()
        ply_path = _ply_path(game_id)
        if ply_path.is_file():
            ply_data = json.loads(ply_path.read_text(encoding="utf-8"))
            data["turn"] = int(ply_data.get("ply", 0))
        return data
    data = json.loads(path.read_text(encoding="utf-8"))
    data["messages"] = _migrate_messages(data)
    data.setdefault("votes", [])
    data.setdefault("status", "open")
    if "turn" not in data:
        ply_path = _ply_path(game_id)
        if ply_path.is_file():
            ply_data = json.loads(ply_path.read_text(encoding="utf-8"))
            data["turn"] = int(ply_data.get("ply", 0))
        else:
            data["turn"] = 0
    return data


def _save_thread_data(game_id: str, data: Dict[str, Any]) -> None:
    root = _thread_root(game_id)
    root.mkdir(parents=True, exist_ok=True)
    payload = {
        "messages": data.get("messages") or [],
        "votes": data.get("votes") or [],
        "status": data.get("status") or "open",
        "turn": int(data.get("turn") or 0),
    }
    _thread_path(game_id).write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _committee_seats(state: Dict[str, Any]) -> int:
    pack = load_pack(str(state["prompt_pack"]))
    return int(pack.seats or 3)


def _validate_seat(state: Dict[str, Any], seat: int) -> Optional[str]:
    seats = _committee_seats(state)
    if seat < 1 or seat > seats:
        return f"seat must be between 1 and {seats}"
    return None


def _current_turn_votes(thread_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    turn = int(thread_data.get("turn") or 0)
    votes: List[Dict[str, Any]] = []
    for vote in thread_data.get("votes") or []:
        vote_turn = vote.get("turn")
        if vote_turn is None or int(vote_turn) == turn:
            votes.append(vote)
    return votes


def _thread_response(
    game_id: str,
    state: Dict[str, Any],
    *,
    data: Optional[Dict[str, Any]] = None,
    ok: bool = True,
    error: Optional[str] = None,
) -> Dict[str, Any]:
    thread_data = data if data is not None else _load_thread_data(game_id)
    response: Dict[str, Any] = {
        "ok": ok,
        "game_id": game_id,
        "turn": int(thread_data.get("turn") or 0),
        "seats": _committee_seats(state),
        "messages": list(thread_data.get("messages") or []),
        "votes": _current_turn_votes(thread_data),
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


def _append_message(
    thread_data: Dict[str, Any],
    *,
    kind: str,
    text: str,
    seat: int = 0,
    uci: Optional[str] = None,
) -> None:
    entry: Dict[str, Any] = {
        "kind": kind,
        "seat": seat,
        "text": text,
        "ts": _utc_now(),
        "turn": int(thread_data.get("turn") or 0),
    }
    if uci is not None:
        entry["uci"] = uci
    thread_data.setdefault("messages", []).append(entry)


def _shared_opponent_id(model_id: str, opponent: Optional[str]) -> str:
    if opponent is not None:
        return opponent
    agent_elo = ELOLadder().get_rating(model_id)
    return get_catalog().select_by_elo(agent_elo).id


def cmd_prompt_test_thread(game_id: str) -> Dict[str, Any]:
    """Return the full committee chat plus current-turn votes."""
    state, error = _ensure_committee_game(game_id)
    if state is None:
        return {"ok": False, "error": error}
    return _thread_response(game_id, state)


def cmd_prompt_test_say(game_id: str, seat: int, text: str) -> Dict[str, Any]:
    """Post a discussion note for a committee seat. Chat is never wiped."""
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

            thread_data = _load_thread_data(game_id)
            _append_message(thread_data, kind="say", text=text, seat=seat)
            _save_thread_data(game_id, thread_data)

            ctrl._touch_activity(state)
            if not gm.save_state(game_id, state):
                return {"ok": False, "error": "Failed to save game state"}

            return _thread_response(game_id, state, data=thread_data)
    except GameBusyError as exc:
        return {"ok": False, "error": str(exc)}


def _reject_illegal_vote(
    game_id: str,
    state: Dict[str, Any],
    thread_data: Dict[str, Any],
    seat: int,
    move_str: str,
    parsed_error: str,
) -> Dict[str, Any]:
    blunt = (
        f"{parsed_error}. That vote was not counted. "
        "Look at the PNG and vote a different move."
    )
    _append_message(
        thread_data,
        kind="system",
        text=f"Seat {seat} voted {move_str} — illegal. Not counted.",
        seat=0,
        uci=move_str,
    )
    _save_thread_data(game_id, thread_data)
    response = _thread_response(game_id, state, data=thread_data, ok=False, error=blunt)
    response["move_error"] = parsed_error
    return response


def cmd_prompt_test_vote(game_id: str, seat: int, uci: str) -> Dict[str, Any]:
    """Record a committee vote; two matching legal votes play via AvE executor."""
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

            thread_data = _load_thread_data(game_id)
            turn = _agent_turn_index(state)
            thread_data["turn"] = turn

            board = chess.Board(state["board_fen"])
            parsed = ctrl._parse_move(board, game_id, uci.strip())
            if isinstance(parsed, dict):
                ctrl._touch_activity(state)
                if not gm.save_state(game_id, state):
                    return {"ok": False, "error": "Failed to save game state"}
                return _reject_illegal_vote(
                    game_id,
                    state,
                    thread_data,
                    seat,
                    uci.strip(),
                    str(parsed.get("error") or "Illegal move"),
                )

            move_uci = parsed.uci()
            current_votes = [
                vote
                for vote in _current_turn_votes(thread_data)
                if int(vote.get("seat", -1)) != seat
            ]
            current_votes.append(
                {
                    "seat": seat,
                    "turn": turn,
                    "uci": move_uci,
                    "ts": _utc_now(),
                }
            )
            older = [
                vote
                for vote in thread_data.get("votes") or []
                if int(vote.get("turn", turn)) != turn
            ]
            thread_data["votes"] = older + current_votes
            _append_message(
                thread_data,
                kind="vote",
                text=f"Seat {seat} votes {move_uci}",
                seat=seat,
                uci=move_uci,
            )

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
                move_result = ctrl._execute_ave_move_locked(game_id, state, majority_uci)
                if not move_result.get("ok"):
                    move_error = str(move_result.get("error") or "move failed")
                    thread_data["status"] = "open"
                    _append_message(
                        thread_data,
                        kind="system",
                        text=f"Harness rejected {majority_uci}: {move_error}",
                        seat=0,
                        uci=majority_uci,
                    )
                    _save_thread_data(game_id, thread_data)
                    response = _thread_response(game_id, state, data=thread_data)
                    response["move_error"] = move_error
                    return response

                played_line = f"Played {majority_uci}."
                moves = state.get("moves") or []
                if len(moves) >= 2:
                    played_line = f"Played {majority_uci}. Engine replied {moves[-1]}."
                if state.get("status") != "in_progress":
                    played_line = (
                        f"{played_line} Game over: {state.get('result')}."
                    )
                _append_message(thread_data, kind="system", text=played_line, seat=0)
                thread_data["votes"] = []
                if state.get("status") == "in_progress":
                    thread_data["turn"] = _agent_turn_index(state)
                    thread_data["status"] = "open"
                else:
                    thread_data["status"] = "played"
                _save_thread_data(game_id, thread_data)
                response = _thread_response(game_id, state, data=thread_data)
                response["move"] = majority_uci
                response["status"] = "played"
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

    shared_opponent = _shared_opponent_id(model_id, opponent)
    games: List[Dict[str, Any]] = []
    for pack in validated:
        game_id = new_game_id()
        created = cmd_new(
            game_id=game_id,
            color="white",
            skill=None,
            fen=None,
            model_name=model_id,
            force=True,
            prompt_pack=pack.id,
            opponent=shared_opponent,
        )
        if not created.get("ok"):
            return {
                "ok": False,
                "error": created.get("error", "failed to create game"),
            }

        game_entry: Dict[str, Any] = {
            "game_id": created["game_id"],
            "board_path": created["board_path"],
            "model": model_id,
            "prompt_pack": pack.id,
            "kind": pack.kind,
            "opponent_id": created.get("opponent_id") or shared_opponent,
            "agent_color": created.get("agent_color") or "WHITE",
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
            _save_thread_data(created["game_id"], _default_thread_data())
            game_entry["seats"] = seats
            games.append(game_entry)
            continue

        game_entry["brief"] = render_overlay_brief(
            pack,
            game_id=created["game_id"],
            board_path=created["board_path"],
            model_id=model_id,
        )
        games.append(game_entry)

    return {"ok": True, "games": games, "opponent_id": shared_opponent}
