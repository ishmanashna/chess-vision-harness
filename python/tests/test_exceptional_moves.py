from types import SimpleNamespace

import chess
import chess.engine
import pytest

from chess_harness.exceptional_moves import classify_exceptional, sacrifice_cost, routine_check_evasion


def test_routine_check_block_needs_difficulty_evidence_beyond_a_unique_best_move():
    board = chess.Board("rnb1k1nr/p1p1q1pp/3b4/1p6/2B5/5N2/PPPP1PPP/RNBQK2R w KQkq - 2 7")
    assert board.is_check()
    evidence = {"sacrifice_cp":0,"discovery":{"root_changed":False,"discovered_depth":1,"stable_through_depth":18},
                "passes":[{"best_chance":.74,"second_chance":.23,"discovery_gain_pp":-2}] * 2}
    assert routine_check_evasion(board, evidence)
    # A genuinely deeper tactical refinement or verified material offer remains eligible.
    evidence["passes"] = [{"best_chance":.74,"second_chance":.23,"discovery_gain_pp":8}] * 2
    assert not routine_check_evasion(board, evidence)
    evidence["discovery"] = None
    evidence["sacrifice_cp"] = 300
    assert not routine_check_evasion(board, evidence)


class Engine:
    def __init__(self, move, best=50, second=-100, depths=(18,22), unstable=False):
        self.engine = self
        self.move, self.best, self.second = move, best, second
        self.depths, self.unstable, self.calls = depths, unstable, 0

    def analyse(self, board, limit, multipv):
        assert multipv == 2 and limit.time <= 1.0
        depth = self.depths[min(self.calls, len(self.depths) - 1)]
        alternate = next(move for move in board.legal_moves if move != self.move)
        top = alternate if self.unstable and self.calls else self.move
        self.calls += 1
        return [{"pv":[top],"score":chess.engine.PovScore(chess.engine.Cp(self.best),board.turn),"depth":depth},
                {"pv":[alternate],"score":chess.engine.PovScore(chess.engine.Cp(self.second),board.turn),"depth":depth}]


def test_only_good_move_earns_great_with_stable_deeper_evidence():
    board = chess.Board()
    move = chess.Move.from_uci("e2e4")
    engine = Engine(move)
    result = classify_exceptional(board, move, engine)
    assert result["label"] == "great" and engine.calls == 2
    assert [item["depth"] for item in result["evidence"]["passes"]] == [18,22]
    assert '"pv"' not in str(result) and "e2e4" not in str(result)


def test_sound_piece_offer_earns_brilliant_and_exchange_is_not_a_sacrifice():
    board = chess.Board("6k1/8/8/3p4/8/4Q3/8/6K1 w - - 0 1")
    move = chess.Move.from_uci("e3e4")
    assert sacrifice_cost(board, move) == 900
    result = classify_exceptional(board, move, Engine(move, best=50,second=40))
    assert result["label"] == "brilliant" and result["evidence"]["sacrifice_cp"] == 900
    traded = chess.Board("6k1/8/2p5/3b4/5N2/8/8/6K1 w - - 0 1")
    assert sacrifice_cost(traded,chess.Move.from_uci("f4d5")) == 0


@pytest.mark.parametrize("options", [dict(best=-650,second=-900), dict(best=900,second=600),
                                  dict(best=50,second=40), dict(depths=(13,13,17)),
                                  dict(depths=(18,17)), dict(unstable=True)])
def test_no_positive_symbol_for_losing_easy_shallow_or_unstable_choices(options):
    move = chess.Move.from_uci("e2e4")
    assert classify_exceptional(chess.Board(),move,Engine(move,**options)) is None


def test_pawn_offer_is_not_a_brilliant_piece_sacrifice():
    board = chess.Board()
    assert sacrifice_cost(board,chess.Move.from_uci("e2e4")) == 0


def test_pinned_capture_does_not_count_as_an_available_piece_sacrifice():
    board = chess.Board("4k3/4r3/8/2Q5/8/8/8/4R1K1 w - - 0 1")
    assert board.is_valid()
    assert sacrifice_cost(board,chess.Move.from_uci("c5c7")) == 0


