# Local prompt test

Same model, several extra texts (or one committee), engine games only, on this PC. You say which packs to run. Subagents play through normal local commands (`chess-harness` / MCP). A local Ops table compares them: games, results, Accuracy, Performance. The public ladder, published snapshots, and Elo do not move.

The player is a chat agent. It looks at `board.png` and talks to the server. There is no model-API reply to parse.

Packs are not hardcoded to four letters. The first roster is `a` `b` `c` `d` `e`. Adding `f` is a new file plus an index row.

## Scope

- AvE only, localhost.
- A pack registry: any non-empty subset (`--packs a,c` or `a,b,c,d,e` or later `f`).
- Two kinds: **overlay** (one subagent + extra text) and **committee** (three subagents, internal thread, think / discuss / vote; the harness plays the winning move).
- Tagged unrated games so the table can accumulate without touching Elo or the public benchmark.
- CLI `new --prompt-pack <id>` and `prompt-test start --packs …`. MCP `chess_new_game` takes the same pack id.
- Overlay play: `board` / `status` / `move` (or MCP). Position from the PNG only.
- Committee play: `board` / `status` plus thread commands. Not `move`.
- Ops tab: one row per pack id that has games.
- Chat: orchestrator launches the matching number of Composer 2.5 subagents. `prompt-test start` only creates games and prints briefs.

## Out of scope

- The internal API runner (OpenAI adapter, scraping UCI from a chat completion). Do not change it for this.
- Public Create Game and paste briefs.
- Leaderboard rows, Elo, published snapshots, Pages UI, git-tracked `finished_games.sqlite` rows for these games.
- Puzzles, identify, AvA, Playground.
- A headless farm that calls a vendor model itself.
- Public or spectator chat. The committee thread is localhost operator data only.

## Product decisions (locked)

1. **Subagents are the players.** Overlay agents read the PNG and `move`. Committee agents read the PNG, post and vote; they do not `move`. No parsing of model prose. Illegal AvE moves stay rejected; that ply is voted again (committee) or the agent tries another move (overlay). The game continues.

2. **Pack ids, not a fixed ABCD.** `config/prompt_packs/index.json` plus `{id}.txt`. Unknown id fails before create. `--packs` is a list. One inscribed model; tag on game and result row (`prompt_pack`, `prompt_pack_hash`). Hash is the `{id}.txt` body only, not `_rules.txt`.

3. **Kinds.** `overlay`: one seat. `committee`: `seats` (3 for `e`). Do not special-case the letters a–e in code. **Reject `kind=committee` at create until Phase 5** (CLI, MCP, HTTP). Phase 1–4 must not start a one-seat `e` game.

4. **Unrated and off every public number.** Packed finish sets `rated: false`. **Do not call `elo.record_game`** — it ignores `rated`. Skip it on **`_finish_game` and `resign`**. Skip `request_public_snapshots_refresh`. Skip `finished_games_db.record_scored_finish` (git-tracked SQLite). `count_scored_by_model` and `aggregate_quality_by_model` skip packed rows (`rated: false` is not enough — those aggregators still count AvH). `schedule_game_quality` still runs.

5. **Create is local.** `--prompt-pack` on `cmd_new` → `GameService.new_game` → `BoardController.new_game` and onto `state.json`. MCP `chess_new_game` same field. Loopback-only `POST /api/v1/games` (`CreateGameBody` + `host_is_loopback`); off loopback, reject.

6. **Briefs: rules first, then the pack is the turn.** Overlay brief = `_rules.txt` + pack body. **`a.txt` is the baseline turn loop** (read PNG, then move). B/C/D *are* their turn loops (they end with `move`). Do not put “send a move” in `_rules.txt` or B/D will be ignored. Committee brief = `_committee_rules.txt` + `e.txt` (no `move`).

7. **Restart is an exact command.** After `game_over`, run `chess-harness new --model {model_id} --prompt-pack {id}` (committee: same, then keep the same seat). Use the new `game_id` and `board_path` from that JSON. Do not reuse the finished id. Idle is 30 minutes without a **played** move.

