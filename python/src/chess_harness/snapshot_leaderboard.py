"""Export public-site leaderboard snapshot from harness models and results."""

from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .models import AGENT_START_ELO, ModelRegistry, normalize_observation
from .paths import project_root, resolve_base_dir, resolve_publish_snapshots_dir
from .puzzle_leaderboard import (
    build_identify_leaderboard,
    build_puzzle_leaderboard,
)
from .results import ResultsManager

# Matches rating_math.k_factor stable threshold and public-site provisional display.
PROVISIONAL_GAMES_THRESHOLD = 100

SNAPSHOT_REFRESH_MIN_INTERVAL_SEC = 30.0
_snapshot_refresh_lock = threading.Lock()
_last_snapshot_refresh_mono = 0.0


def default_output_path() -> Path:
    """Runtime snapshot path used by serve (not the git Sleeping fallback)."""
    return resolve_publish_snapshots_dir() / "leaderboard.json"


def default_puzzle_leaderboard_path() -> Path:
    return resolve_publish_snapshots_dir() / "puzzles_leaderboard.json"


def default_identify_leaderboard_path() -> Path:
    return resolve_publish_snapshots_dir() / "identify_leaderboard.json"


def git_publish_leaderboard_path() -> Path:
    """Committed Sleeping fallback on Pages (`/data/leaderboard.json`)."""
    return project_root() / "public-site" / "data" / "leaderboard.json"


def git_publish_puzzle_leaderboard_path() -> Path:
    return project_root() / "public-site" / "data" / "puzzles_leaderboard.json"


def git_publish_identify_leaderboard_path() -> Path:
    return project_root() / "public-site" / "data" / "identify_leaderboard.json"


def is_provisional(games: int) -> bool:
    return games < PROVISIONAL_GAMES_THRESHOLD


def build_opponent_snapshot_rows() -> List[Dict[str, Any]]:
    """Anchors + calibrated floaters for the public ladder snapshot."""
    from .calibration_view import build_ladder_rating_table
    from .opponents import OpponentCatalog
    from .play_rating import play_rating_status_summary
    from .paths import project_root

    catalog = OpponentCatalog()
    cal_root = project_root() / "elo_calibration" / "results"
    try:
        quality = play_rating_status_summary(root=cal_root)
    except Exception:
        quality = {"engines": []}
    by_engine = {e["engine_id"]: e for e in quality.get("engines", [])}

    rows: List[Dict[str, Any]] = []
    for row in build_ladder_rating_table(catalog):
        oid = str(row.get("id") or "")
        opp = catalog.get(oid) if oid else None
        if opp and opp.type == "stockfish":
            name = f"{opp.display_name} ({oid})"
        elif opp:
            name = opp.display_name
        else:
            name = oid
        info = by_engine.get(oid) or {}
        mean_accuracy = info.get("mean_accuracy")
        mean_play_rating = info.get("mean_play_rating")
        rows.append(
            {
                "id": oid,
                "name": name,
                "elo": round(float(row.get("elo") or 0)),
                "games": int(row.get("games") or 0),
                "anchor": bool(row.get("anchor")),
                "uncalibrated": bool(row.get("uncalibrated")),
                "mean_accuracy": mean_accuracy,
                "mean_play_rating": mean_play_rating,
                "quality_games": int(info.get("sample_count") or 0),
            }
        )
    rows.sort(key=lambda r: (-r["elo"], str(r["name"]).lower()))
    return rows


def _quality_snapshot_fields(
    quality_stats: Dict[str, Dict[str, Any]], model_id: str
) -> Dict[str, Any]:
    stats = quality_stats.get(model_id, {})
    return {
        "mean_accuracy": stats.get("mean_accuracy"),
        "mean_play_rating": stats.get("mean_play_rating"),
        "quality_games": int(stats.get("quality_games", 0)),
    }