def test_forced_legal_move_and_engine_timeouts_are_not_exceptional():
    forced = SimpleNamespace(legal_moves=SimpleNamespace(count=lambda:1))
    assert classify_exceptional(forced,chess.Move.from_uci("e2e4"),Engine(chess.Move.from_uci("e2e4"))) is None
    class Broken:
        def analyse(self,*args,**kwargs): raise TimeoutError()
    assert classify_exceptional(chess.Board(),chess.Move.from_uci("e2e4"),SimpleNamespace(engine=Broken())) is None


def test_black_uses_mover_relative_engine_scores():
    board = chess.Board()
    board.push_uci("e2e4")
    move = chess.Move.from_uci("e7e5")
    assert classify_exceptional(board,move,Engine(move))["label"] == "great"


def test_exceptional_searches_run_after_quality_and_do_not_change_its_values(monkeypatch):
    from chess_harness import game_quality, exceptional_moves
    calls = []
    class QualityEngine:
        def __init__(self): self.engine = SimpleNamespace(id={},options={})
        def evaluate(self, board, depth):
            calls.append("quality")
            self.last_evaluation = {"mate":None}
            return 0
        def quit(self): pass
    monkeypatch.setattr(game_quality,"EvalEngineAdapter",QualityEngine)
    def exceptional(board,move,engine,audit=None):
        assert calls.count("quality") == 4
        calls.append("exceptional")
        return {"label":"great", "evidence":{"version":"fixture"}}
    monkeypatch.setattr(exceptional_moves,"classify_exceptional",exceptional)
    normal = game_quality.analyse_game(["e2e4","e7e5"])
    assert calls == ["quality"] * 4
    calls.clear()
    annotated = game_quality.analyse_game(["e2e4","e7e5"],include_exceptional=True)
    assert calls == ["quality"] * 4 + ["exceptional"] * 2
    assert normal.white == annotated.white and normal.black == annotated.black
    assert annotated.move_analysis["profile"]["label_version"].endswith("v8")


def test_nearly_best_sound_sacrifice_can_be_brilliant():
    board = chess.Board("6k1/8/8/3p4/8/4Q3/8/6K1 w - - 0 1")
    move = chess.Move.from_uci("e3e4")
    class NearlyBest(Engine):
        def analyse(self, board, limit, multipv):
            lines = super().analyse(board, limit, multipv)
            lines[0]["pv"], lines[1]["pv"] = lines[1]["pv"], lines[0]["pv"]
            return lines
    result = classify_exceptional(board,move,NearlyBest(move,best=50,second=40))
    assert result["label"] == "brilliant"
    assert all(p["played_chance"] < p["best_chance"] for p in result["evidence"]["passes"])
    assert classify_exceptional(board,move,NearlyBest(move,best=50,second=-100)) is None


def test_late_stable_quiet_discovery_can_be_brilliant_without_sacrifice(monkeypatch):
    from chess_harness import exceptional_moves as module
    board = chess.Board()
    move = chess.Move.from_uci("e2e4")
    alternate = chess.Move.from_uci("d2d4")
    frames = {depth:{"move":alternate if depth<14 else move,"chance":.30 if depth<14 else .55} for depth in range(1,19)}
    def search(engine, board, settings, trace=False):
        lines = engine.analyse(board,chess.engine.Limit(time=.2),multipv=2)
        return lines, frames if engine.calls == 1 else {}
    monkeypatch.setattr(module,"_search",search)
    result = classify_exceptional(board,move,Engine(move))
    assert sacrifice_cost(board,move) == 0
    assert result["label"] == "brilliant"
    assert result["evidence"]["discovery"]["discovered_depth"] == 14
    # Value refinement may be hidden even when the root was already preferred.
    frames[4]["move"] = move
    assert classify_exceptional(board,move,Engine(move))["label"] == "brilliant"
    frames[4]["move"] = alternate
    frames[4]["chance"] = .55
    assert classify_exceptional(board,move,Engine(move))["label"] == "great"


def test_discovery_requires_consecutive_stability_and_a_recorded_shallow_search():
    from chess_harness.exceptional_moves import discovery_evidence
    move = chess.Move.from_uci("e2e4")
    other = chess.Move.from_uci("d2d4")
    assert discovery_evidence({4:{"move":other,"chance":.3},18:{"move":move,"chance":.6}},move) is None
    assert discovery_evidence({14:{"move":move,"chance":.6},15:{"move":move,"chance":.6},16:{"move":move,"chance":.6}},move) is None