8. **Committee idle.** `say` and `vote` call the same activity touch as a successful create, so discussion does not die at 30 minutes of talk. `status` / `board` still do not reset the clock. A played majority move resets as today.

9. **Ops is where you look.** Tab **A/B**: one row per pack id. Counts, W/D/L, mean Accuracy, mean Performance, localhost `/g/{id}` links. Poll. No start button. Packed games **do not** appear on the Ops Activity live-games list (that list uses the public builder today).

10. **Default opponent matching stays.** Same engines as a normal local `new` unless `--opponent` is passed.

11. **Public watch is off, all spectator doors.** Non-loopback 404/omit packed games on `GET /api/games`, `GET /api/games/{id}/state`, moves, pgn, eval, and `/g/{id}` HTML **and** `/g/{id}/board.png`. One shared helper (`host_is_loopback` is Host-header only — Pages proxy is not loopback). Watching packed games means `http://127.0.0.1:8765`, not the public site while Online.

12. **Committee thread** under `.chess_harness/prompt_test/{game_id}/`, not the game folder. Every message and vote carries **`ply`** (agent ply index). `thread` returns the current ply and only that ply’s notes/votes by default. No FEN, no legal-move lists, no `state.json`.

13. **Committee move path.** `chess-harness move` and MCP `chess_make_move` reject committee games. Majority play uses an **internal AvE executor** (same agent+engine chain as `make_agent_move`, under `game_lock`) that the committee guard does not block. Two matching votes on the **current ply** play that UCI. A third vote after the ply is closed is rejected. Two votes arriving together: one play, idempotent. 1-1-1 after three votes: `tied`, no move. Illegal: `rejected`, clear votes, ply stays open. Software does **not** wait for three think notes; two agreeing votes can play. The prompt still asks them to think first.

14. **Forbidden extras.** Packs and rules ban `imagine` / `chess_imagine_board`, `pgn`, `game audit`, engines, `state.json`, spectator `/api/games/*`, operator commands.

## Pack texts (copy into files)

Copy these bodies into `config/prompt_packs/`. Do not paraphrase. Index titles: A Baseline, B Verify, C Principles, D Slow, E Committee.

### `_rules.txt`

```
You are playing an engine game on this machine. Image-first: the position is the board PNG. Do not cheat.

Game id: {game_id}
Model id: {model_id}
Board PNG: {board_path}
White is at the bottom. Square names are absolute. a1 is the bottom-left square of the image even when you play Black.

Your color and whether it is your turn come from chess-harness status {game_id}. That command is metadata only (your_turn, result, in_check). It is not the piece placement. chess-harness board {game_id} reprints the PNG path.

How you choose a move is in the instructions after this block. Follow those before you send a move.

Prefer UCI (e2e4, g1f3, e7e8q). SAN is fine if it is unambiguous.
If a move is rejected, look at the PNG again and try another. The game continues.
If it is not your turn, wait. Do not move for the engine.

When status says game_over, start a new game with this exact command, then use the new game_id and board_path from the JSON:
  chess-harness new --model {model_id} --prompt-pack {prompt_pack}
Keep going until you are told to stop. Do not reuse the finished game id.

Never read state.json, game.pgn, results.jsonl, or FEN. Never call spectator /api/games/*. Never run an engine or a script to pick moves or list legal moves. Never chess-harness imagine or MCP chess_imagine_board. Never chess-harness pgn or chess-harness game audit. Never operator commands (serve, harness reset, models uninscribe, calibration).

If you go 30 minutes without a move that the harness accepts, the game dies with no result. Do not resign to skip a hard position.
```

### `a.txt`

```
Each turn, until the game is over:

1. Read the board PNG at {board_path}. Do not skip this. Do not reuse an old image.
2. Send one move: chess-harness move {game_id} <move>
```

### `b.txt`

