"""Conservative engine-verified ! / !! detection; candidate lines stay private.

Concepts: Chess.com's published Great/Brilliant definitions. Exact thresholds below
are this benchmark's own fixed policy, never adjusted by an agent's mapped rating.
"""
from __future__ import annotations

import math
import hashlib
import json

import chess
import chess.engine

VERSION = "critical-sound-sacrifice-v1"
VERIFICATION_SCHEMA_VERSION = "exceptional-verification-v2"
# VERSION identifies the evidence structure; policy revisions are separate.
POLICY_VERSION = "critical-discovery-sacrifice-policy-v7"
PROFILE = {"version": POLICY_VERSION, "evidence_version": VERSION, "passes": [{"depth": 18, "seconds": .35, "minimum_depth": 14},
                                           {"depth": 22, "seconds": 1.0, "minimum_depth": 18}],
           "multipv": 2, "critical_gap_pp": 3.0, "critical_alternative_ceiling": .85,
           "minimum_chance": .15, "brilliant_minimum_chance": .30,
           "alternative_winning_chance": .90, "sacrifice_min_cp": 100, "near_best_loss_pp": 3.0,
           "routine_check_evasion_requires_difficulty": True,
           "verification_cache": "position-history reuse", "discovery_cache": "cleared before trace",
           "discovery": {"shallow_depth": 4, "stable_depths": 2, "minimum_gap_pp": 3.0,
                         "great_depth": 5, "great_gain_pp": 1.5,
                         "brilliant_depth": 8, "brilliant_gain_pp": 3.0,
                         "refinement_great_gain_pp": 2.5, "refinement_brilliant_gain_pp": 5.0,
                         "refresh_screen_loss_pp": 0.0},
           "quiet_great": {"minimum_ply": 9, "critical_gap_pp": 0.5, "critical_gap_cp": 8,
                           "late_choice_shallow_cp": 15, "late_choice_deep_gain_cp": 15,
                           "late_choice_depth": 5, "late_choice_stable_depths": 3},
           "routine_guard": {"minimum_gap_pp": 5.0, "great_depth": 6, "stable_depths": 3,
                             "great_gain_pp": 3.0, "refinement_great_gain_pp": 6.0}}
VALUES = {chess.PAWN: 100, chess.KNIGHT: 300, chess.BISHOP: 300,
          chess.ROOK: 500, chess.QUEEN: 900, chess.KING: 20000}


def _chance(score):
    cp = score.score(mate_score=10000)
    return 1 / (1 + math.exp(-.00368208 * max(-1000, min(1000, cp))))


def _search(engine, board, settings, trace=False):
    limit = chess.engine.Limit(depth=settings["depth"], time=settings["seconds"])
    frames = {}
    if not trace:
        return engine.analyse(board, limit, multipv=2), frames
    with engine.analysis(board, limit, multipv=2) as search:
        for info in search:
            if (info.get("multipv", 1) == 1 and info.get("depth") and info.get("score")
                    and info.get("pv") and not info.get("upperbound") and not info.get("lowerbound")):
                score = info["score"].pov(board.turn)
                frames[info["depth"]] = {"move": info["pv"][0], "cp": score.score(mate_score=10000),
                                          "chance": _chance(score)}
        lines = [dict(line) for line in search.multipv]
    return lines, frames


def discovery_evidence(frames, move):
    settings = PROFILE["discovery"]
    shallow = frames.get(settings["shallow_depth"])
    if not shallow or not frames:
        return None
    end = max(frames)
    start = end
    while start in frames and frames[start]["move"] == move:
        start -= 1
    start += 1
    if end - start + 1 < settings["stable_depths"]:
        return None
    return {"shallow_depth": settings["shallow_depth"], "shallow_root_uci": shallow["move"].uci(),
            "shallow_cp": shallow.get("cp"), "discovered_depth": start,
            "final_run_start_depth": start,
            "stable_through_depth": end, "final_run_depths": end - start + 1,
            "shallow_chance": round(shallow["chance"], 5), "root_changed": shallow["move"] != move}