def test_taking_a_hung_knight_is_not_great_merely_because_quiet_moves_are_worse():
    board = chess.Board("6k1/8/8/3p4/4N3/8/8/6K1 b - - 0 1")
    move = chess.Move.from_uci("d5e4")
    assert classify_exceptional(board,move,Engine(move,best=450,second=0)) is None


def test_critical_quiet_defense_can_be_great_while_somewhat_worse():
    move = chess.Move.from_uci("e2e4")
    assert classify_exceptional(chess.Board(),move,Engine(move,best=-150,second=-400))["label"] == "great"


def test_unnecessary_queen_offer_in_an_already_drawn_position_is_not_brilliant():
    board = chess.Board("6k1/8/8/3p4/8/4Q3/8/6K1 w - - 0 1")
    move = chess.Move.from_uci("e3e4")
    assert classify_exceptional(board,move,Engine(move,best=0,second=0)) is None


def test_useful_quiet_move_no_longer_needs_an_extreme_alternative_gap():
    move = chess.Move.from_uci("e2e4")
    # Approximately 4.5 points better: useful, without an enormous only-move gap.
    assert classify_exceptional(chess.Board(),move,Engine(move,best=50,second=0))["label"] == "great"


def test_smaller_quiet_value_refinement_can_be_brilliant(monkeypatch):
    from chess_harness import exceptional_moves as module
    move = chess.Move.from_uci("e2e4")
    frames={d:{"move":move,"chance":.48 if d<=4 else .55} for d in range(1,19)}
    def search(engine,board,settings,trace=False):
        return engine.analyse(board,chess.engine.Limit(time=.2),multipv=2),frames
    monkeypatch.setattr(module,"_search",search)
    assert classify_exceptional(chess.Board(),move,Engine(move,best=50,second=0))["label"] == "brilliant"


@pytest.mark.parametrize("best,second", [(0,0),(50,40)])
def test_ineligible_positions_do_not_spend_a_cold_difficulty_search(best,second):
    move=chess.Move.from_uci("e2e4")
    engine=Engine(move,best=best,second=second)
    engine.options={"Clear Hash":None}
    engine.analysis=None
    engine.configure=lambda *args,**kwargs: pytest.fail("no hash reset needed")
    audit={}
    assert classify_exceptional(chess.Board(),move,engine,audit=audit) is None
    assert engine.calls==1
    assert audit["best_move_uci"]==move.uci()


def _stream_line(board, move, depth, cp, *, multipv=1, bounded=False):
    line = {"multipv": multipv, "depth": depth,
            "score": chess.engine.PovScore(chess.engine.Cp(cp), board.turn), "pv": [move]}
    if bounded:
        line["upperbound"] = True
    return line


class StreamingEngine:
    def __init__(self, batches):
        from contextlib import contextmanager
        self.engine = self
        self.options = {}
        self.batches = list(batches)
        self.requests = []

        @contextmanager
        def analysis(board, limit, multipv):
            self.requests.append((limit.depth, limit.time, multipv))
            yield iter(self.batches.pop(0))
        self.analysis = analysis


def test_streaming_search_uses_deepest_complete_unbounded_multipv_pair():
    from chess_harness.exceptional_moves import _search, _valid_single_pass, PROFILE
    board = chess.Board()
    move = chess.Move.from_uci("e2e4")
    other = chess.Move.from_uci("d2d4")
    engine = StreamingEngine([[
        _stream_line(board, move, 13, 10), _stream_line(board, other, 13, 0, multipv=2),
        _stream_line(board, move, 14, 20), _stream_line(board, other, 14, 0, multipv=2),
        _stream_line(board, move, 15, 30, bounded=True),
        _stream_line(board, other, 15, -10, multipv=2),
    ]])
    lines, _ = _search(engine, board, PROFILE["passes"][0])
    assert [line["depth"] for line in lines] == [14, 14]
    assert _valid_single_pass({"target_depth": 18, "minimum_depth": 14,
                               "roots": [
                                   {"uci": line["pv"][0].uci(), "cp": line["score"].pov(board.turn).score(),
                                    "depth": line["depth"], "bounded": False}
                                   for line in lines]}, PROFILE["passes"][0])
    assert len(engine.requests) == 1