```
Before you send a move, run this list. Do not skip a step. Do it from the PNG, not from what you expect the position to be.

1. Where is every piece?
   Scan the image. White at the bottom, files a→h left to right, ranks 1 at the bottom. For each occupied square, name the piece and the square. If you cannot place every piece, scan again. Do not continue with a partial board.

2. Who am I, and whose turn is it?
   Your color is from status / the game you were given, not from “White sits at the bottom.” Confirm it is your turn. If it is not, wait.

3. What did the opponent just do?
   Find the move that changed the picture. Which piece left which square, and where did it go? What does that change: new attacks, opened or closed lines, a capture, a check?

4. Am I in check?
   Decide from the PNG. If the king is attacked, say so. Which enemy piece(s) check it? The move you play must get out of check (block, capture the checker, or move the king). If you are not in check, say that too.

5. What checks me if I am sloppy?
   Which of their pieces already look at my king, or would if I moved a blocker? Do not walk into a check you can see.

6. Which of my pieces are under threat?
   For each of my pieces: is it attacked? By which pieces? List the attackers.

7. Which of their pieces are under threat?
   Same question for their side. List the attackers on each threatened piece.

8. Are those threats real? (both sides — same questions for my pieces and for theirs)
   For every threatened piece:
   - Is it defended at all? By which pieces?
   - Is it sufficiently defended? Count attackers vs defenders. More attackers than defenders is a problem unless the extra attackers are too valuable to recapture with.
   - Walk the taking sequence on that square: they take, we recapture, they recapture, and so on, in a sensible order (usually cheapest attacker first). Add up the material that would come off. Would we lose more than they do, or the other way around?
   - Threat level: hanging (attacked, not defended) is the worst. Then “they take something worth more than they give back” (e.g. pawn takes queen, or a recapture chain that leaves us down). Equal trades are weaker threats. A piece attacked only by something we would gladly trade for is not the same as a hang.
   Do this for captures I could make and for captures they could make. Do not stop after naming “it’s attacked.”

9. Candidate moves
   From the picture, list a few concrete moves (from-square, to-square, piece). Checks, saving a piece that fails step 8, and captures that win the exchange in step 8 come before quiet ideas. Do not invent a piece that is not in the PNG.

10. Pick one candidate and verify it
    The piece is on the from-square. The path is free if it must be. After this move I am not in check. Step 8 still looks acceptable for the new picture (I did not hang, I did not enter a losing recapture). I am not leaving an obvious mate. If any of that fails, pick another candidate and verify that one.

11. Play the move
    chess-harness move {game_id} <uci>
```

### `c.txt`

```
Play real chess, not a random legal move. Read the PNG first. Then choose using these principles. Then send chess-harness move {game_id} <uci>.

Every move. Checks, captures, and threats first. If they have a check, a hang, or a mate threat, that is the problem — not your long-term plan. If you have a free piece or a forcing win of material, take it unless you see a direct mate you are walking into.

King. King safety beats a pretty center. Do not leave the king in the middle behind open files because development looks nice. Castle when it is actually safe, not on autopilot. Do not rip pawns off your own king for no reason.

Opening (while many pieces are still home). Develop. Knights and bishops off the back rank, king toward safety, do not move the same piece twice unless you must. Do not hunt early queen adventures. Occupy or pressure the center (e- and d-files) with pieces and pawns; do not fling wing pawns instead of developing.

Middlegame. Put pieces on squares where they do something: attack a weak pawn, a pinned piece, an uncastled king, an open file. Trade when you are ahead or when their best piece is the one coming off. Do not trade your last defender. Improve the worst piece before starting a new pawn storm.

Pawns. Pawns do not go backwards. Think once before pushing. Isolated, doubled, and backward pawns are long-term weaknesses; giving them away for nothing is how you lose slowly. Passed pawns become the plan in simplified positions.

Endgame. If queens are off, the king is a piece — bring it forward. Promote passed pawns. Do not wander. If you are a piece up, trade pieces (not always pawns). If you are a piece down, keep pawns messy and avoid a clean conversion.

Tempo. A check that does nothing and a threat you cannot carry out are not “active.” One quiet improving move is better than three loud ones that hang.

You will not calculate like an engine. You will not get a legal-move list. You will look at the PNG, pick a move that does not blunder, and that follows this order: safety, material, activity, then pawn structure.
```

### `d.txt`

