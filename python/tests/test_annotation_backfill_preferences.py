import json

import pytest

from chess_harness import annotation_backfill as backfill
from chess_harness.game_quality import analyse_game
from chess_harness.move_annotations import save_analysis


def _state(moves=("e2e4",)):
    return {
        "game_id": "game-reuse-preferences",
        "status": "finished",
        "end_reason": "resignation",
        "result": "0-1",
        "game_type": "agent_vs_engine",
        "model_name": "test-agent",
        "moves": list(moves),
    }


def _artifact(state):
    artifact = analyse_game(state["moves"], eval_fn=lambda board: 50).move_analysis
    artifact["profile"]["label_version"] = "win-chance-loss-exceptional-v5"
    for row in artifact["plies"]:
        row.update(loss_percent=8.0, label="inaccuracy")
        row.update(best_move_uci="d2d4", best_move_san="d4", best_move_depth=14)
    return artifact


def test_reuse_preferences_skips_only_safe_rows_and_records_scope(monkeypatch):
    state = _state(("e2e4", "e7e5"))
    artifact = _artifact(state)
    artifact["plies"][1].update(best_move_uci="e7e5", best_move_san="e5", best_move_depth=22)
    import chess_harness.engine as engine_module
    import chess_harness.exceptional_moves as exceptional

    class FakeEngine:
        def __init__(self):
            self.engine = object()

        def quit(self):
            pass

    calls = []

    def classify(board, move, engine, audit=None):
        calls.append(move.uci())
        audit.update(best_move_uci=move.uci(), best_move_san=board.san(move), best_move_depth=18)
        return None

    monkeypatch.setattr(engine_module, "EvalEngineAdapter", FakeEngine)
    monkeypatch.setattr(exceptional, "sacrifice_cost", lambda board, move: 0)
    monkeypatch.setattr(exceptional, "classify_exceptional", classify)

    refreshed = backfill.refresh_labels(state, artifact, reuse_preferences=True)

    assert calls == ["e7e5"]
    assert refreshed["plies"][0]["label"] == "inaccuracy"
    assert refreshed["plies"][0]["best_move_uci"] == "d2d4"
    assert refreshed["plies"][0]["best_move_depth"] == 14
    assert refreshed["plies"][1]["label"] == "good"  # Fresh preference still wins over the raw loss threshold.
    assert refreshed["preference_reuse"] == {
        "enabled": True,
        "minimum_saved_preference_depth": 14,
        "skipped_rows": 1,
        "scope": "All prior labels except great/brilliant, including good, with a deep saved preference for another move and sacrifice_cost == 0",
    }
    assert "saved verified alternative preferences reused" in refreshed["label_refresh_scope"]


def test_good_row_with_deep_nonplayed_preference_is_reused(monkeypatch):
    state = _state()
    artifact = _artifact(state)
    row = artifact["plies"][0]
    row.update(label="good", best_move_uci="d2d4", best_move_san="d4", best_move_depth=14)

    import chess_harness.engine as engine_module
    import chess_harness.exceptional_moves as exceptional

    monkeypatch.setattr(engine_module, "EvalEngineAdapter", lambda: pytest.fail("eligible row should be skipped"))
    monkeypatch.setattr(exceptional, "sacrifice_cost", lambda board, move: 0)
    monkeypatch.setattr(exceptional, "classify_exceptional", lambda *args, **kwargs: pytest.fail("eligible row should be skipped"))

    refreshed = backfill.refresh_labels(state, artifact, reuse_preferences=True)

    assert refreshed["plies"][0]["label"] == "inaccuracy"  # Preserve the fresh raw-loss threshold label.
    assert refreshed["plies"][0]["best_move_uci"] == "d2d4"
    assert refreshed["preference_reuse"]["skipped_rows"] == 1
    assert "including good" in refreshed["preference_reuse"]["scope"]


@pytest.mark.parametrize(
    "prior_label,best_move,best_depth,sacrifice_cost",
    [
        ("great", "d2d4", 14, 0),  # Prior positives always receive fresh review.
        ("inaccuracy", "e2e4", 14, 0),  # Existing preference is the played move.
        ("inaccuracy", "d2d4", 13, 0),  # Shallow preferences receive fresh review.
        ("inaccuracy", "d2d4", 14, 100),  # Possible material offers receive fresh review.
        ("good", "invalid-uci", 18, 0),  # Corrupt saved preferences cannot skip verification.
        ("good", "e7e5", 18, 0),  # A preference must be legal for the mover.
    ],
)
def test_preference_reuse_keeps_all_guarded_rows_on_engine_path(
    monkeypatch, prior_label, best_move, best_depth, sacrifice_cost
):
    state = _state()
    artifact = _artifact(state)
    row = artifact["plies"][0]
    row.update(label=prior_label, best_move_uci=best_move, best_move_depth=best_depth)
    if prior_label in {"great", "brilliant"}:
        row["exceptional"] = {"passes": [{}, {}]}

    import chess_harness.engine as engine_module
    import chess_harness.exceptional_moves as exceptional

    class FakeEngine:
        def __init__(self):
            self.engine = object()

        def quit(self):
            pass

    calls = []
    monkeypatch.setattr(engine_module, "EvalEngineAdapter", FakeEngine)
    monkeypatch.setattr(exceptional, "sacrifice_cost", lambda board, move: sacrifice_cost)
    monkeypatch.setattr(exceptional, "classify_exceptional", lambda *args, **kwargs: calls.append(True))

    refreshed = backfill.refresh_labels(state, artifact, reuse_preferences=True)

    assert calls == [True]
    assert refreshed["preference_reuse"]["skipped_rows"] == 0


def test_default_refresh_does_not_reuse_saved_preferences(monkeypatch):
    state = _state()
    artifact = _artifact(state)
    import chess_harness.engine as engine_module
    import chess_harness.exceptional_moves as exceptional

    class FakeEngine:
        def __init__(self):
            self.engine = object()

        def quit(self):
            pass

    calls = []
    monkeypatch.setattr(engine_module, "EvalEngineAdapter", FakeEngine)
    monkeypatch.setattr(exceptional, "sacrifice_cost", lambda board, move: 0)
    monkeypatch.setattr(exceptional, "classify_exceptional", lambda *args, **kwargs: calls.append(True))

    refreshed = backfill.refresh_labels(state, artifact)

    assert calls == [True]
    assert refreshed["preference_reuse"]["enabled"] is False
    assert refreshed["preference_reuse"]["skipped_rows"] == 0


def test_backfill_game_passes_reuse_flag_and_keeps_history(tmp_path, monkeypatch):
    state = _state()
    artifact = _artifact(state)
    artifact["plies"][0].update(loss_percent=8, label="inaccuracy")
    save_analysis(tmp_path, artifact)

    import chess_harness.engine as engine_module
    import chess_harness.exceptional_moves as exceptional

    monkeypatch.setattr(engine_module, "EvalEngineAdapter", lambda: pytest.fail("eligible row should be skipped"))
    monkeypatch.setattr(exceptional, "sacrifice_cost", lambda board, move: 0)
    monkeypatch.setattr(exceptional, "classify_exceptional", lambda *args, **kwargs: pytest.fail("eligible row should be skipped"))

    assert backfill.backfill_game(
        state, tmp_path, "reuse-run", 8, refresh=True, reuse_preferences=True
    ) == "written"
    refreshed = json.loads((tmp_path / "move-analysis.json").read_text())
    assert refreshed["preference_reuse"]["skipped_rows"] == 1
    assert refreshed["plies"][0]["label"] == "inaccuracy"
    assert (tmp_path / "analysis-history/reuse-run/move-analysis.json").exists()
