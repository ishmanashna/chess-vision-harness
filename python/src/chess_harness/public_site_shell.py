"""Static watch/play HTML shells under public-site/ (Phase 9c)."""

from __future__ import annotations

from fastapi.responses import HTMLResponse

from .paths import project_root

__all__ = ["read_watch_shell", "watch_shell_response"]

_SHELL_DIRS = {
    "g": "g",
    "p": "p",
    "i": "i",
    "play": "play",
}


def read_watch_shell(kind: str) -> str:
    """Return the static HTML shell for a watch/play route kind."""
    subdir = _SHELL_DIRS[kind]
    path = project_root() / "public-site" / subdir / "index.html"
    return path.read_text(encoding="utf-8")


def watch_shell_response(kind: str) -> HTMLResponse:
    """HTMLResponse for local serve; Pages serves the same files statically."""
    headers: dict[str, str] = {}
    if kind == "play":
        headers["Referrer-Policy"] = "no-referrer"
    return HTMLResponse(read_watch_shell(kind), headers=headers or None)