```
This is a real game. It is worth sitting with. Read the PNG. Do not send a move until you have done the rest of this block. Then chess-harness move {game_id} <uci>.

Look at the whole board. Whose turn. Your king. Their king. Every piece that can be taken. Then look a second time — the first pass misses things.

Think it through in words: what changed last move, what they want, what you want, then pick one move. If two moves look equal, wait anyway and check whether one of them hangs.

Do not play a move because it sounds like chess. “Develop the knight,” “play the Italian,” “occupy the center,” “castle because that is what you do” are names and slogans. They are not this position. If the PNG does not support it this turn — you hang, you ignore a check, you miss a capture, you move a piece that is not there — it is a bad move. The board in front of you beats every principle and every opening name.

Take as long as you need. A careful move beats a fast one. There is no prize for finishing the turn quickly.

You are allowed to be unsure. Unsure means look at the image again, not guess.
```

### `_committee_rules.txt`

```
You are playing an engine game on this machine with two other seats. Image-first: the position is the board PNG. Do not cheat.

Game id: {game_id}
Model id: {model_id}
Board PNG: {board_path}
Seat: {seat}
White is at the bottom. Square names are absolute. a1 is the bottom-left square of the image even when you play Black.

You never send chess-harness move or MCP chess_make_move. The harness plays after a vote.

Your color and whether it is your turn: chess-harness status {game_id} (metadata only). chess-harness board {game_id} reprints the PNG path.

Thread (current ply only unless you ask otherwise):
  chess-harness prompt-test thread {game_id}
  chess-harness prompt-test say {game_id} {seat} <text>
  chess-harness prompt-test vote {game_id} {seat} <uci>

When status says game_over, start a new game:
  chess-harness new --model {model_id} --prompt-pack {prompt_pack}
Keep the same seat. Use the new game_id and board_path. Do not reuse the finished id. Continue until you are told to stop.

Never read state.json, game.pgn, results.jsonl, or FEN. Never call spectator /api/games/*. Never run an engine or list legal moves. Never chess-harness imagine or MCP chess_imagine_board. Never chess-harness pgn or game audit. Never operator commands.

Talk and votes keep the game alive. A 30-minute gap with no say, vote, or played move still kills the game with no result. Do not resign to skip a hard position.
```

### `e.txt`

```
You are one of three seats (your seat number is above). You are equals.

Each ply, in this order:

1. Think
   Read the board PNG for this ply. Post a note with say. Say what you see, a candidate UCI, and why. Do not vote yet. Read the thread. If another seat has not posted yet, wait a bit and read again, then continue — do not wait forever.

2. Discuss
   Reply with say. Argue from the picture. You may change your candidate.

3. Vote
   chess-harness prompt-test vote {game_id} {seat} <uci>
   Exactly one move. You may change your vote by voting again before a winner is played. Two matching votes on this ply are enough; the harness will play even if the third seat has not voted.

4. Winner
   After a move is played, read the PNG again. Do not vote the old ply. thread tells you the current ply.
   If the thread says tied (three different votes), discuss and vote again until two agree.
   If the thread says rejected, the ply is still open. Look at the PNG and vote again.
```

## Phase 1 — Registry, files, tagged overlay `new`

**Goal:** Index + pack files. Overlay `new --prompt-pack b` tags a game. Unknown ids fail. Committee ids fail at create.

**Work**

- Write `config/prompt_packs/` from **Pack texts** (`index.json`, `_rules.txt`, `_committee_rules.txt`, `a`–`e.txt`).
- Loader: id → kind, seats, body, hash of `{id}.txt`. Unknown id errors. Committee id errors with “not available until committee play exists” (remove that reject in Phase 5).
- Thread `prompt_pack` through `__main__.py` `_parse_new_opts`, `cmd_new`, `GameService.new_game`, `BoardController.new_game` onto state (`prompt_pack`, `prompt_pack_hash`, `prompt_pack_kind`).
- MCP `chess_new_game` same field, same reject for committee.
- Loopback `POST /api/v1/games` body field + `host_is_loopback`.

**Done when:** `new --model <id> --prompt-pack b` stores `b` and the hash of `b.txt`. `a` is valid. `nope` fails. `e` fails. Untagged `new` unchanged.

**Verify:** Loader and `new` tests in a temp harness dir. Do not run the full suite.

## Phase 2 — Off the public numbers, still graded