def build_snapshot(
    registry: ModelRegistry,
    game_counts: Dict[str, int],
    *,
    rated_counts: Optional[Dict[str, int]] = None,
    quality_stats: Optional[Dict[str, Dict[str, Any]]] = None,
    generated_at: Optional[str] = None,
    include_opponents: bool = True,
    puzzle_agents: Optional[List[Dict[str, Any]]] = None,
    identify_agents: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Build leaderboard snapshot.

    ``game_counts`` is the display Games column (scored: real results including AvH).
    ``rated_counts`` drives provisional ``*`` (Elo ladder games only). When omitted,
    provisional uses ``game_counts`` (legacy call sites / tests).
    ``puzzle_agents`` / ``identify_agents`` are the per-agent rows from
    ``build_puzzle_leaderboard`` / ``build_identify_leaderboard``; puzzle and
    identification stats are merged onto each agent row (nulls when absent) so
    the public site shows one unified table.
    Always emits boolean ``provisional`` so clients never derive it from display Games.
    """
    quality_stats = quality_stats or {}
    provisional_counts = rated_counts if rated_counts is not None else game_counts
    puzzle_by_id = {str(a.get("id") or ""): a for a in (puzzle_agents or [])}
    identify_by_id = {str(a.get("id") or ""): a for a in (identify_agents or [])}
    model_ids = {str(m.get("id") or "") for m in registry.list_models()}
    model_ids |= set(puzzle_by_id) | set(identify_by_id)
    agents: List[Dict[str, Any]] = []
    for model_id in sorted(model_ids):
        if not model_id:
            continue
        model = registry.get(model_id) or {}
        pz = puzzle_by_id.get(model_id) or {}
        iz = identify_by_id.get(model_id) or {}
        games = int(game_counts.get(model_id, 0))
        rated = int(provisional_counts.get(model_id, 0))
        agents.append(
            {
                "id": model_id,
                "name": model.get("name") or pz.get("name") or iz.get("name") or model_id,
                "elo": round(float(model.get("elo", AGENT_START_ELO))),
                "games": games,
                "provisional": is_provisional(rated),
                **_quality_snapshot_fields(quality_stats, model_id),
                "puzzle_rating": pz.get("rating"),
                "puzzle_deviation": pz.get("deviation"),
                "puzzle_attempts": int(pz.get("attempts") or 0),
                "puzzle_solves": int(pz.get("solves") or 0),
                "identify_attempts": int(iz.get("attempts") or 0),
                "identify_full": int(iz.get("full") or 0),
                "identify_mean_accuracy": iz.get("mean_accuracy"),
                "identify_full_position_rate": iz.get("full_position_rate"),
                "observation": normalize_observation(model.get("observation")),
            }
        )
    agents.sort(key=lambda a: (-a["elo"], str(a["name"]).lower()))

    if generated_at is None:
        generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")

    snapshot: Dict[str, Any] = {"generated_at": generated_at, "agents": agents}
    if include_opponents:
        snapshot["opponents"] = build_opponent_snapshot_rows()
    return snapshot


def load_live_leaderboard(
    *,
    base_dir: Optional[str] = None,
    registry: Optional[ModelRegistry] = None,
) -> Dict[str, Any]:
    """Build public-site leaderboard JSON from current harness state (no disk write)."""
    reg = registry or ModelRegistry()
    harness_base = str(base_dir) if base_dir else str(resolve_base_dir())
    results = ResultsManager(base_dir=harness_base)
    return build_snapshot(
        reg,
        results.count_scored_by_model(),
        rated_counts=results.count_by_model(),
        quality_stats=results.aggregate_quality_by_model(),
        puzzle_agents=build_puzzle_leaderboard(registry=reg).get("agents", []),
        identify_agents=build_identify_leaderboard(registry=reg).get("agents", []),
    )


def export_leaderboard_snapshot(
    output_path: Optional[Path | str] = None,
    *,
    base_dir: Optional[str] = None,
    registry: Optional[ModelRegistry] = None,
) -> Path:
    """Write leaderboard JSON for the public site offline fallback."""
    snapshot = load_live_leaderboard(base_dir=base_dir, registry=registry)
    out = Path(output_path) if output_path else default_output_path()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")
    return out


def load_live_puzzle_leaderboard(
    *, registry: Optional[ModelRegistry] = None
) -> Dict[str, Any]:
    """Public-site puzzle leaderboard JSON from current harness state."""
    return build_puzzle_leaderboard(registry=registry or ModelRegistry())


def load_live_identify_leaderboard(
    *, registry: Optional[ModelRegistry] = None
) -> Dict[str, Any]:
    """Public-site board-identification leaderboard JSON from current state."""
    return build_identify_leaderboard(registry=registry or ModelRegistry())


def _inject_inline_snapshot(snapshot_json: str) -> None:
    """Inject leaderboard JSON into HTML pages as an inline <script> tag.

    The JS front-end picks up ``window.CVH_INLINE_SNAPSHOT`` and paints
    the table instantly — no fetch needed. A subsequent live fetch upgrades
    the data if the server is reachable.
    """
    sentinel = "window.CVH_INLINE_SNAPSHOT"
    snippet = f'<script>{sentinel}={snapshot_json}</script>\n</head>'
    root = project_root() / "public-site"
    for rel in ("index.html", "leaderboard/index.html"):
        html_path = root / rel
        if not html_path.is_file():
            continue
        text = html_path.read_text(encoding="utf-8")
        # Remove any prior inline snapshot
        import re
        cleaned = re.sub(
            r"<script>window\.CVH_INLINE_SNAPSHOT=.*?</script>\n",
            "",
            text,
            flags=re.DOTALL,
        )
        new_text = cleaned.replace("</head>", snippet, 1)
        html_path.write_text(new_text, encoding="utf-8")


def export_public_snapshots(
    *,
    output_path: Optional[Path | str] = None,
    puzzle_path: Optional[Path | str] = None,
    identify_path: Optional[Path | str] = None,
    base_dir: Optional[str] = None,
    registry: Optional[ModelRegistry] = None,
    inject_inline: bool = False,
) -> Dict[str, Path]:
    """Write leaderboard snapshots (ladder, puzzles, identify).

    Default targets are the runtime publish dir under ``CHESS_HARNESS_DIR``
    (serve debounced refresh). Use ``export_git_publish_snapshots`` or pass
    explicit ``public-site/data`` paths for intentional Sleeping publish.
    """
    ladder_path = export_leaderboard_snapshot(
        Path(output_path) if output_path else None,
        base_dir=base_dir,
        registry=registry,
    )
    puzzle_out = Path(puzzle_path) if puzzle_path else default_puzzle_leaderboard_path()
    puzzle_out.parent.mkdir(parents=True, exist_ok=True)
    puzzle_out.write_text(
        json.dumps(load_live_puzzle_leaderboard(registry=registry), indent=2) + "\n",
        encoding="utf-8",
    )
    if identify_path:
        identify_out = Path(identify_path)
    elif puzzle_path:
        identify_out = Path(puzzle_path).parent / "identify_leaderboard.json"
    elif output_path:
        identify_out = Path(output_path).parent / "identify_leaderboard.json"
    else:
        identify_out = default_identify_leaderboard_path()
    identify_out.parent.mkdir(parents=True, exist_ok=True)
    identify_out.write_text(
        json.dumps(load_live_identify_leaderboard(registry=registry), indent=2) + "\n",
        encoding="utf-8",
    )
    if inject_inline:
        snapshot_json = ladder_path.read_text(encoding="utf-8").strip()
        _inject_inline_snapshot(snapshot_json)
    return {"leaderboard": ladder_path, "puzzles": puzzle_out, "identify": identify_out}


def export_git_publish_snapshots(
    *,
    output_path: Optional[Path | str] = None,
    base_dir: Optional[str] = None,
    registry: Optional[ModelRegistry] = None,
) -> Dict[str, Path]:
    """Write Sleeping fallbacks to ``public-site/data/*.json`` and inline HTML."""
    ladder = Path(output_path) if output_path else git_publish_leaderboard_path()
    puzzle_parent = ladder.parent
    return export_public_snapshots(
        output_path=ladder,
        puzzle_path=puzzle_parent / "puzzles_leaderboard.json",
        identify_path=puzzle_parent / "identify_leaderboard.json",
        base_dir=base_dir,
        registry=registry,
        inject_inline=True,
    )


def request_public_snapshots_refresh() -> None:
    """Debounced background write of all public-site leaderboard snapshots."""
    global _last_snapshot_refresh_mono
    now = time.monotonic()
    with _snapshot_refresh_lock:
        if now - _last_snapshot_refresh_mono < SNAPSHOT_REFRESH_MIN_INTERVAL_SEC:
            return
        try:
            export_public_snapshots()
            _last_snapshot_refresh_mono = now
        except Exception:
            pass
