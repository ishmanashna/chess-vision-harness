import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from chess_harness import annotation_backfill as backfill
from chess_harness.game_quality import analyse_game
from chess_harness.move_annotations import annotations_payload


def state():
    return {"game_id":"game-old", "status":"finished", "game_type":"agent_vs_engine",
            "model_name":"test-agent", "moves":["e2e4","e7e5"], "result":"1-0",
            "agent_accuracy":87.2,"agent_play_rating":2200,"elo_after":630}


def fake_analysis(pgn, depth, include_exceptional):
    assert include_exceptional
    quality = analyse_game(pgn, depth=depth, eval_fn=lambda board:15)
    quality.move_analysis["exceptional_profile"]["enabled"] = True
    return quality


def test_annotation_only_preserves_state_results_and_old_artifact(tmp_path):
    saved = state()
    raw = json.dumps(saved).encode()
    (tmp_path/"state.json").write_bytes(raw)
    (tmp_path/"game.pgn").write_text("original PGN")
    (tmp_path/"move-analysis.json").write_text('{"old":true}')
    assert backfill.backfill_game(saved,tmp_path,"run",8,fake_analysis) == "written"
    assert (tmp_path/"state.json").read_bytes() == raw
    assert (tmp_path/"game.pgn").read_text() == "original PGN"
    assert (tmp_path/"analysis-history/run/move-analysis.json").read_text() == '{"old":true}'
    assert annotations_payload(tmp_path,saved)["status"] == "complete"
    assert backfill.backfill_game(saved,tmp_path,"run2",8,lambda *a,**kw:pytest.fail("already saved")) == "existing"


def test_invalid_moves_do_not_replace_saved_artifact(tmp_path):
    saved = state()
    saved["moves"] = ["e2e5"]
    (tmp_path/"move-analysis.json").write_text("original")
    with pytest.raises(ValueError, match="Illegal saved move"):
        backfill.backfill_game(saved,tmp_path,"run",8,fake_analysis)
    assert (tmp_path/"move-analysis.json").read_text() == "original"


def test_nonstandard_start_and_empty_game(tmp_path):
    saved = state()
    saved.update(start_fen="8/8/8/8/8/8/4k3/6K1 b - - 0 8",moves=[])
    assert backfill.backfill_game(saved,tmp_path,"run",8,lambda *a,**kw:pytest.fail("no engine needed")) == "written"
    assert annotations_payload(tmp_path,saved)["plies"] == []


def test_inventory_prefers_live_state_and_retains_archive_only(tmp_path):
    import sqlite3
    root = tmp_path/"runtime"
    folder = root/"games/game-old"
    folder.mkdir(parents=True)
    live = state()
    (folder/"state.json").write_text(json.dumps(live))
    database = tmp_path/"archive.sqlite"
    with sqlite3.connect(database) as db:
        db.execute("CREATE TABLE finished_games (game_id TEXT,state_json TEXT)")
        archived = dict(live,game_id="game-archived")
        db.executemany("INSERT INTO finished_games VALUES (?,?)",[("game-old",json.dumps(dict(live,moves=[]))),
                                                                 ("game-archived",json.dumps(archived))])
    before = database.read_bytes()
    rows = backfill.inventory(root,database)
    assert rows["game-old"][0]["moves"] == live["moves"]
    assert rows["game-archived"][1] == root/"archived-move-analysis/game-archived"
    assert database.read_bytes() == before


def test_label_refresh_reuses_saved_evaluations_and_preserves_prior_analysis(tmp_path, monkeypatch):
    saved = state()
    backfill.backfill_game(saved,tmp_path,"first",8,fake_analysis)
    path = tmp_path/"move-analysis.json"
    old = json.loads(path.read_text())
    old["profile"]["label_version"] = "win-chance-loss-exceptional-v2"
    old["plies"][0].update(loss_percent=6,label="inaccuracy")
    path.write_text(json.dumps(old))
    import chess_harness.exceptional_moves as exceptional
    import chess_harness.engine as engine_module
    monkeypatch.setattr(engine_module,"EvalEngineAdapter",lambda:SimpleNamespace(quit=lambda:None))
    monkeypatch.setattr(exceptional,"sacrifice_cost",lambda *a:0)
    monkeypatch.setattr(exceptional,"classify_exceptional",lambda *a:None)
    assert backfill.backfill_game(saved,tmp_path,"refresh",8,lambda *a,**kw:pytest.fail("must reuse scores"),refresh=True) == "written"
    new = json.loads(path.read_text())
    assert new["plies"][0]["label"] == "good"
    assert new["plies"][0]["before"] == old["plies"][0]["before"]
    assert new["plies"][0]["after"] == old["plies"][0]["after"]
    assert new["profile"]["engine_sha256"] == old["profile"]["engine_sha256"]
    assert (tmp_path/"analysis-history/refresh/move-analysis.json").exists()
