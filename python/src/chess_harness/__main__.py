"""Canonical CLI entry (`chess-harness`, `python -m chess_harness`)."""

from __future__ import annotations

import json
import sys

from . import bootstrap  # noqa: F401
from . import commands


def _parse_new_opts(args: list[str]) -> dict:
    opts: dict = {}
    positional: list[str] = []
    i = 0
    while i < len(args):
        if args[i] == "--force":
            opts["force"] = True
            i += 1
        elif args[i].startswith("--") and i + 1 < len(args):
            opts[args[i][2:]] = args[i + 1]
            i += 2
        else:
            positional.append(args[i])
            i += 1
    opts["_positional"] = positional
    return opts


def main(argv: list[str] | None = None) -> None:
    args = list(sys.argv[1:] if argv is None else argv)

    if not args or args[0] == "new":
        opts = _parse_new_opts(args[1:] if args and args[0] == "new" else args)
        positional = opts.pop("_positional", [])
        game_id = opts.get("id", positional[0] if positional else commands.default_game_id())
        color = opts.get("color")
        skill = int(opts["skill"]) if "skill" in opts else None
        opponent = opts.get("opponent")
        print(
            json.dumps(
                commands.cmd_new(
                    game_id,
                    color,
                    skill,
                    opts.get("fen"),
                    opts.get("model"),
                    force=opts.get("force", False),
                    opponent=opponent,
                ),
                indent=2,
            )
        )

    elif args[0] == "move":
        if len(args) < 3:
            print("Usage: chess-harness move <game_id> <move>")
            sys.exit(1)
        print(json.dumps(commands.cmd_move(args[1], args[2]), indent=2))

    elif args[0] == "pgn":
        if len(args) < 2:
            print("Usage: chess-harness pgn <game_id>")
            sys.exit(1)
        print(json.dumps(commands.cmd_pgn(args[1]), indent=2))

    elif args[0] == "game":
        if len(args) < 3 or args[1] != "audit":
            print("Usage: chess-harness game audit <game_id>")
            sys.exit(1)
        print(json.dumps(commands.cmd_game_audit(args[2]), indent=2))

    elif args[0] == "resign":
        if len(args) < 2:
            print("Usage: chess-harness resign <game_id>")
            sys.exit(1)
        print(json.dumps(commands.cmd_resign(args[1]), indent=2))

    elif args[0] == "board":
        game_id = args[1] if len(args) > 1 else "default"
        print(json.dumps(commands.cmd_board(game_id), indent=2))

    elif args[0] == "status":
        game_id = args[1] if len(args) > 1 else "default"
        print(json.dumps(commands.cmd_status(game_id), indent=2))

    elif args[0] == "list":
        commands.cmd_list()

    elif args[0] == "leaderboard":
        commands.cmd_leaderboard()

    elif args[0] == "snapshot-leaderboard":
        output = None
        i = 1
        while i < len(args):
            if args[i] == "--output" and i + 1 < len(args):
                output = args[i + 1]
                i += 2
            else:
                i += 1
        commands.cmd_snapshot_leaderboard(output)

    elif args[0] == "rating":
        if len(args) < 3 or args[1] != "--model":
            print("Usage: chess-harness rating --model <name>")
            sys.exit(1)
        commands.cmd_rating(args[2])

    elif args[0] == "aggregate":
        commands.cmd_aggregate()

    elif args[0] == "rebuild-elo":
        commands.cmd_rebuild_elo()

    elif args[0] == "serve":
        if len(args) > 1 and args[1] == "stop":
            port = 8765
            if len(args) > 2 and args[2] == "--port" and len(args) > 3:
                port = int(args[3])
            commands.cmd_serve_stop(port)
            return

        host = "127.0.0.1"
        port = 8765
        force = False
        i = 1
        while i < len(args):
            if args[i] == "--host" and i + 1 < len(args):
                host = args[i + 1]
                i += 2
            elif args[i] == "--port" and i + 1 < len(args):
                port = int(args[i + 1])
                i += 2
            elif args[i] == "--force":
                force = True
                i += 1
            else:
                i += 1
        try:
            commands.cmd_serve(host, port, force=force)
        except RuntimeError as e:
            print(str(e), file=sys.stderr)
            sys.exit(1)

    elif args[0] == "models":
        if len(args) < 2:
            commands.cmd_models_list()
        elif args[1] == "list":
            commands.cmd_models_list()
        elif args[1] == "inscribe":
            if len(args) < 3:
                print('Usage: chess-harness models inscribe <id> [--name "Display Name"]')
                sys.exit(1)
            model_id = args[2]
            name = None
            if len(args) > 4 and args[3] == "--name":
                name = args[4]
            commands.cmd_models_inscribe(model_id, name)
        elif args[1] == "uninscribe":
            if len(args) < 3:
                print("Usage: chess-harness models uninscribe <id>")
                sys.exit(1)
            sys.exit(commands.cmd_models_uninscribe(args[2]))
        elif args[1] == "disable":
            if len(args) < 3:
                print("Usage: chess-harness models disable <id>")
                sys.exit(1)
            sys.exit(commands.cmd_models_set_enabled(args[2], False))
        elif args[1] == "enable":
            if len(args) < 3:
                print("Usage: chess-harness models enable <id>")
                sys.exit(1)
            sys.exit(commands.cmd_models_set_enabled(args[2], True))
        else:
            print(
                "Usage: chess-harness models list|inscribe <id>|uninscribe <id>|disable <id>|enable <id>"
            )
            sys.exit(1)

    elif args[0] == "audit":
        if len(args) < 2 or args[1] != "tail":
            print("Usage: chess-harness audit tail [n]")
            sys.exit(1)
        from .activity_audit import print_activity_tail

        n = int(args[2]) if len(args) > 2 else 50
        print_activity_tail(n)

    elif args[0] == "harness":
        if len(args) < 2 or args[1] != "reset":
            print("Usage: chess-harness harness reset [--yes]")
            sys.exit(1)
        sys.exit(commands.cmd_harness_reset(confirm="--yes" in args))

    elif args[0] == "migrate-results":
        commands.cmd_migrate_results()

    elif args[0] == "prune-no-result":
        dry_run = "--dry-run" in args
        export_snapshot = "--no-snapshot" not in args
        sys.exit(commands.cmd_prune_no_result(export_snapshot=export_snapshot, dry_run=dry_run))

    elif args[0] in ("analyse-quality", "quality-backfill"):
        game_id = None
        force = False
        i = 1
        while i < len(args):
            if args[i] == "--game-id" and i + 1 < len(args):
                game_id = args[i + 1]
                i += 2
            elif args[i] == "--force":
                force = True
                i += 1
            else:
                print(
                    "Usage: chess-harness analyse-quality [--game-id ID] [--force]"
                )
                sys.exit(1)
        sys.exit(commands.cmd_analyse_quality(game_id, force=force))

    elif args[0] in ("rebuild-estimation-samples", "rebuild-play-rating-samples"):
        sys.exit(commands.cmd_rebuild_estimation_samples())

    elif args[0] == "opponents":
        if len(args) < 2 or args[1] == "list":
            commands.cmd_opponents_list()
        elif args[1] == "verify":
            sys.exit(commands.cmd_opponents_verify())
        elif args[1] == "disable":
            if len(args) < 3:
                print("Usage: chess-harness opponents disable <id>")
                sys.exit(1)
            sys.exit(commands.cmd_opponents_set_enabled(args[2], False))
        elif args[1] == "enable":
            if len(args) < 3:
                print("Usage: chess-harness opponents enable <id>")
                sys.exit(1)
            sys.exit(commands.cmd_opponents_set_enabled(args[2], True))
        else:
            print("Usage: chess-harness opponents list|verify|disable <id>|enable <id>")
            sys.exit(1)

    elif args[0] == "tournament":
        if len(args) < 2:
            print("Usage: chess-harness tournament create|start|smoke|aggregate")
            sys.exit(1)
        sub = args[1]
        if sub == "create":
            opponents = args[2].split(",") if len(args) > 2 else ["stockfish:5"]
            print(json.dumps(commands.cmd_tournament_create(opponents), indent=2))
        elif sub == "start":
            commands.cmd_tournament_start()
        elif sub == "smoke":
            n = int(args[2]) if len(args) > 2 else 3
            print(json.dumps(commands.cmd_tournament_smoke(n), indent=2))
        elif sub == "aggregate":
            commands.cmd_aggregate()
        else:
            print("Unknown tournament subcommand")
            sys.exit(1)

    else:
        print("Chess Vision Harness — run: chess-harness new --model <id>")
        sys.exit(1)


if __name__ == "__main__":
    main()
