"""
Command-line interface for Chess Vision Harness.

Prefer `python play.py` for the canonical CLI. This entry point delegates to the same handlers.
"""

import argparse
import json
import sys

from . import bootstrap  # noqa: F401
from . import commands


def main():
    parser = argparse.ArgumentParser(
        description="Chess Vision Harness (use play.py for the canonical CLI)"
    )
    subparsers = parser.add_subparsers(dest="command")

    new_p = subparsers.add_parser("new")
    new_p.add_argument("--game", default=None)
    new_p.add_argument("--color", default=None, choices=["white", "black", "random"])
    new_p.add_argument("--skill", type=int, default=None, help="Deprecated: use --opponent stockfish:N")
    new_p.add_argument("--opponent", default=None)
    new_p.add_argument("--fen")
    new_p.add_argument("--model")
    new_p.add_argument("--force", action="store_true")

    for name in ("board", "move", "resign", "pgn", "status"):
        p = subparsers.add_parser(name)
        p.add_argument("--game", default="default")
        if name == "move":
            p.add_argument("move")

    subparsers.add_parser("list")
    subparsers.add_parser("leaderboard")
    subparsers.add_parser("aggregate")
    subparsers.add_parser("rebuild-elo")

    models_p = subparsers.add_parser("models")
    models_sub = models_p.add_subparsers(dest="models_cmd")
    models_sub.add_parser("list")
    inscribe_p = models_sub.add_parser("inscribe")
    inscribe_p.add_argument("model_id")
    inscribe_p.add_argument("--name", default=None)
    uninscribe_p = models_sub.add_parser("uninscribe")
    uninscribe_p.add_argument("model_id")

    harness_p = subparsers.add_parser("harness")
    harness_sub = harness_p.add_subparsers(dest="harness_cmd")
    reset_p = harness_sub.add_parser("reset")
    reset_p.add_argument("--yes", action="store_true")

    opp_p = subparsers.add_parser("opponents")
    opp_sub = opp_p.add_subparsers(dest="opponents_cmd")
    opp_sub.add_parser("list")
    opp_sub.add_parser("verify")

    serve_p = subparsers.add_parser("serve")
    serve_p.add_argument("--host", default="127.0.0.1")
    serve_p.add_argument("--port", type=int, default=8765)
    serve_p.add_argument("--force", action="store_true")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == "new":
        game_id = args.game or commands.default_game_id()
        print(json.dumps(
            commands.cmd_new(
                game_id, args.color, args.skill, args.fen, args.model, args.force, args.opponent
            ),
            indent=2,
        ))
    elif args.command == "board":
        print(json.dumps(commands.cmd_board(args.game), indent=2))
    elif args.command == "move":
        print(json.dumps(commands.cmd_move(args.game, args.move), indent=2))
    elif args.command == "resign":
        print(json.dumps(commands.cmd_resign(args.game), indent=2))
    elif args.command == "pgn":
        print(json.dumps(commands.cmd_pgn(args.game), indent=2))
    elif args.command == "status":
        print(json.dumps(commands.cmd_status(args.game), indent=2))
    elif args.command == "list":
        commands.cmd_list()
    elif args.command == "serve":
        commands.cmd_serve(args.host, args.port, force=args.force)
    elif args.command == "leaderboard":
        commands.cmd_leaderboard()
    elif args.command == "aggregate":
        commands.cmd_aggregate()
    elif args.command == "rebuild-elo":
        commands.cmd_rebuild_elo()
    elif args.command == "models":
        if args.models_cmd == "inscribe":
            commands.cmd_models_inscribe(args.model_id, args.name)
        elif args.models_cmd == "uninscribe":
            sys.exit(commands.cmd_models_uninscribe(args.model_id))
        else:
            commands.cmd_models_list()
    elif args.command == "harness":
        if args.harness_cmd == "reset":
            sys.exit(commands.cmd_harness_reset(confirm=args.yes))
        parser.print_help()
        sys.exit(1)
    elif args.command == "opponents":
        if args.opponents_cmd == "verify":
            sys.exit(commands.cmd_opponents_verify())
        commands.cmd_opponents_list()


if __name__ == "__main__":
    main()
