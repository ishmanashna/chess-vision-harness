#!/usr/bin/env python3
"""Chess Vision Harness — play chess vs catalog opponents via board images."""

import json
import sys

# Bootstrap paths and Stockfish before other imports
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent / "src"))
import chess_harness.bootstrap  # noqa: F401

from chess_harness import commands


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


def main():
    args = sys.argv[1:]

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
            print("Usage: python play.py move <game_id> <move>")
            sys.exit(1)
        print(json.dumps(commands.cmd_move(args[1], args[2]), indent=2))

    elif args[0] == "pgn":
        if len(args) < 2:
            print("Usage: python play.py pgn <game_id>")
            sys.exit(1)
        print(json.dumps(commands.cmd_pgn(args[1]), indent=2))

    elif args[0] == "game":
        if len(args) < 3 or args[1] != "audit":
            print("Usage: python play.py game audit <game_id>")
            sys.exit(1)
        print(json.dumps(commands.cmd_game_audit(args[2]), indent=2))

    elif args[0] == "resign":
        if len(args) < 2:
            print("Usage: python play.py resign <game_id>")
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

    elif args[0] == "rating":
        if len(args) < 3 or args[1] != "--model":
            print("Usage: python play.py rating --model <name>")
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
                print("Usage: python play.py models inscribe <id> [--name \"Display Name\"]")
                sys.exit(1)
            model_id = args[2]
            name = None
            if len(args) > 4 and args[3] == "--name":
                name = args[4]
            commands.cmd_models_inscribe(model_id, name)
        elif args[1] == "uninscribe":
            if len(args) < 3:
                print("Usage: python play.py models uninscribe <id>")
                sys.exit(1)
            sys.exit(commands.cmd_models_uninscribe(args[2]))
        else:
            print("Usage: python play.py models list|inscribe <id>|uninscribe <id>")
            sys.exit(1)

    elif args[0] == "harness":
        if len(args) < 2 or args[1] != "reset":
            print("Usage: python play.py harness reset [--yes]")
            sys.exit(1)
        sys.exit(commands.cmd_harness_reset(confirm="--yes" in args))

    elif args[0] == "migrate-results":
        commands.cmd_migrate_results()

    elif args[0] == "opponents":
        if len(args) < 2 or args[1] == "list":
            commands.cmd_opponents_list()
        elif args[1] == "verify":
            sys.exit(commands.cmd_opponents_verify())
        else:
            print("Usage: python play.py opponents list|verify")
            sys.exit(1)

    elif args[0] == "tournament":
        if len(args) < 2:
            print("Usage: python play.py tournament create|start|smoke|aggregate")
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
        print(__doc__ or "Chess Vision Harness — run: python play.py new")
        sys.exit(1)


if __name__ == "__main__":
    main()
