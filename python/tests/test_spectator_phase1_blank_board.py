"""Phase 1: spectator blank board — CSS floor + first-load sync hardening."""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PUBLIC_CSS = REPO_ROOT / "public-site" / "css"
PUBLIC_JS = REPO_ROOT / "public-site" / "js"


def _board_wrap_rule(css: str) -> str:
    m = re.search(
        r"\.watch-board-wrap,\s*\n\.spec-board-wrap,\s*\n\.puzzle-board-wrap\s*\{([^}]+)\}",
        css,
        re.DOTALL,
    )
    assert m, "board wrap rule not found"
    return m.group(1)


def test_watch_css_board_wrap_width_has_240px_floor():
    css = (PUBLIC_CSS / "watch.css").read_text(encoding="utf-8")
    rule = _board_wrap_rule(css)
    assert "max(240px, calc(100vw - 560px))" in rule
    assert "max(240px, calc(100vh - 220px))" in rule
    assert "min-width: 240px" in rule
    assert "calc(100vw - 560px)" in rule


def test_spectator_board_js_refreshes_layout_after_sync():
    js = (PUBLIC_JS / "spectator-board.js").read_text(encoding="utf-8")
    assert "responsive: true" in js
    assert "handleResize" in js
    assert "afterLayoutPaint" in js
    assert "requestAnimationFrame" in js


def test_spectator_game_js_always_fetches_moves_and_syncs_tip():
    js = (PUBLIC_JS / "spectator-game.js").read_text(encoding="utf-8")
    poll = js[js.index("async function poll") : js.index("window.addEventListener", js.index("async function poll"))]
    assert poll.index('fetch("/api/games/"') < poll.index("needsBoardSync")
    assert "needsBoardSync" in poll
    assert "movesPlyCount !== board.getTipPly()" in poll
    assert "effectiveMoveCount" in poll
    assert "syncHeights();" in poll
