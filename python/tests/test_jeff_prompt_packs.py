"""Jeff A/B pack registry and council adapter smoke tests."""

from __future__ import annotations

from collections import Counter

from chess_harness.prompt_packs import (
    is_jeff_council_state,
    is_jeff_family,
    load_pack,
    pack_family,
)
from chess_harness.runner.adapters.jeff_council import JeffCouncilAdapter


def test_jeff_packs_load():
    for pid in ("ja", "jb", "jc", "jd", "ji", "j2", "je"):
        pack = load_pack(pid)
        assert pack.family == "jeff"
        assert is_jeff_family(pack)
        assert pack_family(pid) == "jeff"
    assert load_pack("j2").duplicate_board is True
    je = load_pack("je")
    assert je.kind == "jeff_council"
    assert je.seat_packs == ("jb", "jc", "jd")
    assert is_jeff_council_state({"prompt_pack_kind": "jeff_council"})
    assert not is_jeff_council_state({"prompt_pack_kind": "committee"})


def test_jeff_council_majority():
    class V:
        def __init__(self, move):
            self.move = move
            self.provider = "typesafe"

        def choose_move(self, *, board_text, board_png=None):
            return self.move

        def choose_placement(self, *, board_text, board_png=None):
            return {}

        def probe(self, *, board_text, board_png=None):
            return None

    adapter = JeffCouncilAdapter([V("e2e4"), V("e2e4"), V("d2d4")])
    assert adapter.choose_move(board_text="x") == "e2e4"
    assert Counter(adapter.last_votes)["e2e4"] == 2


def test_jeff_council_tie_breaks_seat_order():
    class V:
        def __init__(self, move):
            self.move = move
            self.provider = "typesafe"

        def choose_move(self, *, board_text, board_png=None):
            return self.move

        def choose_placement(self, *, board_text, board_png=None):
            return {}

        def probe(self, *, board_text, board_png=None):
            return None

    adapter = JeffCouncilAdapter([V("a2a3"), V("b2b3"), V("c2c3")])
    assert adapter.choose_move(board_text="x") == "a2a3"
