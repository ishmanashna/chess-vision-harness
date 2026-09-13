# Open Questions

1. Is "checking what moves are legal" really a strong handout to agents? Why are they struggling with that in the first place?

2. Should we explicitly allow that for all agents in the future and see what happens?

3. Should we also reintroduce a text-based "imagine" feature, so agents can explore lines?

4. Should effort level live in the agent id/name (e.g. `gpt-5.6-luna-max`), as a separate field on the inscribed model, or nowhere - always run highest effort? Different efforts can be legitimately different "players," but four ladder rows for one model family feels wrong. Highest effort is usually the real use of a model; some (e.g. Luna) are still useful and much cheaper at high/medium/max. What should the benchmark treat as the canonical identity?

5. Do we need another A/B row that never sends the board PNG and relies only on the text position (e.g. board.txt grid)? We need to know whether the image is actually helping, or whether models do worse because we send a picture at all?

6. Rename away from "Chess Vision Harness"? Candidates like "the chess harness," "Agentic Chess," or something shorter - what should the public name be?

7. What should this site become? Three lanes that all seem viable: (1) a serious agent chess benchmark, (2) a fun and straightforward way to play a chess game with your agent, (3) a place where humans and agents mingle - a kind of Lichess that natively supports agents (queue, match, maybe vs Fable). All three are acceptable; pulling off all three would be ideal. Which to prioritize, and can they share one product without watering each other down?

8. Fun-lane friction: Create Game / Playground / Inscribe Agent is still too much bureaucracy. Ideal is almost no UI - "just tell your agent" and it hands you a spectator/play link (or the page redirects). A giant one-click button is the fallback if humans need a door. How far can we collapse the flow without breaking the benchmark spine? Sign-in that binds a human account to "their" agent (by account name / Google, without a separate agent API key ceremony) is one path - is that enough?

9. Where should rough cost / token / time-to-move estimates live publicly? Not a new Benchmark column - maybe a Leaderboards / Ops-style tables tab fed from experiments (e.g. Composer load-and-burn). What is good enough to show without pretending we have provider-meter truth?

10. ChessBench-style "field-relative Elo" vs our human-anchored AvE ladder: how loudly should the homepage contrast that (beyond the current human-ratings line)? Any other transparency lines the home tab still needs?

11. Track time per move (wall-clock per ply / per agent turn) so we can see when models stall or think forever - surface it for seats and for comparing providers.
