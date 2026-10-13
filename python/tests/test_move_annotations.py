"""Per-ply alignment, mate semantics, persistence and spectator-only disclosure."""
import json
from types import SimpleNamespace

import chess
import pytest

from chess_harness.game_manager import GameManager
from chess_harness.game_quality import analyse_game
from chess_harness.move_annotations import annotations_payload, move_label, position_score, save_analysis
from chess_harness.move_rows import moves_payload, spectator_moves_payload

MOVES = ["e2e4", "e7e5", "g1f3", "b8c6"]


def fixture_analysis(moves=MOVES):
    scores = [0, -200, 200, 190, 190]
    return analyse_game(moves, depth=8, eval_fn=lambda board: scores[len(board.move_stack)]).move_analysis


def state(moves=MOVES, **extra):
    return dict(status="finished", result="1-0", moves=moves, quality_at="fixture", **extra)


def test_each_ply_has_mover_relative_loss_but_white_relative_scores():
    analysis = fixture_analysis()
    rows = analysis["plies"]
    assert [row["ply"] for row in rows] == [1, 2, 3, 4]
    assert [row["color"] for row in rows] == ["white", "black", "white", "black"]
    assert rows[0]["loss_cp"] == 200
    assert rows[1]["loss_cp"] == 400  # Black loses when White's eval increases.
    assert rows[1]["before"]["cp"] == -200 and rows[1]["after"]["cp"] == 200
    assert rows[0]["label"] == "mistake" and rows[1]["label"] == "blunder"
    assert rows[-1]["label"] == "good"
    assert analysis["profile"]["depth"] == 8 and not analysis["profile"]["budget_validated"]
    assert not any(key in json.dumps(analysis) for key in ['"pv"', '"best_move"', '"alternatives"'])


@pytest.mark.parametrize("loss,label", [(0,"good"), (5,"good"), (7.99,"good"), (8,"inaccuracy"), (9.99,"inaccuracy"), (10,"mistake"), (30,"mistake"), (30.01,"blunder")])
def test_label_boundaries(loss, label):
    assert move_label(loss) == label


def test_preferred_move_is_not_a_shallow_search_error_and_scores_are_preserved():
    from chess_harness.move_annotations import apply_preference
    row = {"uci":"e2e4","label":"mistake","before":{"cp":100},"after":{"cp":-100},"loss_percent":17.0}
    apply_preference(row,{"best_move_uci":"e2e4","best_move_san":"e4","best_move_depth":14})
    assert row["label"] == "good" and row["shallow_label"] == "mistake"
    assert row["before"]["cp"] == 100 and row["after"]["cp"] == -100 and row["loss_percent"] == 17.0


def test_checkmate_is_typed_not_a_fake_centipawn_delta():
    moves = ["f2f3", "e7e5", "g2g4", "d8h4"]
    analysis = analyse_game(moves, eval_fn=lambda board: -500).move_analysis
    last = analysis["plies"][-1]
    assert last["after"] == {"cp": None, "mate": 0, "winner": "black"}
    assert last["loss_cp"] is None and last["label"] == "good"
    engine = SimpleNamespace(last_evaluation={"mate": 3})
    assert position_score(chess.Board(), 10000, engine)["winner"] == "white"
    engine.last_evaluation = {"mate": -4}
    assert position_score(chess.Board(), -10000, engine)["winner"] == "black"
    drawn = chess.Board("8/8/8/8/8/8/4k3/7K w - - 0 1")
    assert position_score(drawn, 0, engine) == {"cp": 0, "mate": None}


def test_black_start_fen_preserves_ply_color_and_move_number():
    fen = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 7"
    pgn = f'[SetUp "1"]\n[FEN "{fen}"]\n\n7... e5 8. Nf3 *'
    quality = analyse_game(pgn, eval_fn=lambda board: 0)
    assert quality.start_color == chess.BLACK
    assert [row["color"] for row in quality.move_analysis["plies"]] == ["black", "white"]
    saved = state(["e7e5", "g1f3"], start_fen=fen)
    rows = spectator_moves_payload(saved)["move_rows"]
    assert rows[0] == {"num": 7, "white": "", "black": "e5", "white_ply": None, "black_ply": 1}
    assert rows[1]["num"] == 8 and rows[1]["white_ply"] == 2


def test_incomplete_analysis_is_not_presented_as_complete(tmp_path):
    analysis = analyse_game(MOVES, eval_fn=lambda board: None if len(board.move_stack) == 2 else 0).move_analysis
    assert analysis["status"] == "incomplete"
    save_analysis(tmp_path, analysis)
    assert annotations_payload(tmp_path, state())["status"] == "unavailable"


