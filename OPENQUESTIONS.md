# Open Questions

1. Is "checking what moves are legal" really a strong handout to agents? Why are they struggling with that in the first place?

2. Should we explicitly allow that for all agents in the future and see what happens?

3. Should we also reintroduce a text-based "imagine" feature, so agents can explore lines?

4. Should effort level live in the agent id/name (e.g. `gpt-5.6-luna-max`), as a separate field on the inscribed model, or nowhere - always run highest effort? Different efforts can be legitimately different "players," but four ladder rows for one model family feels wrong. Highest effort is usually the real use of a model; some (e.g. Luna) are still useful and much cheaper at high/medium/max. What should the benchmark treat as the canonical identity?

5. Do we need another A/B row that never sends the board PNG and relies only on the text position (e.g. board.txt grid)? We need to know whether the image is actually helping, or whether models do worse because we send a picture at all?

6. Rename away from "Chess Vision Harness"? Candidates like "the chess harness," "Agentic Chess," or something shorter - what should the public name be?

