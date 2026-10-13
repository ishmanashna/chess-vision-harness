"""Conservative engine-verified ! / !! detection; candidate lines stay private.

Concepts: Chess.com's published Great/Brilliant definitions. Exact thresholds below
are this benchmark's own fixed policy, never adjusted by an agent's mapped rating.
"""
from __future__ import annotations

import math

import chess
import chess.engine

VERSION = "critical-sound-sacrifice-v1"
# VERSION identifies the evidence structure; policy revisions are separate.
POLICY_VERSION = "critical-discovery-sacrifice-policy-v6"
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
                frames[info["depth"]] = {"move": info["pv"][0], "chance": _chance(info["score"].pov(board.turn))}
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
    return {"shallow_depth": settings["shallow_depth"], "discovered_depth": start,
            "stable_through_depth": end, "shallow_chance": round(shallow["chance"], 5),
            "root_changed": shallow["move"] != move}


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


def classify_exceptional(board: chess.Board, move: chess.Move, engine, audit=None) -> dict | None:
    if engine is None or not getattr(engine, "engine", None):
        return None
    if board.legal_moves.count() < 2:
        if audit is not None and board.legal_moves.count() == 1:
            forced = next(iter(board.legal_moves))
            audit.update(best_move_uci=forced.uci(),best_move_san=board.san(forced),best_move_depth=0,forced_choice=True)
        return None
    evidence = []
    sacrifice = sacrifice_cost(board, move)
    try:
        native = engine.engine
        cold_trace = hasattr(native, "analysis") and "Clear Hash" in getattr(native, "options", {})
        discovery = None
        for settings in PROFILE["passes"]:
            lines, frames = _search(native, board, settings)
            if audit is not None and lines and lines[0].get("pv") and lines[0].get("depth", 0) >= 8:
                preference = lines[0]["pv"][0]
                if preference in board.legal_moves:
                    audit.update(best_move_uci=preference.uci(), best_move_san=board.san(preference), best_move_depth=lines[0]["depth"])
            if frames:
                discovery = discovery_evidence(frames, move)
            if len(lines) < 2 or any(line.get("depth", 0) < settings["minimum_depth"] or not line.get("pv") or line.get("upperbound") or line.get("lowerbound") for line in lines[:2]):
                return None
            if lines[0]["pv"][0] == lines[1]["pv"][0]:
                return None
            best, second = [_chance(line["score"].pov(board.turn)) for line in lines[:2]]
            verified_depth = min(line["depth"] for line in lines[:2])
            played_is_best = lines[0]["pv"][0] == move
            played = best
            alternative = second
            # These outcomes cannot qualify regardless of a cold difficulty trace.
            # Preserve the preferred-move audit, but avoid redundant engine work.
            if played_is_best and (
                best < PROFILE["minimum_chance"]
                or second >= PROFILE["alternative_winning_chance"]
                or all(abs(chance - .5) <= .02 for chance in (best, second))
                or ((sacrifice is None or sacrifice < PROFILE["sacrifice_min_cp"])
                    and (best - second) * 100 < min(PROFILE["critical_gap_pp"], PROFILE["discovery"]["minimum_gap_pp"]))
            ):
                return None
            if cold_trace and not evidence and played_is_best:
                # Verification can reuse adjacent-position work; human-difficulty
                # evidence must come from a separate cold iterative search.
                native.configure({"Clear Hash": None})
                _, cold_frames = _search(native, board, settings, trace=True)
                discovery = discovery_evidence(cold_frames, move)
            if not played_is_best:
                if sacrifice is None or sacrifice < PROFILE["sacrifice_min_cp"]:
                    return None
                if lines[1]["pv"][0] == move:
                    played = second
                else:
                    forced = engine.engine.analyse(board, chess.engine.Limit(depth=settings["depth"], time=settings["seconds"]), root_moves=[move])
                    if forced.get("depth", 0) < settings["minimum_depth"] or forced.get("upperbound") or forced.get("lowerbound") or not forced.get("pv") or forced["pv"][0] != move:
                        return None
                    verified_depth = min(verified_depth, forced["depth"])
                    played = _chance(forced["score"].pov(board.turn))
                alternative = best
                if (best - played) * 100 > PROFILE["near_best_loss_pp"]:
                    return None
            if played < PROFILE["minimum_chance"] or alternative >= PROFILE["alternative_winning_chance"]:
                return None
            if all(abs(chance - .5) <= .02 for chance in (best, played, alternative)):
                # Discarding material in an already drawn / claimable position
                # is not brilliant merely because the engine still reports a draw.
                return None
            brilliant = played >= PROFILE["brilliant_minimum_chance"] and sacrifice is not None and sacrifice >= PROFILE["sacrifice_min_cp"]
            great = played_is_best and (best - second) * 100 >= PROFILE["critical_gap_pp"] and second < PROFILE["critical_alternative_ceiling"]
            discovery_gain = (played - discovery["shallow_chance"]) * 100 if discovery else 0
            hard = False
            if discovery and played_is_best and (best - second) * 100 >= PROFILE["discovery"]["minimum_gap_pp"]:
                hard = difficult(discovery, discovery_gain, (best - second) * 100, PROFILE["discovery"])
                brilliant = brilliant or (played >= PROFILE["brilliant_minimum_chance"] and ((discovery["root_changed"] and discovery["discovered_depth"] >= PROFILE["discovery"]["brilliant_depth"] and discovery_gain >= PROFILE["discovery"]["brilliant_gain_pp"]) or discovery_gain >= PROFILE["discovery"]["refinement_brilliant_gain_pp"]))
                great = great or hard
            # Taking a hung piece / making an ordinary recapture is not exceptional
            # just because every non-capture is worse. Require deeper tactical value.
            nonobvious_capture = discovery and discovery["root_changed"] and discovery["discovered_depth"] >= PROFILE["routine_guard"]["great_depth"] and discovery["stable_through_depth"] - discovery["discovered_depth"] + 1 >= PROFILE["routine_guard"]["stable_depths"] and difficult(discovery, discovery_gain, (best - second) * 100, PROFILE["routine_guard"])
            sound_offer = sacrifice is not None and sacrifice >= PROFILE["sacrifice_min_cp"]
            if board.is_capture(move) and not sound_offer and not nonobvious_capture:
                if audit is not None: audit["rejection"] = "routine capture without a deeper tactical discovery"
                return None
            if not brilliant and not great:
                return None
            evidence.append({"depth": verified_depth,
                             "best_chance": round(best, 4), "second_chance": round(second, 4), "played_chance": round(played, 4),
                             "discovery_gain_pp": round(discovery_gain, 4), "label": "brilliant" if brilliant else "great"})
        label = "brilliant" if all(item["label"] == "brilliant" for item in evidence) else "great"
        for item in evidence:
            item["search_label"] = item["label"]
            item["label"] = label
        saved = {"version": VERSION, "policy_version": POLICY_VERSION, "passes": evidence, "sacrifice_cp": sacrifice, "discovery": discovery}
        if routine_check_evasion(board, saved):
            if audit is not None: audit["rejection"] = "routine check evasion without deeper difficulty evidence"
            return None
        return {"label": label, "evidence": saved}
    except (chess.engine.EngineError, chess.engine.EngineTerminatedError, KeyError, TypeError, ValueError, AttributeError, TimeoutError, OSError):
        return None