def test_prior_complete_shallow_iteration_triggers_bounded_retry_then_recovers():
    board = chess.Board()
    move = chess.Move.from_uci("e2e4")
    other = chess.Move.from_uci("d2d4")
    batches = [
        [_stream_line(board, move, 13, 50), _stream_line(board, other, 13, -100, multipv=2),
         _stream_line(board, move, 15, 60, bounded=True),
         _stream_line(board, other, 15, -80, multipv=2)],
        [_stream_line(board, move, 18, 50), _stream_line(board, other, 18, -100, multipv=2)],
        [_stream_line(board, move, 22, 50), _stream_line(board, other, 22, -100, multipv=2)],
    ]
    engine = StreamingEngine(batches)
    audit = {}
    result = classify_exceptional(board, move, engine, audit=audit)
    assert result and result["label"] == "great"
    verification = audit["verification"]
    assert [p["roots"][0]["depth"] for p in verification["passes"]] == [18, 22]
    assert verification["passes"][0]["retry_attempts"] == [{"seconds": .35}]
    assert [attempt["valid"] for attempt in verification["passes"][0]["search_attempts"]] == [False, True]
    assert verification["passes"][1]["retry_attempts"] == []
    assert engine.requests == [(18, .35, 2), (18, .35, 2), (22, 1.0, 2)]


def test_second_pass_uses_its_own_half_second_retry_budget():
    board = chess.Board()
    move = chess.Move.from_uci("e2e4")
    other = chess.Move.from_uci("d2d4")
    engine = StreamingEngine([
        [_stream_line(board, move, 18, 50), _stream_line(board, other, 18, -100, multipv=2)],
        [_stream_line(board, move, 17, 50), _stream_line(board, other, 17, -100, multipv=2),
         _stream_line(board, move, 22, 60, bounded=True),
         _stream_line(board, other, 22, -80, multipv=2)],
        [_stream_line(board, move, 22, 50), _stream_line(board, other, 22, -100, multipv=2)],
    ])
    audit = {}
    result = classify_exceptional(board, move, engine, audit=audit)
    assert result and result["label"] == "great"
    assert audit["verification"]["passes"][1]["retry_attempts"] == [{"seconds": .5}]
    assert engine.requests == [(18, .35, 2), (22, 1.0, 2), (22, .5, 2)]


def test_bounded_retry_that_still_has_no_valid_pair_fails_closed():
    board = chess.Board()
    move = chess.Move.from_uci("e2e4")
    other = chess.Move.from_uci("d2d4")
    engine = StreamingEngine([
        [_stream_line(board, move, 13, 50), _stream_line(board, other, 13, -100, multipv=2)],
        [_stream_line(board, move, 18, 50, bounded=True),
         _stream_line(board, other, 18, -100, multipv=2)],
    ])
    audit = {}
    assert classify_exceptional(board, move, engine, audit=audit) is None
    verification = audit["verification"]
    assert verification["complete"] is False
    assert verification["passes"][0]["retry_attempts"] == [{"seconds": .35}]
    assert len(engine.requests) == 2


def _quiet_late_position():
    board = chess.Board()
    for uci in ("e2e4", "e7e5", "g1f3", "b8c6", "f1c4", "g8f6", "d2d3", "f8c5"):
        board.push_uci(uci)
    return board, chess.Move.from_uci("h2h3")


