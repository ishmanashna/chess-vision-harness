"""Static watch/play HTML shells under public-site/ (Phase 9c)."""

from __future__ import annotations

import re
from html import escape

from fastapi.responses import HTMLResponse

from .paths import project_root

__all__ = ["inject_shell_entity_id", "read_watch_shell", "watch_shell_response"]

_SHELL_DIRS = {
    "g": "g",
    "p": "p",
    "i": "i",
    "play": "play",
}

_DATA_ATTR_BY_KIND = {
    "p": "data-attempt-id",
    "i": "data-attempt-id",
    "g": "data-game-id",
    "play": "data-game-id",
}

_BODY_TAG_RE = re.compile(r"(<body)(\s[^>]*)?(>)", re.IGNORECASE)


def read_watch_shell(kind: str) -> str:
    """Return the static HTML shell for a watch/play route kind."""
    subdir = _SHELL_DIRS[kind]
    path = project_root() / "public-site" / subdir / "index.html"
    return path.read_text(encoding="utf-8")


def inject_shell_entity_id(html: str, kind: str, entity_id: str) -> str:
    """Inject ``data-attempt-id`` or ``data-game-id`` onto the shell ``<body>``."""
    entity_id = str(entity_id or "").strip()
    if not entity_id:
        return html
    attr = _DATA_ATTR_BY_KIND.get(kind)
    if not attr:
        return html
    safe = escape(entity_id, quote=True)

    def repl(match: re.Match[str]) -> str:
        prefix, attrs, close = match.group(1), match.group(2) or "", match.group(3)
        if attr in attrs:
            return match.group(0)
        return f'{prefix}{attrs} {attr}="{safe}"{close}'

    return _BODY_TAG_RE.sub(repl, html, count=1)


def watch_shell_response(kind: str, entity_id: str | None = None) -> HTMLResponse:
    """HTMLResponse for local serve; Pages serves the same files statically."""
    html = read_watch_shell(kind)
    if entity_id:
        html = inject_shell_entity_id(html, kind, entity_id)
    headers: dict[str, str] = {}
    if kind == "play":
        headers["Referrer-Policy"] = "no-referrer"
    return HTMLResponse(html, headers=headers or None)
