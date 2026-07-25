# PRODUCT

## What this is

A fair chess benchmark for vision-capable AI agents. Agents see the board as an image, choose a move, and play against a ladder of rated opponents. Humans can watch games and compare agents on a shared leaderboard.

**Public URL today:** [https://chessvisionharness.pages.dev](https://chessvisionharness.pages.dev) — always-on site; live games when the operator’s game server is Online (see [`DEPLOY.md`](DEPLOY.md)).

## Why it exists

Most agent “chess” demos leak the position as text or let the model call an engine. That measures tooling, not vision and play. This project forces the hard path: look at the board, move, repeat — with illegal moves rejected and no hidden shortcuts.

## Desired product

A public, copyable vision-chess benchmark people trust:

- Anyone can bring an agent, start a rated game, and finish it under the same rules (public Create Game + `/api/v1`, or local CLI/MCP).
- Results update a shared agent ladder (live on the game host; published snapshot on the public site).
- Operators can watch live games and review finished ones.
- Opponent strength is honest — calibrated engines from strong down through random and worse — so a weak agent faces weak opponents, not a world champion by accident.
- Later: the harness can call models itself for batch benchmarks; agents can play each other; a human can play an agent in the browser. Live viewing stays on Twitch (or similar), not a custom stream stack.

The north star is simple: **bring an agent, play fair rated games, see where you stand.**

## Who it’s for

- **Operators** — run the benchmark, tune opponents, watch and validate games.
- **Agent builders** — plug in a vision model and measure real play strength.
- **Outsiders** — reproduce results and compare agents under the same contract.

## What success looks like

- Agents that only see the board can complete honest games end to end.
- Rankings reflect play, not leaked state or engine help.
- Opponent difficulty matches the agent’s level in a sensible way.
- A stranger can understand the offer without reading the codebase: play, watch, compare.

## What we are not building

- Screen-clicking / computer-use bots
- Online matchmaking or official human ratings
- Training models inside this repo
- In-app live streaming (operators use Twitch or screen share)
- A product that rewards cheating the vision contract
