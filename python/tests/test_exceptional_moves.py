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
        assert multipv == 2 and limit.time <= .8
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


@pytest.mark.parametrize("options", [dict(best=-200,second=-500), dict(best=900,second=600),
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
    def exceptional(board,move,engine):
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
    assert annotated.move_analysis["profile"]["label_version"].endswith("v2")