**Goal:** Packed games never change Elo, live leaderboard means, published snapshots, or `finished_games.sqlite`. Moves still get Accuracy and Performance. The public site cannot see them through any spectator door.

**Work**

- `_result_row_base` copies `prompt_pack`, `prompt_pack_hash`, `rated: false` from state.
- `_finish_game` **and** `resign`: skip `elo.record_game`, skip snapshot refresh, skip `record_scored_finish`. Still `schedule_game_quality`.
- `count_scored_by_model` and `aggregate_quality_by_model` skip packed rows.
- Shared spectator helper: non-loopback packed → omit/404 on list, state, moves, pgn, eval, HTML `/g/`, board PNG. Loopback allowed.
- Packed games omitted from Ops Activity’s live list (A/B tab is Phase 4).

**Done when:** Packed overlay AvE finish **and** resign: tagged row, `rated: false`, quality fields, Elo unchanged, sqlite unchanged, live leaderboard means unchanged. Non-loopback list/state/PNG 404. Loopback watch works. Untagged `new` still rates and sqlite-writes.

**Verify:** Finish + resign tests. Host-header tests on list, state, and board image. Do not run the full suite.

## Phase 3 — Start helper for any overlay set

**Goal:** `prompt-test start --model <id> --packs a,c,d` creates those games and prints briefs. Does not play.

**Work**

- Brief renderer: `_rules.txt` + pack body, fill `{game_id}`, `{board_path}`, `{model_id}`, `{prompt_pack}`.
- `chess-harness prompt-test start --model <id> --packs …`. Overlay only. JSON per game: ids, paths, `kind`, full brief. Committee in the list → error (until Phase 5).
- `__main__.py` dispatches `prompt-test`.

**Done when:** Temp dir, `--packs a,b,c,d` four games four briefs (each brief contains `_rules` then that pack). `--packs a,c` two. `--packs e` errors. Runner untouched.

**Verify:** Temp-dir CLI tests. Do not run the full suite.

## Phase 4 — Ops table

**Goal:** Ops shows one row per pack id that appears in tagged games.

**Work**

- Loopback `GET /api/ops/prompt-test`: per id, title from index if known, in-progress (from game list + pack tag), finished (exclude `*`), W/D/L, mean Accuracy, mean Performance, recent ids.
- Ops tab **A/B**. Dynamic rows. Poll ~10s.
- Pages already blocks `/ops*`.

**Done when:** Packed games show as rows matching tags. Pages `/ops/` stays 404.

**Verify:** Snapshot JSON from fixtures with two and with five pack ids. Loopback HTML/JS. Do not run the full suite.

## Phase 5 — Committee pack (`e`)

**Goal:** Three subagents share a ply-scoped thread. Majority vote plays through the internal AvE executor. `start` may include `e` (three briefs, one game).

**Work**

- Allow `kind=committee` at create. Storage `.chess_harness/prompt_test/{game_id}/`.
- CLI: `thread`, `say`, `vote`. Each record has `ply`. `say`/`vote` touch activity. JSON, no FEN.
- Vote under `game_lock`. Majority on current ply → internal executor (not `cmd_move`). Closed ply rejects further votes. Illegal → `rejected`, clear votes. 1-1-1 → `tied`.
- `cmd_move` / `chess_make_move` reject committee games.
- Briefs: `_committee_rules.txt` + `e.txt`, `{seat}` 1–3. `start --packs e` or mixed with overlays.
- Orchestrator (not this phase’s coding) launches three Composer 2.5 subagents for `e`.

**Done when:** Temp-dir: two votes `e2e4` on ply 0 play that move and the engine replies. Third vote after play is rejected. 1-1-1 stays tied. Direct `move` fails. `say` without a move does not idle-kill in a short test (activity touched). `start --packs e` returns three seats and one `game_id`.

**Verify:** Committee CLI tests with stub or tiny AvE. Do not run the full suite.

## Estimated duration

- Phase 1: 2.5–4 agent-hours
- Phase 2: 4–6 agent-hours
- Phase 3: 2–3.5 agent-hours
- Phase 4: 2–3.5 agent-hours
- Phase 5: 5–7 agent-hours