def _cached_verification(board, move, best_cp, second_cp, *, shallow_cp=None, played_cp=None):
    from chess_harness import exceptional_moves as module
    verification = {"schema_version": module.VERIFICATION_SCHEMA_VERSION,
                    "policy_version": module.POLICY_VERSION,
                    "search_profile": module._search_profile(), "played_uci": move.uci(),
                    "position_key": module._position_key(board), "sacrifice_cp": 0,
                    "passes": [], "complete": True}
    for settings in module.PROFILE["passes"]:
        verification["passes"].append({
            "target_depth": settings["depth"], "minimum_depth": settings["minimum_depth"],
            "roots": [{"uci": move.uci(), "cp": best_cp, "depth": settings["minimum_depth"], "bounded": False},
                      {"uci": "a2a3", "cp": second_cp, "depth": settings["minimum_depth"], "bounded": False}],
            "played": {"uci": move.uci(), "cp": played_cp if played_cp is not None else best_cp,
                       "depth": settings["minimum_depth"], "bounded": False}})
    if shallow_cp is not None:
        verification.update({
            "quiet_probe": {"valid": True, "root_changed": True, "depth": 4, "shallow_cp": 0,
                            "shallow_chance": .5, "bounded": False,
                            "roots": [{"uci": "a2a3", "cp": 0, "depth": 4, "bounded": False},
                                      {"uci": move.uci(), "cp": shallow_cp, "depth": 4, "bounded": False}]},
            "forced_shallow": {"uci": move.uci(), "cp": shallow_cp, "chance": .48,
                               "depth": 4, "bounded": False, "hash_cleared": True},
            "discovery_trace_complete": True,
            "discovery": {"shallow_depth": 4, "shallow_cp": 0,
                          "shallow_chance": .5, "root_changed": True,
                          "discovered_depth": 5, "final_run_start_depth": 5,
                          "stable_through_depth": 7, "final_run_depths": 3,
                          "shallow_root_uci": "a2a3"}})
    return verification


def test_quiet_critical_gap_uses_both_chance_and_cp_thresholds():
    from chess_harness.exceptional_moves import classify_cached
    board, move = _quiet_late_position()
    # Eight raw centipawns around equality clear 0.5 percentage points while
    # avoiding the older large-gap route.
    verification = _cached_verification(board, move, 0, -8)
    definitive, result = classify_cached(board, move, verification)
    assert definitive and result["label"] == "great"
    assert result["evidence"]["route"] == "quiet_critical_gap"
    assert all(row["raw_cp_gap"] == 8 for row in result["evidence"]["passes"])

    assert classify_cached(board, move, _cached_verification(board, move, 0, -7))[1] is None
    # Far from equality, eight cp is too small to establish the chance gap.
    assert classify_cached(board, move, _cached_verification(board, move, 700, 692))[1] is None


def test_late_choice_has_independent_shallow_proof_without_global_gain():
    from chess_harness.exceptional_moves import classify_cached
    board, move = _quiet_late_position()
    verification = _cached_verification(board, move, -5, -5, shallow_cp=-20, played_cp=-5)
    verification["discovery"].update({"shallow_cp": 0, "shallow_chance": .5})
    # Cold depth four preferred a different move at 0 cp; forced h3 was -20.
    verification["quiet_probe"].update({"shallow_cp": 0})
    definitive, result = classify_cached(board, move, verification)
    assert definitive and result["label"] == "great"
    assert result["evidence"]["route"] == "quiet_late_choice"
    assert all(row["deep_gain_cp"] == 15 for row in result["evidence"]["passes"])
    # Both deeper choices remain equal at -5 cp, so the label comes from the
    # documented cold shallow-choice evidence rather than global gain.


def test_late_choice_fresh_and_cached_grading_are_equivalent(monkeypatch):
    from chess_harness import exceptional_moves as module
    board, move = _quiet_late_position()
    alternate = chess.Move.from_uci("a2a3")

    class QuietEngine:
        def __init__(self):
            self.engine = self
            self.options = {"Clear Hash": None}
            self.analysis = object()

        def configure(self, options):
            assert options == {"Clear Hash": None}

        def analyse(self, board, limit, multipv=None, root_moves=None):
            if root_moves:
                root = root_moves[0]
                return {"pv": [root], "score": chess.engine.PovScore(chess.engine.Cp(-20), board.turn),
                        "depth": 4}
            assert limit.depth == 4 and multipv == 2
            return [{"pv": [alternate], "score": chess.engine.PovScore(chess.engine.Cp(0), board.turn), "depth": 4},
                    {"pv": [move], "score": chess.engine.PovScore(chess.engine.Cp(-20), board.turn), "depth": 4}]

    def search(engine, position, settings, trace=False):
        if trace:
            frames = {4: {"move": alternate, "cp": 0, "chance": .5},
                      5: {"move": move, "cp": -5, "chance": .495},
                      6: {"move": move, "cp": -5, "chance": .495},
                      7: {"move": move, "cp": -5, "chance": .495}}
            return [], frames
        depth = settings["depth"]
        lines = [{"pv": [move], "score": chess.engine.PovScore(chess.engine.Cp(-5), position.turn), "depth": depth},
                 {"pv": [alternate], "score": chess.engine.PovScore(chess.engine.Cp(-5), position.turn), "depth": depth}]
        return lines, {}

    monkeypatch.setattr(module, "_search", search)
    audit = {}
    fresh = classify_exceptional(board, move, QuietEngine(), audit=audit)
    definitive, cached = module.classify_cached(board, move, audit["verification"])
    assert definitive and fresh == cached, (audit, fresh, cached)
    assert fresh["evidence"]["route"] == "quiet_late_choice"