def _exchange_gain(board, square, budget, depth=10):
    """Legal capture-tree material gain; unknown if the bounded tree is exhausted."""
    captures = [move for move in board.legal_moves if move.to_square == square and board.is_capture(move)]
    if not captures:
        return 0
    if depth <= 0:
        return None
    best = 0  # A side may decline the exchange.
    for move in captures:
        budget[0] -= 1
        if budget[0] < 0:
            return None
        piece = board.piece_at(square)
        captured = VALUES[piece.piece_type] if piece else 100  # en passant
        promoted = VALUES.get(move.promotion, 100) - 100 if move.promotion else 0
        board.push(move)
        try:
            reply = _exchange_gain(board, square, budget, depth - 1)
        finally:
            board.pop()
        if reply is None:
            return None
        best = max(best, captured + promoted - reply)
    return best


def sacrifice_cost(board: chess.Board, move: chess.Move):
    piece = board.piece_at(move.from_square)
    if not piece or piece.piece_type in {chess.PAWN, chess.KING}:
        return 0
    captured = board.piece_at(move.to_square)
    gain = VALUES[captured.piece_type] if captured else (100 if board.is_en_passant(move) else 0)
    after = board.copy(stack=True)
    after.push(move)
    if after.is_game_over():
        return 0
    exchange = _exchange_gain(after, move.to_square, [256])
    return None if exchange is None else max(0, exchange - gain)


def difficult(discovery, gain, gap, settings):
    if not discovery or gap < settings["minimum_gap_pp"]:
        return False
    late = discovery.get("root_changed") and discovery.get("discovered_depth", 0) >= settings["great_depth"]
    return (late and gain >= settings["great_gain_pp"]) or gain >= settings["refinement_great_gain_pp"]


def routine_check_evasion(board, evidence):
    """A unique check block alone is insufficient evidence of difficulty.

    Uses the saved verification evidence too, so this stricter exclusion can
    be applied to historical artifacts without repeating engine searches.
    """
    if not board.is_check() or (evidence.get("sacrifice_cp") or 0) >= PROFILE["sacrifice_min_cp"]:
        return False
    discovery = evidence.get("discovery") or {}
    if not discovery or len(evidence.get("passes", [])) != 2:
        return True
    settings = PROFILE["routine_guard"]
    if discovery.get("stable_through_depth", 0) - discovery.get("discovered_depth", 0) + 1 < settings["stable_depths"]:
        return True
    for item in evidence["passes"]:
        gain = item.get("discovery_gain_pp", 0)
        gap = (item["best_chance"] - item["second_chance"]) * 100
        if not difficult(discovery, gain, gap, settings):
            return True
    return False


def _search_profile():
    return {
        "passes": [dict(item) for item in PROFILE["passes"]],
        "multipv": PROFILE["multipv"],
        "cold_discovery": {"depth": PROFILE["passes"][0]["depth"],
                           "seconds": PROFILE["passes"][0]["seconds"],
                           "minimum_depth": PROFILE["passes"][0]["minimum_depth"],
                           "multipv": 2, "clear_hash": True},
        "forced_shallow": {"depth": 4, "seconds": None, "root_moves": "played-only", "clear_hash": True},
    }