def test_saved_analysis_is_validated_and_projection_excludes_lines(tmp_path):
    analysis = fixture_analysis()
    analysis["secret"] = "private"
    analysis["plies"][0]["pv"] = ["d2d4"]
    analysis["plies"][0]["before"]["pv"] = ["d2d4"]
    save_analysis(tmp_path, analysis)
    payload = annotations_payload(tmp_path, state())
    assert payload["status"] == "complete"
    assert "private" not in json.dumps(payload) and '"pv"' not in json.dumps(payload)
    assert annotations_payload(tmp_path, state(["d2d4"]))["status"] == "unavailable"
    assert annotations_payload(tmp_path, dict(state(), status="in_progress"))["status"] == "unavailable"
    analysis["plies"][1]["ply"] = 1
    save_analysis(tmp_path, analysis)
    assert annotations_payload(tmp_path, state())["status"] == "unavailable"


def test_positive_labels_need_saved_verification_and_never_publish_candidate_lines(tmp_path):
    from chess_harness.exceptional_moves import VERSION
    analysis = fixture_analysis()
    row = analysis["plies"][0]
    row["label"] = "brilliant"
    save_analysis(tmp_path, analysis)
    assert annotations_payload(tmp_path,state())["status"] == "unavailable"
    row["exceptional"] = {"version": VERSION, "sacrifice_cp": 200, "pv":["private"],
                          "passes":[{"depth":18,"label":"brilliant","best_chance":.6,"second_chance":.5,"pv":["private"]},
                                    {"depth":22,"label":"brilliant","best_chance":.6,"second_chance":.5}]}
    save_analysis(tmp_path,analysis)
    payload = annotations_payload(tmp_path,state())
    assert payload["status"] == "complete"
    assert payload["plies"][0]["exceptional"]["sacrifice_cp"] == 200
    assert "private" not in json.dumps(payload) and '"pv"' not in json.dumps(payload)


def test_missing_and_bad_artifacts_are_honest(tmp_path):
    assert annotations_payload(tmp_path, state())["status"] == "unavailable"
    pending = state()
    pending.pop("quality_at")
    assert annotations_payload(tmp_path, pending)["status"] == "pending"
    assert annotations_payload(tmp_path, dict(state(),quality_provisional=True))["status"] == "pending"
    (tmp_path / "move-analysis.json").write_text("broken")
    assert annotations_payload(tmp_path, pending)["status"] == "unavailable"


def test_finish_persists_annotations_without_agent_surface_changes(tmp_path, monkeypatch):
    from chess_harness import quality_finish
    gm = GameManager(str(tmp_path))
    saved = state(agent_color="WHITE")
    saved.pop("quality_at")
    gm.save_state("fixture", saved)
    gm.get_pgn_path("fixture").write_text("1. e4 e5 2. Nf3 Nc6 1-0")
    quality = analyse_game(MOVES, eval_fn=lambda board: 0)
    monkeypatch.setattr(quality_finish, "analyse_game", lambda pgn, **kwargs: quality)
    before = moves_payload(saved)
    assert quality_finish.run_game_quality("fixture", base_dir=str(tmp_path))
    after_state = gm.load_state("fixture")
    assert annotations_payload(gm.get_game_dir("fixture"), after_state)["status"] == "complete"
    assert moves_payload(after_state) == before
    assert "move_analysis" not in after_state and "annotations" not in after_state
    assert not quality_finish.run_game_quality("fixture", base_dir=str(tmp_path))


def test_annotations_route_only_reads_saved_finished_artifact(harness_client, monkeypatch):
    from chess_harness import spectator
    client, base = harness_client
    gm = GameManager(str(base))
    saved = state()
    gm.save_state("fixture", saved)
    save_analysis(gm.get_game_dir("fixture"), fixture_analysis())
    monkeypatch.setattr(spectator, "_eval_position", lambda *args: pytest.fail("GET must not run an engine"))
    assert client.get("/api/games/fixture/annotations").json()["status"] == "complete"
    saved["status"] = "in_progress"
    gm.save_state("fixture", saved)
    assert client.get("/api/games/fixture/annotations").json()["status"] == "unavailable"
    saved.update(status="finished", prompt_pack="P1", prompt_test_family="composer")
    # Packed visibility uses the same helper as other spectator endpoints.
    gm.save_state("fixture", saved)
    assert client.get("/api/games/fixture/annotations", headers={"Host": "public.example"}).status_code == 404
