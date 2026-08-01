"""Phase 6: /g/ wider columns, info-column height sync, shared engine abbreviation."""

from __future__ import annotations

import re
from pathlib import Path

from chess_harness.spectator_game_page import render_game_view_page

REPO_ROOT = Path(__file__).resolve().parents[2]
PUBLIC_JS = REPO_ROOT / "public-site" / "js"


def _abbrev_from_js_logic(value: str) -> str:
    """Mirror CVH.abbreviateListName for focused regression checks."""

    def name_without_elo(v: str) -> str:
        return re.sub(r"\s*\(\d+\)\s*$", "", str(v or "")).strip()

    def shorten_engine_tag(tag: str) -> str:
        t = str(tag or "").strip()
        m = re.match(r"^depth\s+(\d+)\s*\+\s*(\d+)%\s*noise$", t, re.I)
        if m:
            return f"d{m.group(1)}+{m.group(2)}%"
        m = re.match(r"^depth\s+(\d+)$", t, re.I)
        if m:
            return f"d{m.group(1)}"
        m = re.match(r"^(\d+)%\s*noise$", t, re.I)
        if m:
            return f"{m.group(1)}% noise"
        m = re.match(r"^Skill\s+(-?\d+)$", t, re.I)
        if m:
            return f"Skill {m.group(1)}"
        return t

    s = name_without_elo(value)
    m = re.match(r"^Stockfish\s+\d+(?:\.\d+)?\s*\((.+)\)$", s, re.I)
    if m:
        return shorten_engine_tag(m.group(1))
    m = re.match(r"^Stockfish\s+(\d+(?:\.\d+)?)$", s, re.I)
    if m:
        return f"SF {m.group(1)}"
    return s


def test_spectator_game_page_phase6_layout_widths():
    html = render_game_view_page("game-phase6")
    assert "minmax(300px,400px)" in html
    assert "minmax(240px,320px)" in html
    assert "minmax(280px,360px)" not in html
    assert "minmax(200px,280px)" not in html
    assert "calc(100vw - 848px)" in html
    assert "calc(100vw - 768px)" not in html
    assert ".info-panel-slot{position:relative;flex:1" in html


def test_spectator_game_js_syncs_info_column_height():
    js = (PUBLIC_JS / "spectator-game.js").read_text(encoding="utf-8")
    assert 'querySelector(".info-col")' in js
    assert "infoCol.style.height" in js
    assert "movesCol.style.maxHeight" in js
    assert "abbreviateName" in js
    assert "CVH.abbreviateListName" in js
    # Applied in Game info, quality labels (via sideNames), and board chrome.
    assert "abbreviateName(whiteName)" in js
    assert "abbreviateName(blackName)" in js
    assert "ev.top_label" in js
    assert js.index("abbreviateName") < js.index("ev.top_label")


def test_common_js_exports_abbreviate_list_name():
    js = (PUBLIC_JS / "common.js").read_text(encoding="utf-8")
    assert "function abbreviateListName" in js
    assert "function shortenEngineTag" in js
    assert "window.CVH.abbreviateListName = abbreviateListName" in js
    assert "window.CVH.nameWithoutElo = nameWithoutElo" in js


def test_abbreviate_list_name_shortens_stockfish_tags():
    assert (
        _abbrev_from_js_logic("Stockfish 17.1 (depth 1 + 62% noise)") == "d1+62%"
    )
    assert _abbrev_from_js_logic("Stockfish 17.1 (depth 4)") == "d4"
    assert _abbrev_from_js_logic("Stockfish 17.1 (10% noise)") == "10% noise"
    assert _abbrev_from_js_logic("Stockfish 17.1 (Skill 5)") == "Skill 5"
    assert _abbrev_from_js_logic("Stockfish 17.1") == "SF 17.1"
    assert (
        _abbrev_from_js_logic("Stockfish 17.1 (depth 1 + 62% noise) (412)")
        == "d1+62%"
    )
    assert _abbrev_from_js_logic("Claude Opus") == "Claude Opus"
