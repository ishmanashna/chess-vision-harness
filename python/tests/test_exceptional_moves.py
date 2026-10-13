from types import SimpleNamespace

import chess
import chess.engine
import pytest

from chess_harness.exceptional_moves import classify_exceptional, sacrifice_cost


class Engine:
    def __init__(self, move, best=50, second=-100, depths=(18,22), unstable=False):
        self.engine = self
        self.move, self.best, self.second = move, best, second
        self.depths, self.unstable, self.calls = depths, unstable, 0

    def analyse(self, board, limit, multipv):
        assert multipv == 2 and limit.time <= 1.0
        depth = self.depths[self.calls]
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


@pytest.mark.parametrize("options", [dict(best=-400,second=-700), dict(best=900,second=600),
                                  dict(best=50,second=40), dict(depths=(13,22)),
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
    assert annotated.move_analysis["profile"]["label_version"].endswith("v4")


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