def _position_key(board):
    identity = {"root_fen": board.root().fen(), "moves": [move.uci() for move in board.move_stack]}
    encoded = json.dumps(identity, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


def _new_quiet_context(board, move):
    if len(board.move_stack) + 1 < PROFILE["quiet_great"]["minimum_ply"]:
        return False
    if board.is_check() or board.is_capture(move):
        return False
    after = board.copy(stack=True)
    after.push(move)
    for position in (board, after):
        if (position.is_insufficient_material() or position.is_game_over(claim_draw=True)
                or position.can_claim_threefold_repetition() or position.can_claim_fifty_moves()):
            return False
    return True


def _score_record(line, board):
    if not line.get("pv") or not line.get("score"):
        return None
    score = line["score"].pov(board.turn)
    return {"uci": line["pv"][0].uci(), "cp": score.score(mate_score=10000),
            "mate": score.mate(), "chance": round(_chance(score), 6),
            "depth": line.get("depth", 0),
            "bounded": bool(line.get("upperbound") or line.get("lowerbound"))}


def _normalise_single(info):
    return info[0] if isinstance(info, list) and info else info


def _cold_shallow_probe(native, board, move):
    if "Clear Hash" not in getattr(native, "options", {}):
        return None, None
    settings = PROFILE["quiet_great"]
    native.configure({"Clear Hash": None})
    lines = native.analyse(board, chess.engine.Limit(depth=4), multipv=2)
    if isinstance(lines, dict):
        lines = [lines]
    roots = [_score_record(line, board) for line in lines[:2]]
    roots = [root for root in roots if root is not None]
    if not roots or roots[0]["depth"] < 4 or roots[0]["bounded"]:
        return {"roots": roots, "valid": False}, None
    probe = {"depth": roots[0]["depth"], "roots": roots, "root_changed": roots[0]["uci"] != move.uci(),
             "shallow_cp": roots[0]["cp"], "shallow_chance": roots[0]["chance"], "bounded": roots[0]["bounded"]}
    forced = None
    if probe["root_changed"]:
        # This is a separate hash-cleared, fixed-depth forced-move score.
        native.configure({"Clear Hash": None})
        line = _normalise_single(native.analyse(board, chess.engine.Limit(depth=4), root_moves=[move])) or {}
        root = _score_record(line, board)
        if root is not None:
            forced = {"depth": root["depth"], "uci": root["uci"], "cp": root["cp"],
                      "chance": root["chance"], "bounded": root["bounded"], "hash_cleared": True}
    probe["valid"] = bool(len(roots) >= 2 and roots[0]["depth"] >= 4 and not roots[0]["bounded"]
                         and roots[0]["uci"] != roots[1]["uci"])
    return probe, forced


def _valid_passes(verification, require_played_top=False):
    passes = verification.get("passes")
    if not isinstance(passes, list) or len(passes) != 2:
        return False
    for item, settings in zip(passes, PROFILE["passes"]):
        if not isinstance(item, dict):
            return False
        roots = item.get("roots") if isinstance(item, dict) else None
        if (item.get("target_depth") != settings["depth"] or item.get("minimum_depth") != settings["minimum_depth"]
                or not isinstance(roots, list) or len(roots) != 2):
            return False
        if any(not isinstance(root, dict) for root in roots):
            return False
        if any(not isinstance(root.get("uci"), str) or not isinstance(root.get("cp"), int)
               or not isinstance(root.get("depth"), int) or root["depth"] < settings["minimum_depth"]
               or root.get("bounded") is not False for root in roots):
            return False
        if roots[0]["uci"] == roots[1]["uci"]:
            return False
        if require_played_top and roots[0]["uci"] != verification.get("played_uci"):
            return False
    return True


def _cached_result(label, verification, pass_evidence, route):
    for item in pass_evidence:
        item["search_label"] = item["label"]
        item["label"] = label
    discovery = dict(verification.get("discovery") or {})
    discovery.pop("shallow_root_uci", None)
    return {"label": label, "evidence": {"version": VERSION, "policy_version": POLICY_VERSION,
                                           "passes": pass_evidence,
                                           "sacrifice_cp": verification.get("sacrifice_cp"),
                                           "discovery": discovery or None,
                                           "route": route}}


def _grade_verified(board, move, verification):
    """Purely grade verified numeric evidence; never searches or mutates inputs."""
    if not _valid_passes(verification):
        return None
    roots_by_pass = [item["roots"] for item in verification["passes"]]
    discovery = verification.get("discovery")
    sacrifice = verification.get("sacrifice_cp")
    if sacrifice is not None and not isinstance(sacrifice, int):
        return None
    cached_pass_evidence = []
    legacy_allowed = True
    for item, roots in zip(verification["passes"], roots_by_pass):
        best_root, second_root = roots
        best, second = _chance(chess.engine.Cp(best_root["cp"])), _chance(chess.engine.Cp(second_root["cp"]))
        played_is_best = best_root["uci"] == move.uci()
        played_root = best_root if played_is_best else second_root if second_root["uci"] == move.uci() else item.get("played")
        sound_offer = sacrifice is not None and sacrifice >= PROFILE["sacrifice_min_cp"]
        if not played_is_best:
            if not sound_offer or not isinstance(played_root, dict):
                legacy_allowed = False
                cached_pass_evidence.append(None)
                continue
            if (played_root.get("uci") != move.uci() or not isinstance(played_root.get("cp"), int)
                    or played_root.get("bounded") is not False
                    or played_root.get("depth", 0) < item["minimum_depth"]):
                return None
            played = _chance(chess.engine.Cp(played_root["cp"]))
            alternative = best
            if (best - played) * 100 > PROFILE["near_best_loss_pp"]:
                legacy_allowed = False
        else:
            played = best
            alternative = second
        if (played < PROFILE["minimum_chance"]
                or alternative >= PROFILE["alternative_winning_chance"]
                or all(abs(value - .5) <= .02 for value in (best, played, alternative))):
            legacy_allowed = False
        gap_pp = (best - second) * 100
        discovery_gain = (played - discovery["shallow_chance"]) * 100 if discovery and discovery.get("shallow_chance") is not None else 0
        brilliant = played >= PROFILE["brilliant_minimum_chance"] and sound_offer
        great = played_is_best and gap_pp >= PROFILE["critical_gap_pp"] and second < PROFILE["critical_alternative_ceiling"]
        if discovery and played_is_best and gap_pp >= PROFILE["discovery"]["minimum_gap_pp"]:
            great = great or difficult(discovery, discovery_gain, gap_pp, PROFILE["discovery"])
            brilliant = brilliant or (played >= PROFILE["brilliant_minimum_chance"] and (
                (discovery.get("root_changed") and discovery.get("discovered_depth", 0) >= PROFILE["discovery"]["brilliant_depth"]
                 and discovery_gain >= PROFILE["discovery"]["brilliant_gain_pp"])
                or discovery_gain >= PROFILE["discovery"]["refinement_brilliant_gain_pp"]))
        label = "brilliant" if brilliant else "great" if great else None
        if board.is_capture(move) and not sound_offer:
            nonobvious_capture = bool(discovery and discovery.get("root_changed")
                                      and discovery.get("discovered_depth", 0) >= PROFILE["routine_guard"]["great_depth"]
                                      and discovery.get("final_run_depths", 0) >= PROFILE["routine_guard"]["stable_depths"]
                                      and difficult(discovery, discovery_gain, gap_pp, PROFILE["routine_guard"]))
            if not nonobvious_capture:
                label = None
        if label is None:
            legacy_allowed = False
        cached_pass_evidence.append({"depth": min(best_root["depth"], second_root["depth"]),
                                     "best_chance": round(best, 4), "second_chance": round(second, 4),
                                     "played_chance": round(played, 4), "discovery_gain_pp": round(discovery_gain, 4),
                                     "label": label or "none"})
    if legacy_allowed and all(item and item["label"] in {"great", "brilliant"} for item in cached_pass_evidence):
        label = "brilliant" if all(item["label"] == "brilliant" for item in cached_pass_evidence) else "great"
        candidate = _cached_result(label, verification, cached_pass_evidence, "v6")
        if not routine_check_evasion(board, candidate["evidence"]):
            return candidate

    if not _new_quiet_context(board, move) or not _valid_passes(verification, require_played_top=True):
        return None
    quiet_settings = PROFILE["quiet_great"]
    passes = verification["passes"]
    # Route A: a small but explicit, mover-relative and raw-CP separation.
    route_a = all(
        (_chance(chess.engine.Cp(roots[0]["cp"])) >= PROFILE["minimum_chance"]
         and roots[0]["cp"] - roots[1]["cp"] >= quiet_settings["critical_gap_cp"]
         and (_chance(chess.engine.Cp(roots[0]["cp"]))
              - _chance(chess.engine.Cp(roots[1]["cp"]))) * 100
         >= quiet_settings["critical_gap_pp"])
        for roots in roots_by_pass
    )
    if route_a:
        rows = []
        for item, roots in zip(passes, roots_by_pass):
            best = _chance(chess.engine.Cp(roots[0]["cp"]))
            second = _chance(chess.engine.Cp(roots[1]["cp"]))
            rows.append({"depth": min(root["depth"] for root in roots), "best_chance": round(best, 4),
                         "second_chance": round(second, 4), "played_chance": round(best, 4),
                         "raw_cp_gap": roots[0]["cp"] - roots[1]["cp"], "label": "great"})
        return _cached_result("great", verification, rows, "quiet_critical_gap")

    # Route B: prove the played move was a real late choice, not engine ordering.
    forced = verification.get("forced_shallow") or {}
    cold = discovery or {}
    if (verification.get("discovery_trace_complete") is True
            and (verification.get("quiet_probe") or {}).get("valid") is True
            and cold.get("root_changed") is True
            and cold.get("final_run_start_depth", 0) >= quiet_settings["late_choice_depth"]
            and cold.get("final_run_depths", 0) >= quiet_settings["late_choice_stable_depths"]
            and isinstance(cold.get("shallow_cp"), int)
            and forced.get("uci") == move.uci() and isinstance(forced.get("cp"), int)
            and forced.get("depth", 0) >= 4 and forced.get("bounded") is False
            and cold["shallow_cp"] - forced["cp"] >= quiet_settings["late_choice_shallow_cp"]
            and all(isinstance(item.get("played"), dict)
                    and item["played"].get("uci") == move.uci()
                    and isinstance(item["played"].get("cp"), int)
                    and item["played"].get("bounded") is False
                    and item["played"].get("depth", 0) >= item["minimum_depth"]
                    and _chance(chess.engine.Cp(item["played"]["cp"])) >= PROFILE["minimum_chance"]
                    and item["played"]["cp"] - forced["cp"] >= quiet_settings["late_choice_deep_gain_cp"]
                    for item in passes)):
        rows = []
        for item in passes:
            best = _chance(chess.engine.Cp(item["roots"][0]["cp"]))
            second = _chance(chess.engine.Cp(item["roots"][1]["cp"]))
            played = _chance(chess.engine.Cp(item["played"]["cp"]))
            rows.append({"depth": item["played"]["depth"], "best_chance": round(best, 4),
                         "second_chance": round(second, 4), "played_chance": round(played, 4),
                         "shallow_best_cp": cold["shallow_cp"], "shallow_played_cp": forced["cp"],
                         "shallow_played_chance": forced["chance"], "shallow_played_depth": forced["depth"],
                         "deep_gain_cp": item["played"]["cp"] - forced["cp"], "label": "great"})
        return _cached_result("great", verification, rows, "quiet_late_choice")
    return None


def classify_cached(board: chess.Board, move: chess.Move, verification: dict) -> tuple[bool, dict | None]:
    """Return (definitive, result) for a matching private numeric proof.

    A false definitive flag means the caller must perform fresh engine analysis.
    A matching complete proof can be regraded after policy changes without storing PVs.
    """
    if not isinstance(verification, dict):
        return False, None
    if (verification.get("schema_version") != VERIFICATION_SCHEMA_VERSION
            or verification.get("search_profile") != _search_profile()
            or verification.get("played_uci") != move.uci()
            or verification.get("position_key") != _position_key(board)):
        return False, None
    if verification.get("definitive_rejection"):
        # An early stop did not save a complete proof, so its conclusion is
        # valid only under the exact policy that authorized the stop.
        if verification.get("policy_version") != POLICY_VERSION:
            return False, None
        first = verification.get("passes", [])
        sacrifice = verification.get("sacrifice_cp")
        no_offer = sacrifice is None or (isinstance(sacrifice, int)
                                         and sacrifice < PROFILE["sacrifice_min_cp"])
        if (verification["definitive_rejection"] == "played_not_top_no_offer"
                and isinstance(first, list) and len(first) == 1
                and _valid_single_pass(first[0], PROFILE["passes"][0]) and no_offer
                and first[0]["roots"][0]["uci"] != move.uci()):
            return True, None
        if (verification["definitive_rejection"] == "noneligible_first_pass_no_route"
                and isinstance(first, list) and len(first) == 1
                and _valid_single_pass(first[0], PROFILE["passes"][0]) and no_offer):
            return True, None
        return False, None
    if verification.get("complete") is not True or not _valid_passes(verification):
        return False, None
    try:
        result = _grade_verified(board, move, verification)
    except (KeyError, TypeError, ValueError, AttributeError):
        return False, None
    if result is not None and result.get("evidence", {}).get("route") in {"v6", "quiet_critical_gap"}:
        return True, result
    if _new_quiet_context(board, move):
        probe = verification.get("quiet_probe") or {}
        forced = verification.get("forced_shallow")
        if not _valid_quiet_probe(board, move, probe, forced):
            return False, None
        if probe.get("root_changed"):
            if probe["shallow_cp"] - forced["cp"] >= PROFILE["quiet_great"]["late_choice_shallow_cp"]:
                if verification.get("discovery_trace_complete") is not True:
                    return False, None
    return True, result


def _valid_single_pass(item, settings):
    roots = item.get("roots") if isinstance(item, dict) else None
    return bool(isinstance(item, dict)
                and item.get("target_depth") == settings["depth"] and item.get("minimum_depth") == settings["minimum_depth"]
                and isinstance(roots, list) and len(roots) == 2
                and all(isinstance(root, dict) for root in roots)
                and all(isinstance(root.get("uci"), str) and isinstance(root.get("cp"), int)
                        and isinstance(root.get("depth"), int) and root["depth"] >= settings["minimum_depth"]
                        and root.get("bounded") is False for root in roots)
                and roots[0].get("uci") != roots[1].get("uci")
                )


def _valid_quiet_probe(board, move, probe, forced):
    """Validate the compact, hash-cleared shallow proof before reusing it."""
    roots = probe.get("roots") if isinstance(probe, dict) else None
    if (not isinstance(roots, list) or len(roots) != 2 or probe.get("valid") is not True
            or not isinstance(probe.get("depth"), int) or probe["depth"] < 4
            or probe.get("bounded") is not False):
        return False
    if any(not isinstance(root, dict) or not isinstance(root.get("uci"), str)
           or not isinstance(root.get("cp"), int) or not isinstance(root.get("depth"), int)
           or root["depth"] < 4
           or root.get("bounded") is not False for root in roots):
        return False
    try:
        if any(chess.Move.from_uci(root["uci"]) not in board.legal_moves for root in roots):
            return False
    except ValueError:
        return False
    changed = roots[0]["uci"] != move.uci()
    if (roots[0]["uci"] == roots[1]["uci"] or probe.get("root_changed") is not changed
            or probe.get("shallow_cp") != roots[0]["cp"]
            or not isinstance(probe.get("shallow_chance"), (int, float))):
        return False
    if not changed:
        return forced is None
    return bool(isinstance(forced, dict) and forced.get("uci") == move.uci()
                and isinstance(forced.get("cp"), int) and isinstance(forced.get("depth"), int)
                and forced["depth"] >= 4
                and forced.get("bounded") is False and forced.get("hash_cleared") is True
                and isinstance(forced.get("chance"), (int, float)))


def classify_exceptional(board: chess.Board, move: chess.Move, engine, audit=None) -> dict | None:
    if engine is None or not getattr(engine, "engine", None):
        return None
    legal_count = board.legal_moves.count()
    if legal_count < 2:
        if audit is not None and legal_count == 1:
            forced = next(iter(board.legal_moves))
            audit.update(best_move_uci=forced.uci(), best_move_san=board.san(forced), best_move_depth=0, forced_choice=True)
        return None
    if move not in board.legal_moves:
        return None
    native = engine.engine
    sacrifice = sacrifice_cost(board, move)
    verification = {"schema_version": VERIFICATION_SCHEMA_VERSION, "policy_version": POLICY_VERSION,
                    "search_profile": _search_profile(), "played_uci": move.uci(),
                    "position_key": _position_key(board), "sacrifice_cp": sacrifice,
                    "passes": [], "discovery": None, "forced_shallow": None, "complete": False}
    if audit is not None:
        audit["verification"] = verification
    try:
        quiet_eligible = _new_quiet_context(board, move)
        cold_capable = hasattr(native, "analysis") and "Clear Hash" in getattr(native, "options", {})
        probe, forced_shallow = _cold_shallow_probe(native, board, move) if quiet_eligible and cold_capable else (None, None)
        if probe is not None:
            verification["quiet_probe"] = probe
            verification["discovery"] = {"shallow_depth": 4, "shallow_root_uci": probe["roots"][0]["uci"] if probe.get("roots") else None,
                                          "shallow_cp": probe.get("shallow_cp"), "shallow_chance": probe.get("shallow_chance"),
                                          "root_changed": probe.get("root_changed")}
        if forced_shallow is not None:
            verification["forced_shallow"] = forced_shallow
        discovery_frames = {}
        for settings in PROFILE["passes"]:
            lines, frames = _search(native, board, settings)
            if frames:
                discovery_frames.update(frames)
            if isinstance(lines, dict):
                lines = [lines]
            roots = [_score_record(line, board) for line in lines[:2]]
            roots = [root for root in roots if root is not None]
            pass_record = {"target_depth": settings["depth"], "minimum_depth": settings["minimum_depth"], "roots": roots}
            verification["passes"].append(pass_record)
            if audit is not None and lines and lines[0].get("pv") and lines[0].get("depth", 0) >= 8:
                preference = lines[0]["pv"][0]
                if preference in board.legal_moves:
                    audit.update(best_move_uci=preference.uci(), best_move_san=board.san(preference), best_move_depth=lines[0]["depth"])
            if not _valid_single_pass(pass_record, settings):
                return None
            top_is_played = roots[0]["uci"] == move.uci()
            if len(verification["passes"]) == 1 and not top_is_played and (sacrifice is None or sacrifice < PROFILE["sacrifice_min_cp"]):
                verification["definitive_rejection"] = "played_not_top_no_offer"
                return None
            if len(verification["passes"]) == 1 and top_is_played and not quiet_eligible:
                best_chance, second_chance = _chance(chess.engine.Cp(roots[0]["cp"])), _chance(chess.engine.Cp(roots[1]["cp"]))
                if (best_chance < PROFILE["minimum_chance"]
                        or second_chance >= PROFILE["alternative_winning_chance"]
                        or all(abs(value - .5) <= .02 for value in (best_chance, second_chance))
                        or (sacrifice is None or sacrifice < PROFILE["sacrifice_min_cp"])
                        and (best_chance - second_chance) * 100 < PROFILE["critical_gap_pp"]):
                    verification["definitive_rejection"] = "noneligible_first_pass_no_route"
                    return None
            if not top_is_played and roots[1]["uci"] != move.uci() and sacrifice is not None and sacrifice >= PROFILE["sacrifice_min_cp"]:
                forced = _normalise_single(native.analyse(
                    board, chess.engine.Limit(depth=settings["depth"], time=settings["seconds"]), root_moves=[move])) or {}
                score = _score_record(forced, board)
                if score and score["uci"] == move.uci():
                    pass_record["played"] = score
            elif roots[1]["uci"] == move.uci():
                pass_record["played"] = roots[1]
            else:
                pass_record["played"] = roots[0]

        verification["complete"] = True
        passes_top = all(item["roots"][0]["uci"] == move.uci() for item in verification["passes"])
        gaps = [(_chance(chess.engine.Cp(item["roots"][0]["cp"]))
                 - _chance(chess.engine.Cp(item["roots"][1]["cp"]))) * 100
                for item in verification["passes"]]
        old_discovery_candidate = passes_top and any(gap >= PROFILE["discovery"]["minimum_gap_pp"] for gap in gaps)
        late_choice_seed = bool(quiet_eligible and probe and forced_shallow and probe.get("valid")
                                and probe.get("root_changed")
                                and probe.get("shallow_cp") - forced_shallow.get("cp", 100000)
                                >= PROFILE["quiet_great"]["late_choice_shallow_cp"]
                                and not forced_shallow.get("bounded") and forced_shallow.get("depth", 0) >= 4)
        if cold_capable and passes_top and (old_discovery_candidate or late_choice_seed):
            native.configure({"Clear Hash": None})
            _, frames = _search(native, board, PROFILE["passes"][0], trace=True)
            verification["discovery_trace_complete"] = bool(frames)
            traced = discovery_evidence(frames, move)
            if traced:
                verification["discovery"] = traced
        elif discovery_frames and not (verification.get("discovery") or {}).get("final_run_depths"):
            traced = discovery_evidence(discovery_frames, move)
            if traced:
                verification["discovery"] = traced
        if not passes_top:
            # A positive sacrifice route still needs a played score; this is
            # retained above for lines outside MultiPV-2.
            for item in verification["passes"]:
                if item["roots"][0]["uci"] != move.uci() and item.get("played") is None:
                    verification["complete"] = False
        definitive, result = classify_cached(board, move, verification)
        if not definitive:
            verification["complete"] = False
            result = _grade_verified(board, move, verification)
        if result is None and audit is not None and not verification.get("rejection"):
            audit["rejection"] = "No exceptional route passed verified evidence"
        return result
    except (chess.engine.EngineError, chess.engine.EngineTerminatedError, KeyError, TypeError, ValueError,
            AttributeError, TimeoutError, OSError):
        if audit is not None:
            audit.setdefault("rejection", "Search failed or timed out")
        verification["complete"] = False
        return None