def test_shallow_equal_root_tie_does_not_claim_late_choice():
    from chess_harness.exceptional_moves import classify_cached
    board, move = _quiet_late_position()
    verification = _cached_verification(board, move, -5, -5, shallow_cp=-5, played_cp=-5)
    verification["quiet_probe"].update({"shallow_cp": -5, "roots": [
        {"uci": "a2a3", "cp": -5, "depth": 4, "bounded": False},
        {"uci": move.uci(), "cp": -5, "depth": 4, "bounded": False}]})
    verification["discovery"].update({"shallow_cp": -5})
    definitive, result = classify_cached(board, move, verification)
    assert definitive and result is None


def test_late_choice_requires_final_contiguous_stability_and_matching_cache_identity():
    from chess_harness.exceptional_moves import classify_cached
    board, move = _quiet_late_position()
    verification = _cached_verification(board, move, -5, -5, shallow_cp=-20, played_cp=-5)
    verification["discovery"].update({"final_run_depths": 2})
    assert classify_cached(board, move, verification) == (True, None)

    verification["discovery"]["final_run_depths"] = 3
    stale = dict(verification, position_key="not-the-position")
    assert classify_cached(board, move, stale) == (False, None)
    stale = dict(verification, search_profile={"depth": 1})
    assert classify_cached(board, move, stale) == (False, None)


def test_discovery_records_final_run_start_for_auditable_regrading():
    from chess_harness.exceptional_moves import discovery_evidence
    move = chess.Move.from_uci("h2h3")
    other = chess.Move.from_uci("a2a3")
    frames = {4: {"move": other, "cp": 0, "chance": .5},
              5: {"move": move, "cp": -5, "chance": .495},
              6: {"move": move, "cp": -5, "chance": .495},
              7: {"move": move, "cp": -5, "chance": .495}}
    evidence = discovery_evidence(frames, move)
    assert evidence["final_run_start_depth"] == evidence["discovered_depth"] == 5
    assert evidence["final_run_depths"] == 3 and evidence["shallow_cp"] == 0


def test_public_evidence_version_remains_compatible_with_running_server():
    from chess_harness.exceptional_moves import VERSION
    assert VERSION == "critical-sound-sacrifice-v1"


def test_complete_cached_proof_can_be_regraded_after_policy_revision():
    from chess_harness import exceptional_moves as module
    board, move = _quiet_late_position()
    verification = _cached_verification(board, move, 0, -8)
    verification["policy_version"] = module.PREVIOUS_POLICY_VERSION
    verification["search_profile"].pop("retry_budget")
    definitive, result = module.classify_cached(board, move, verification)
    assert definitive and result["label"] == "great"
    assert result["evidence"]["policy_version"] == module.POLICY_VERSION


def test_incomplete_cached_rejections_require_current_policy_and_valid_reason():
    from chess_harness import exceptional_moves as module
    board, move = _quiet_late_position()
    stale = _cached_verification(board, move, 0, -100)
    stale["passes"] = stale["passes"][:1]
    stale["complete"] = False
    stale["definitive_rejection"] = "noneligible_first_pass_no_route"
    stale["policy_version"] = "critical-discovery-sacrifice-policy-v6"
    assert module.classify_cached(board, move, stale) == (False, None)

    inconsistent = _cached_verification(board, move, 0, -100)
    inconsistent["passes"] = inconsistent["passes"][:1]
    inconsistent["complete"] = False
    inconsistent["definitive_rejection"] = "played_not_top_no_offer"
    assert module.classify_cached(board, move, inconsistent) == (False, None)


