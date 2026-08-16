"""Phase 2: chat toggle placement, last-move colors, board annotations."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PUBLIC_SITE = REPO_ROOT / "public-site"
PUBLIC_JS = PUBLIC_SITE / "js"
ARROWS_CSS = (
    "https://cdn.jsdelivr.net/npm/cm-chessboard@8.7.2/assets/extensions/arrows/arrows.css"
)


def test_game_page_chat_toggle_in_export_footer_not_info_head():
    html = (PUBLIC_SITE / "g" / "index.html").read_text(encoding="utf-8")
    assert "info-col-head" not in html
    assert 'id="info-panel-toggle"' in html
    assert html.index("export-links") < html.index('id="info-panel-toggle"')


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


def test_watch_css_last_move_theme_tokens():
    css = (PUBLIC_SITE / "css" / "watch.css").read_text(encoding="utf-8")
    assert ".last-move-from" in css
    assert ".last-move-to" in css
    assert "[data-theme=\"dark\"]" in css
    assert "--last-move-from-fill" in css
