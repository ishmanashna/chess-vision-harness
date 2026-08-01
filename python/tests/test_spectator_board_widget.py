"""Phase 5: /g/ cm-chessboard spectator widget markup + moves start_fen."""

from __future__ import annotations

from pathlib import Path

from chess_harness.move_rows import spectator_moves_payload
from chess_harness.spectator_game_page import (
    CM_CDN,
    CM_CHESSBOARD_VERSION,
    render_game_view_page,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
PUBLIC_JS = REPO_ROOT / "public-site" / "js"


def test_spectator_game_page_board_widget_markup():
    html = render_game_view_page("game-board-widget")
    assert 'id="board-wrap"' in html
    assert 'class="spec-board-wrap"' in html
    assert 'id="board"' in html
    assert 'class="spec-board"' in html
    # On-screen board is a mount div, not a tip <img>; download link still Pillow PNG.
    assert '<img id="board"' not in html
    assert 'href="/g/game-board-widget/board.png"' in html
    assert "Download board PNG" in html
    assert 'type="module" src="/js/spectator-game.js"' in html
    assert f"cm-chessboard@{CM_CHESSBOARD_VERSION}" in html
    assert f"{CM_CDN}/assets/chessboard.css" in html
    assert "markers/markers.css" in html
    assert 'data-game-id="game-board-widget"' in html


def test_spectator_board_js_matches_playground_cdn():
    board_js = (PUBLIC_JS / "spectator-board.js").read_text(encoding="utf-8")
    assert "cm-chessboard@8.7.2" in board_js
    assert "pieces/staunty.svg" in board_js
    assert "showCoordinates: true" in board_js
    assert "BORDER_TYPE.none" in board_js
    assert "COLOR.white" in board_js
    assert "autoMarkers: null" in board_js
    assert "MARKER_TYPE.frame" in board_js
    assert "setViewPly" in board_js
    assert "syncTip" in board_js
    play_board = (PUBLIC_JS / "play-board.js").read_text(encoding="utf-8")
    assert "cm-chessboard@8.7.2" in play_board


def test_spectator_game_js_uses_moves_api_not_img_src():
    game_js = (PUBLIC_JS / "spectator-game.js").read_text(encoding="utf-8")
    assert "createSpectatorBoard" in game_js
    assert "/moves" in game_js
    assert "plies_detail" in game_js
    assert "start_fen" in game_js
    assert "board.syncTip" in game_js
    assert 'getElementById("board").src' not in game_js
    assert "CVH.spectatorBoard" in game_js


def test_spectator_moves_payload_includes_start_fen():
    import chess

    custom = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1"
    payload = spectator_moves_payload(
        {"start_fen": custom, "moves": ["e7e5"]}
    )
    assert payload["start_fen"] == custom
    assert payload["plies"] == 1
    assert payload["plies_detail"][0]["uci"] == "e7e5"
    assert "fen" not in payload  # bare key never; start_fen is spectator-only

    default = spectator_moves_payload({"moves": []})
    assert default["start_fen"] == chess.STARTING_FEN