def test_v7_incomplete_negative_proofs_are_reused_only_for_supported_reasons():
    from chess_harness import exceptional_moves as module
    board, move = _quiet_late_position()
    not_top = _cached_verification(board, move, 0, -100)
    not_top["passes"] = not_top["passes"][:1]
    not_top["complete"] = False
    not_top["policy_version"] = module.PREVIOUS_POLICY_VERSION
    not_top["search_profile"].pop("retry_budget")
    not_top["definitive_rejection"] = "played_not_top_no_offer"
    not_top["passes"][0]["roots"][0]["uci"] = "a2a3"
    not_top["passes"][0]["roots"][1]["uci"] = "b2b3"
    assert module.classify_cached(board, move, not_top) == (True, None)

    forged = _cached_verification(board, move, 0, -100)
    forged["passes"] = forged["passes"][:1]
    forged["complete"] = False
    forged["policy_version"] = module.PREVIOUS_POLICY_VERSION
    forged["search_profile"].pop("retry_budget")
    forged["definitive_rejection"] = "played_not_top_no_offer"
    assert module.classify_cached(board, move, forged) == (False, None)

    no_route = _cached_verification(board, move, 0, -100)
    no_route["passes"] = no_route["passes"][:1]
    no_route["complete"] = False
    no_route["policy_version"] = module.PREVIOUS_POLICY_VERSION
    no_route["search_profile"].pop("retry_budget")
    no_route["definitive_rejection"] = "noneligible_first_pass_no_route"
    assert module.classify_cached(board, move, no_route) == (True, None)


def test_new_quiet_routes_do_not_award_hopeless_moves():
    from chess_harness.exceptional_moves import classify_cached
    board, move = _quiet_late_position()
    # At this score difference the chance gap clears 0.5pp, but the top move
    # itself remains below the minimum chance for an exceptional label.
    route_a = _cached_verification(board, move, -540, -555)
    assert classify_cached(board, move, route_a)[1] is None

    route_b = _cached_verification(board, move, -600, -600, shallow_cp=-620, played_cp=-600)
    route_b["quiet_probe"].update({
        "shallow_cp": -1000, "roots": [
            {"uci": "a2a3", "cp": -1000, "depth": 4, "bounded": False},
            {"uci": move.uci(), "cp": -1001, "depth": 4, "bounded": False}]})
    route_b["forced_shallow"]["cp"] = -620
    route_b["discovery"].update({"shallow_cp": -1000, "shallow_chance": .024})
    assert classify_cached(board, move, route_b)[1] is None


def test_late_choice_does_not_reward_near_equal_forced_mates():
    from chess_harness.exceptional_moves import classify_cached
    board, move = _quiet_late_position()
    # Both deep lines are forced mates with only a three-cp Stockfish
    # distance. The sigmoid clips both to a win, so this is routine conversion.
    routine_mate = _cached_verification(board, move, 9994, 9991,
                                        shallow_cp=960, played_cp=9994)
    routine_mate["discovery"].update({"shallow_cp": 961, "shallow_chance": .97176})
    assert classify_cached(board, move, routine_mate) == (True, None)


def test_late_choice_keeps_a_materially_faster_forced_mate():
    from chess_harness.exceptional_moves import classify_cached
    board, move = _quiet_late_position()
    # A seven-cp mate-score separation can represent a materially shorter mate
    # (for example mate in five versus mate in twelve), and remains eligible.
    faster_mate = _cached_verification(board, move, 9995, 9988,
                                       shallow_cp=1000, played_cp=9995)
    faster_mate["discovery"].update({"shallow_cp": 1500})
    faster_mate["quiet_probe"].update({"shallow_cp": 1500, "roots": [
        {"uci": "a2a3", "cp": 1500, "depth": 4, "bounded": False},
        {"uci": move.uci(), "cp": 1000, "depth": 4, "bounded": False}]})
    definitive, result = classify_cached(board, move, faster_mate)
    assert definitive and result["label"] == "great"
    assert result["evidence"]["route"] == "quiet_late_choice"
