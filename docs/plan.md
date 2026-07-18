# Plan: Markdown-only repo root

Status: **implemented** (2026-07-18)

## Goal

Repo root contains **only** `*.md` files and directories. Remove every other root file. No exceptions.

## Done when

- `ls` at repo root shows six markdown files plus folders only.
- `pip install -e python/` works; `chess-harness --help` works.
- `python scripts/quality_gate.py` passes (after line-limit debt is unchanged or fixed separately).
- CI green on Ubuntu + Windows.
- README install/quick-start updated; no references to root `play.py`, root `opponents.json`, or root Node config.

## Target tree

```
chess-vision-harness/
  AGENTS.md
  ARCHITECTURE.md
  NOTICE.md
  ORCHESTRATOR.md
  PRODUCT.md
  README.md
  bin/
    .gitignore
  config/
    opponents.json
    models.json.example
    mcp.json.example
  docs/
    LICENSE.md              # moved from root LICENSE
    plan.md
    …
  elo_calibration/
    …
  frontend/
    .gitignore
    package.json
    package-lock.json
    tsconfig.json
    eslint.config.js
    src/
      placeholder.ts
  python/
    .gitignore
    pyproject.toml
    src/chess_harness/
    tests/
      fixtures/models.json
  scripts/
    check_line_limits.py
    quality_gate.py
    serve.bat               # moved from root
    test.bat                # moved from root
    …
```

Delete empty `web/` and root `src/`, `tests/`, `node_modules/` after moves.

## Phase 1 — Create homes and move files

Move without logic changes first (git mv where possible):

| From (root) | To |
|-------------|-----|
| `src/` | `python/src/` |
| `tests/` | `python/tests/` |
| `pyproject.toml` | `python/pyproject.toml` |
| `opponents.json` | `config/opponents.json` |
| `models.json.example` | `config/models.json.example` |
| `mcp.json.example` | `config/mcp.json.example` |
| `models.json` | `.chess_harness/models.json` (runtime; already gitignored) |
| `package.json`, `package-lock.json`, `tsconfig.json`, `eslint.config.js` | `frontend/` |
| `frontend/placeholder.ts` | `frontend/src/placeholder.ts` |
| `serve.bat`, `test.bat` | `scripts/` |
| `LICENSE` | `docs/LICENSE.md` |
| `play.py` | **delete** (no shim at root) |
| `.gitignore` | **delete** — replaced by nested ignores (phase 2) |

Update `python/pyproject.toml`:

- `readme = "../README.md"`
- `[tool.pytest.ini_options] testpaths` unchanged relative to `python/`
- Hatch `packages` still `src/chess_harness`

## Phase 2 — Nested `.gitignore` (no root ignore file)

Split current root `.gitignore` into:

| File | Patterns |
|------|------------|
| `python/.gitignore` | `__pycache__/`, `*.py[cod]`, `.pytest_cache/`, `.venv/`, `venv/`, `*.egg-info/`, `.env` |
| `frontend/.gitignore` | `node_modules/` |
| `bin/.gitignore` | `**/*.exe`, `stockfish*`, `opponents/**` with `!opponents/LICENSES.md` |
| `.chess_harness/.gitignore` | `*` (ignore all runtime data; keep committed fixtures elsewhere) |
| `elo_calibration/results/.gitignore` | same allow-list as today for `merged_ratings.json`, `continuous/` |

Add `scripts/check_clean_root.py`: fail if any non-`*.md` **file** exists at repo root (allow only directories). Wire into `quality_gate.py`.

## Phase 3 — Path resolution

Update `python/src/chess_harness/paths.py`:

- `project_root()` → parent of `python/` (four levels up from `paths.py`, or explicit `python/` sibling detection).
- `resolve_opponents_file()` → `<repo>/config/opponents.json`
- `resolve_models_file()` → `<repo>/.chess_harness/models.json` (create from example on first use if missing)
- `resolve_base_dir()` → `<repo>/.chess_harness/` (unchanged semantics)
- `resolve_stockfish()` → `<repo>/bin/...` (paths use `project_root()`)

Grep and fix hardcoded `opponents.json`, `models.json`, `play.py`, root-relative assumptions in:

- `python/src/chess_harness/*`
- `scripts/*`
- `elo_calibration/*`
- `docs/*`, `README.md`, `AGENTS.md`
- `.github/workflows/test.yml` — set `MODELS_FILE=python/tests/fixtures/models.json`, `OPPONENTS_FILE=config/opponents.json`, run pytest from `python/` or with `cd python && pytest`

## Phase 4 — CLI and docs

- Canonical install: `pip install -e python/`
- Canonical commands: `chess-harness …`, `chess-harness-mcp`, `python -m chess_harness`
- README quick start: replace every `python play.py` with `chess-harness`
- AGENTS.md: same
- `NOTICE.md`: point license to `docs/LICENSE.md`
- `scripts/quality_gate.py`: `npm`/`tsc`/`eslint` cwd = `frontend/`; pytest cwd = `python/`
- `scripts/check_line_limits.py`: scan repo but skip `node_modules`, `.chess_harness`, etc.
- `serve.bat` / `test.bat`: update paths

## Phase 5 — Verify

```bash
pip install -e python/
pip install -e "python/[dev]"
python scripts/check_clean_root.py
python scripts/quality_gate.py
cd python && pytest -q
```

Manual: `chess-harness serve --force`, open calibration page, one `chess-harness new` smoke.

## Out of scope

- Splitting oversized Python files for the 300-line limit (separate work).
- Roadmap Plan 0 `GameService` refactor.
- Moving `elo_calibration/` under `python/` (stays top-level folder).

## Estimated duration

| Phase | Agent-hours |
|-------|-------------|
| 1 — Move files | 1–2 |
| 2 — Nested gitignore + root checker | 1–2 |
| 3 — Path resolution + grep fixes | 2–4 |
| 4 — CLI + docs + quality gate | 2–3 |
| 5 — Verify + CI | 1–2 |
| **Total** | **7–13** |
