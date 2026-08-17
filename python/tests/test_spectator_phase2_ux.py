"""Phase 2: chat toggle placement, last-move colors, board annotations."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PUBLIC_SITE = REPO_ROOT / "public-site"
PUBLIC_JS = PUBLIC_SITE / "js"
ARROWS_CSS = (
    "https://cdn.jsdelivr.net/npm/cm-chessboard@8.7.2/assets/extensions/arrows/arrows.css"
)


def test_game_page_chat_toggle_in_card_headers():
    html = (PUBLIC_SITE / "g" / "index.html").read_text(encoding="utf-8")
    assert "info-col-footer" not in html
    assert 'id="info-panel-toggle"' in html
    assert 'id="info-panel-toggle-chat"' in html
    assert html.index("info-card-head") < html.index('id="info-panel-toggle"')
    assert html.index('id="info-panel-toggle"') < html.index("export-links")
    assert ">Chat</button>" in html
    assert ">Game</button>" in html


def test_spectator_board_uses_colored_last_move_not_frame():
    js = (PUBLIC_JS / "spectator-board.js").read_text(encoding="utf-8")
    assert "MARKER_TYPE.frame" not in js
    assert "paintLastMoveMarkers" in js
    assert "createBoardAnnotations" in js
    assert "Arrows" in js


def test_shared_annotation_and_last_move_modules_exist():
    assert (PUBLIC_JS / "board-annotations.js").is_file()
    assert (PUBLIC_JS / "board-last-move.js").is_file()
    ann = (PUBLIC_JS / "board-annotations.js").read_text(encoding="utf-8")
    assert "createBoardAnnotations" in ann
    assert "ANNOTATION_SQUARE_MARKER" in ann
    assert "ANNOTATION_PREVIEW" not in ann
    assert "knightCornerSquare" in ann
    assert "toggleArrow" in ann
    assert "isKnightMove" in ann
    last = (PUBLIC_JS / "board-last-move.js").read_text(encoding="utf-8")
    assert "LAST_MOVE_FROM_MARKER" in last
    assert "LAST_MOVE_TO_MARKER" in last


def test_watch_pages_load_arrows_css():
    for rel in ("g/index.html", "p/index.html", "i/index.html", "play/index.html"):
        html = (PUBLIC_SITE / rel).read_text(encoding="utf-8")
        assert ARROWS_CSS in html, rel


def test_play_board_wires_annotations_and_last_move():
    js = (PUBLIC_JS / "play-board.js").read_text(encoding="utf-8")
    assert "createBoardAnnotations" in js
    assert "paintLastMoveMarkers" in js
    assert "MARKER_TYPE.frame" not in js
    assert "Arrows" in js


def test_puzzle_and_identify_watch_wire_annotations():
    for name in ("puzzle-watch.js", "identify-watch.js"):
        js = (PUBLIC_JS / name).read_text(encoding="utf-8")
        assert "createBoardAnnotations" in js
        assert "clearAnnotations" in js
        assert "Arrows" in js


def test_puzzle_watch_paints_last_move_identify_does_not():
    puzzle = (PUBLIC_JS / "puzzle-watch.js").read_text(encoding="utf-8")
    identify = (PUBLIC_JS / "identify-watch.js").read_text(encoding="utf-8")
    assert "paintLastMoveMarkers" in puzzle
    assert "lastUciBetweenFens" in puzzle
    assert "pinScrollToBottom" in puzzle
    assert "paintLastMoveMarkers" not in identify
    assert "IDENTIFY_EXACT_MARKER" in identify
    assert "IDENTIFY_MISMATCH_MARKER" in identify
    assert "board.removeMarkers();" not in identify


def test_play_premove_waits_for_drag_cleanup():
    js = (PUBLIC_JS / "play-board-premove.js").read_text(encoding="utf-8")
    assert "deferDisplay" not in js
    assert "queueMicrotask" not in js
    assert "moveInputProcess" in js
    assert "syncDisplay(true)" in js
    assert "skipDisplay" in js
    assert js.count("afterDragCleanup") >= 2


def test_play_rails_follow_orientation():
    html = (PUBLIC_SITE / "play" / "index.html").read_text(encoding="utf-8")
    ui = (PUBLIC_JS / "play-page-ui.js").read_text(encoding="utf-8")
    css = (PUBLIC_SITE / "css" / "play.css").read_text(encoding="utf-8")
    assert "data-play-near-label" in html
    assert "data-play-far-label" in html
    assert "data-play-black-label" not in html
    assert "nearLbl.classList.add(humanColor)" in ui
    assert 'humanColor === "white" ? "black"' in ui
    assert "max-height: 1.4em" in css
    assert "white-space: nowrap" in css


def test_annotations_clear_only_empty_square():
    ann = (PUBLIC_JS / "board-annotations.js").read_text(encoding="utf-8")
    assert "squareOccupied" in ann
    assert "getPiece" in ann
    assert "getArrows" in ann
    assert "arrow-annotation-shaft" in (PUBLIC_SITE / "css" / "watch.css").read_text(
        encoding="utf-8"
    )


def test_puzzle_live_repins_after_layout():
    js = (PUBLIC_JS / "puzzle-watch.js").read_text(encoding="utf-8")
    assert "onPuzzleLayout" in js
    assert "ResizeObserver(onPuzzleLayout)" in js


def test_launcher_scripts_are_cache_busted():
    html = (PUBLIC_SITE / "launch" / "index.html").read_text(encoding="utf-8")
    assert "/js/launcher.js?v=" in html
    assert "/js/common.js?v=" in html


def test_launcher_enables_playground_nickname():
    js = (PUBLIC_SITE / "js" / "launcher.js").read_text(encoding="utf-8")
    assert "nicknameEl" in js
    assert "inscribeBtn, nicknameEl" in js or "nicknameEl].forEach" in js
    assert "Do not re-prompt" in js


def test_moves_scroll_helper_pins_to_bottom():
    helper = (PUBLIC_JS / "moves-scroll.js").read_text(encoding="utf-8")
    play_ui = (PUBLIC_JS / "play-page-ui.js").read_text(encoding="utf-8")
    spec = (PUBLIC_JS / "spectator-game.js").read_text(encoding="utf-8")
    assert "export function pinScrollToBottom" in helper
    assert "scrollHeight" in helper
    assert "pinScrollToBottom" in play_ui
    assert "scrollIntoView" not in play_ui
    assert "pinScrollToBottom" in spec


def test_watch_css_last_move_theme_tokens():
    css = (PUBLIC_SITE / "css" / "watch.css").read_text(encoding="utf-8")
    assert ".last-move-from" in css
    assert ".last-move-to" in css
    assert "[data-theme=\"dark\"]" in css
    assert "--last-move-from-fill" in css
    assert "arrow-annotation-preview" not in css
    assert ".meta-game-id code" in css
    assert "overflow-wrap: anywhere" in css
    assert "copy-game-id" in (PUBLIC_SITE / "g" / "index.html").read_text(encoding="utf-8")
