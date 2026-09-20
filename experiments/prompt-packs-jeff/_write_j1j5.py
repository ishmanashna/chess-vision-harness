from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACKS = ROOT / "config" / "prompt_packs"
ADAPTERS = ROOT / "python" / "src" / "chess_harness" / "runner" / "adapters"
PROMPT_PACKS_PY = ROOT / "python" / "src" / "chess_harness" / "prompt_packs.py"
EXP = ROOT / "experiments" / "prompt-packs-jeff"

# --- pack bodies ---
BODIES = {
    "j1": """Jeff J1 baseline. You only pick among legal UCI moves.

Priorities: stop mate threats and checks against you; take free material; make a safe improving move; avoid hanging pieces.

Do not narrate. Do not invent moves outside the option list.
""",
    "j2": """Jeff J2 careful. Prefer a solid non-hanging move over a flashy one.

Look twice for checks, captures, and threats. If two moves look equal, pick the one that loses less if you misread. No opening names as excuses.

You only pick among legal UCI moves. Do not narrate.
""",
    "j3": """Jeff J3 phase seat (spirit is chosen in code by opening/middlegame/endgame and material).

Fallback if no phase tag: stop mate threats; take free material; safe improving move; avoid hanging pieces. Legal UCI only.
""",
    "j4": """Jeff J4 checklist seat. Follow the checklist answers already given in the note when picking the final move.

Legal UCI only. Prefer moves that respect: escape check, stop mate threats, avoid losing exchanges, take equal-or-better when safe.
""",
    "j5": """Jeff J5 propose-and-check seat. When asked for a move, pick the best legal UCI. When asked to compare two boards, answer only with the labeled options.
""",
}

# Phase advice snippets for J3 (injected by adapter)
PHASE_DIR = PACKS / "j3_phases"
PHASE_DIR.mkdir(parents=True, exist_ok=True)
PHASE_TEXTS = {
    "opening_even": "Phase: OPENING. Material: EVEN.\nDevelop, castle when safe, fight for the center, do not hang pieces. Prefer developing moves over early queen adventures.",
    "opening_ahead": "Phase: OPENING. Material: AHEAD.\nYou are up material. Develop safely, castle, trade pieces when it simplifies without returning the edge. Do not get fancy.",
    "opening_behind": "Phase: OPENING. Material: BEHIND.\nYou are down material. Develop, castle, seek counterplay and complications carefully. Avoid further free losses.",
    "middle_even": "Phase: MIDDLEGAME. Material: EVEN.\nKing safety first, then material, then activity. Look for tactics; improve worst piece; do not hang.",
    "middle_ahead": "Phase: MIDDLEGAME. Material: AHEAD.\nYou are up material. Simplify when safe, stop counterplay, trade pieces not pawns if it reduces their attack.",
    "middle_behind": "Phase: MIDDLEGAME. Material: BEHIND.\nYou are down material. Create threats, avoid passive trades, look for tactics or perpetual chances. Do not collapse.",
    "end_even": "Phase: ENDGAME. Material: EVEN.\nActivate king, push passed pawns, centralize. Avoid random checks. Trade into known draws only if needed.",
    "end_ahead": "Phase: ENDGAME. Material: AHEAD.\nConvert: cut the enemy king off, shrink the box, bring your king, promote/mate. Do not check forever without tightening.",
    "end_behind": "Phase: ENDGAME. Material: BEHIND.\nFight for a draw: activate king, blockade passers, seek stalemate or perpetual if available. Do not resign by hanging more.",
}
for name, text in PHASE_TEXTS.items():
    (PHASE_DIR / f"{name}.txt").write_text(text.strip() + "\n", encoding="utf-8")

# Archive old j2 double-board body if still the double one
old_j2 = PACKS / "j2.txt"
if old_j2.exists() and "double-board" in old_j2.read_text(encoding="utf-8").lower():
    (PACKS / "j2_double.txt").write_text(old_j2.read_text(encoding="utf-8"), encoding="utf-8")

for pid, body in BODIES.items():
    (PACKS / f"{pid}.txt").write_text(body.strip() + "\n", encoding="utf-8")

# Update index.json
idx_path = PACKS / "index.json"
idx = json.loads(idx_path.read_text(encoding="utf-8"))
packs = idx.setdefault("packs", {})
# keep old ja-je/ji; add / overwrite j1-j5; archive double
packs["j2_double"] = {
    "title": "J2 Double Board (legacy)",
    "kind": "overlay",
    "family": "jeff",
    "observation": "text",
    "duplicate_board": True,
    "rules": "_rules_jeff.txt",
}
packs["j1"] = {
    "title": "J1 Baseline",
    "kind": "overlay",
    "family": "jeff",
    "observation": "text",
    "rules": "_rules_jeff.txt",
}
packs["j2"] = {
    "title": "J2 Careful",
    "kind": "overlay",
    "family": "jeff",
    "observation": "text",
    "rules": "_rules_jeff.txt",
}
packs["j3"] = {
    "title": "J3 Phase+Material",
    "kind": "jeff_phase",
    "family": "jeff",
    "observation": "text",
    "rules": "_rules_jeff.txt",
}
packs["j4"] = {
    "title": "J4 Checklist Flow",
    "kind": "jeff_checklist",
    "family": "jeff",
    "observation": "text",
    "rules": "_rules_jeff.txt",
}
packs["j5"] = {
    "title": "J5 Propose+Imagine",
    "kind": "jeff_imagine",
    "family": "jeff",
    "observation": "text",
    "rules": "_rules_jeff.txt",
}
idx_path.write_text(json.dumps(idx, indent=2) + "\n", encoding="utf-8")
print("packs written")

# --- phase helper ---
(ADAPTERS / "jeff_phase_detect.py").write_text(
    '''"""Classify opening / middlegame / endgame and material edge for Jeff J3."""

from __future__ import annotations

import chess

# Simple piece values in centipawns-ish integers.
_VALUES = {
    chess.PAWN: 1,
    chess.KNIGHT: 3,
    chess.BISHOP: 3,
    chess.ROOK: 5,
    chess.QUEEN: 9,
}


def material_score(board: chess.Board) -> tuple[int, int]:
    """Return (white_points, black_points) ignoring kings."""
    w = b = 0
    for sq, piece in board.piece_map().items():
        if piece.piece_type == chess.KING:
            continue
        val = _VALUES.get(piece.piece_type, 0)
        if piece.color == chess.WHITE:
            w += val
        else:
            b += val
    return w, b


def classify_phase(board: chess.Board) -> str:
    """Return opening | middle | end from piece count and queens/minors."""
    pieces = board.piece_map()
    n = len(pieces)
    queens = sum(1 for p in pieces.values() if p.piece_type == chess.QUEEN)
    minors = sum(
        1
        for p in pieces.values()
        if p.piece_type in (chess.KNIGHT, chess.BISHOP)
    )
    # Endgame: few pieces, or no queens and limited material.
    if n <= 12 or (queens == 0 and n <= 16):
        return "end"
    # Opening: early, many pieces still on board, both sides undeveloped-ish.
    if n >= 28 and board.fullmove_number <= 12:
        return "opening"
    if n >= 26 and board.fullmove_number <= 10:
        return "opening"
    return "middle"


def material_edge_for_side(board: chess.Board, side: chess.Color) -> str:
    """ahead | even | behind from side-to-move / agent side perspective."""
    w, b = material_score(board)
    ours = w if side == chess.WHITE else b
    theirs = b if side == chess.WHITE else w
    diff = ours - theirs
    if diff >= 2:
        return "ahead"
    if diff <= -2:
        return "behind"
    return "even"


def phase_key(board: chess.Board, *, side: chess.Color | None = None) -> str:
    """e.g. middle_ahead."""
    side = board.turn if side is None else side
    return f"{classify_phase(board)}_{material_edge_for_side(board, side)}"
''',
    encoding="utf-8",
)

# --- jeff_phase adapter ---
(ADAPTERS / "jeff_phase.py").write_text(
    '''"""J3: inject phase+material spirit, then normal Typesafe Choice."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from .jeff_phase_detect import phase_key
from .typesafe import TypesafeAdapter, board_from_board_text

_PHASE_DIR = (
    Path(__file__).resolve().parents[4] / "config" / "prompt_packs" / "j3_phases"
)


def load_phase_spirit(key: str) -> str:
    path = _PHASE_DIR / f"{key}.txt"
    if path.is_file():
        return path.read_text(encoding="utf-8").strip()
    # fallback middle_even
    fb = _PHASE_DIR / "middle_even.txt"
    return fb.read_text(encoding="utf-8").strip() if fb.is_file() else key


class JeffPhaseAdapter:
    """Rebuild board, classify phase/material, set spirit, delegate to Typesafe."""

    provider = "typesafe"

    def __init__(self, inner: TypesafeAdapter):
        self.inner = inner
        self.last_phase_key: Optional[str] = None

    def choose_move(self, *, board_text: str, board_png: Optional[bytes] = None) -> str:
        board = board_from_board_text(board_text)
        key = phase_key(board)
        self.last_phase_key = key
        spirit = load_phase_spirit(key)
        self.inner.spirit = spirit
        return self.inner.choose_move(board_text=board_text, board_png=board_png)

    def choose_placement(self, *, board_text: str, board_png: Optional[bytes] = None):
        return self.inner.choose_placement(board_text=board_text, board_png=board_png)

    def probe(self, *, board_text: str, board_png: Optional[bytes] = None) -> None:
        self.inner.probe(board_text=board_text, board_png=board_png)
''',
    encoding="utf-8",
)

# --- jeff_checklist adapter (J4) ---
(ADAPTERS / "jeff_checklist.py").write_text(
    '''"""J4: flowchart of Jeff yes/no checks, then final move Choice."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .typesafe import TypesafeAdapter, board_from_board_text, legal_uci


class JeffChecklistAdapter:
    """Ask Jeff a fixed checklist, then pick a move with answers in the note."""

    provider = "typesafe"

    def __init__(self, inner: TypesafeAdapter):
        self.inner = inner
        self.last_answers: Dict[str, str] = {}

    def _ask_label(self, *, board_text: str, question: str, options: List[str]) -> str:
        # Reuse System One with labeled criteria (not UCI).
        criteria = {opt: None for opt in options}
        # Temporarily call systemone via a tiny monkey on inner.
        state = {"board_text": board_text}
        note = (
            question
            + " Answer with exactly one of the criteria keys. No other words."
        )
        # Build questions payload like choose_move but with custom criteria.
        from typing import Any as _Any

        questions = {
            "answer": {
                "type": "choice",
                "note": note,
                "criteria": criteria,
            }
        }
        # TypesafeAdapter._systemone expects state object; pass a simple namespace
        class _State:
            pass

        st = _State()
        st.board_text = board_text
        raw = self.inner._systemone(state=st, questions=questions)
        answer = (raw.get("answers") or {}).get("answer") or raw.get("answer") or {}
        if isinstance(answer, dict):
            choice = str(answer.get("choice") or "").strip()
        else:
            choice = str(answer).strip()
        if choice not in criteria:
            # probabilities fallback
            probs = answer.get("probabilities") if isinstance(answer, dict) else None
            if isinstance(probs, dict) and probs:
                choice = max(probs.items(), key=lambda kv: float(kv[1]))[0]
        if choice not in criteria:
            choice = options[0]
        return choice

    def choose_move(self, *, board_text: str, board_png: Optional[bytes] = None) -> str:
        del board_png
        board = board_from_board_text(board_text)
        legal = legal_uci(board)
        answers: Dict[str, str] = {}

        answers["in_check"] = self._ask_label(
            board_text=board_text,
            question="Are we (side to move) currently in check?",
            options=["yes", "no"],
        )
        answers["losing_hang"] = self._ask_label(
            board_text=board_text,
            question=(
                "Are any of our pieces threatened such that if the exchange "
                "is forced we lose material points?"
            ),
            options=["yes", "no"],
        )
        answers["our_equal_capture"] = self._ask_label(
            board_text=board_text,
            question="Are we threatening a capture of equal or greater value that looks safe?",
            options=["yes", "no"],
        )
        answers["useful_check"] = self._ask_label(
            board_text=board_text,
            question="Is there a check available that improves our position (not a useless check)?",
            options=["yes", "no", "none"],
        )
        answers["mate_threat"] = self._ask_label(
            board_text=board_text,
            question="Is the opponent threatening checkmate in the next move or two?",
            options=["yes", "no"],
        )
        self.last_answers = answers

        checklist = "; ".join(f"{k}={v}" for k, v in answers.items())
        spirit = (
            "Checklist answers (trust these): "
            + checklist
            + ". Pick the legal UCI that best respects them: "
            "escape check if in_check=yes; stop mate if mate_threat=yes; "
            "save hanging losers if losing_hang=yes; take safe equal-or-better "
            "if our_equal_capture=yes; use a useful check only if useful_check=yes."
        )
        self.inner.spirit = spirit
        # Restrict criteria to legal via normal choose_move
        return self.inner.choose_move(board_text=board_text, board_png=None)

    def choose_placement(self, *, board_text: str, board_png: Optional[bytes] = None):
        return self.inner.choose_placement(board_text=board_text, board_png=board_png)

    def probe(self, *, board_text: str, board_png: Optional[bytes] = None) -> None:
        self.inner.probe(board_text=board_text, board_png=board_png)
''',
    encoding="utf-8",
)

# --- jeff_imagine adapter (J5): Jeff proposes, we imagine, Jeff compares ---
(ADAPTERS / "jeff_imagine.py").write_text(
    '''"""J5: Jeff proposes a move; we render the imagined board; Jeff keeps or bans."""

from __future__ import annotations

from typing import List, Optional, Set

import chess

from ....board_text import format_board_text
from .typesafe import TypesafeAdapter, board_from_board_text, legal_uci


class JeffImagineAdapter:
    """Jeff picks candidates; code only imagines; Jeff compares real vs imagined."""

    provider = "typesafe"

    def __init__(self, inner: TypesafeAdapter, *, max_tries: int = 5):
        self.inner = inner
        self.max_tries = max(1, int(max_tries))
        self.last_tries: List[str] = []

    def _jeff_proposes(self, board_text: str, banned: Set[str]) -> str:
        board = board_from_board_text(board_text)
        legal = [u for u in legal_uci(board) if u not in banned]
        if not legal:
            legal = legal_uci(board)
        spirit = (
            "Propose the single best legal UCI for the side to move. "
            "Do not pick a banned move."
        )
        if banned:
            spirit += " Banned (already rejected): " + ", ".join(sorted(banned)) + "."
        self.inner.spirit = spirit
        # Temporarily shrink by asking normal choose_move then validate.
        move = self.inner.choose_move(board_text=board_text, board_png=None)
        if move not in legal:
            move = legal[0]
        return move

    def _jeff_prefers_imagined(self, *, real_text: str, imagined_text: str, side: str) -> bool:
        """True if Jeff says the imagined position is better for `side`."""
        note = (
            f"Board A is the current position. Board B is after a candidate move by {side}. "
            f"Is Board B better for {side} than Board A? "
            "Answer with exactly one criteria key: better_for_us or worse_for_us."
        )
        criteria = {"better_for_us": None, "worse_for_us": None}
        questions = {
            "answer": {
                "type": "choice",
                "note": note
                + "\\n\\nBOARD_A (real):\\n"
                + real_text
                + "\\n\\nBOARD_B (imagined):\\n"
                + imagined_text,
                "criteria": criteria,
            }
        }

        class _State:
            pass

        st = _State()
        st.board_text = real_text
        raw = self.inner._systemone(state=st, questions=questions)
        answer = (raw.get("answers") or {}).get("answer") or raw.get("answer") or {}
        if isinstance(answer, dict):
            choice = str(answer.get("choice") or "").strip()
            if choice not in criteria:
                probs = answer.get("probabilities") or {}
                if isinstance(probs, dict) and probs:
                    choice = max(probs.items(), key=lambda kv: float(kv[1]))[0]
        else:
            choice = str(answer).strip()
        return choice == "better_for_us"

    def choose_move(self, *, board_text: str, board_png: Optional[bytes] = None) -> str:
        del board_png
        board = board_from_board_text(board_text)
        side = "white" if board.turn == chess.WHITE else "black"
        banned: Set[str] = set()
        self.last_tries = []
        last = None
        for _ in range(self.max_tries):
            proposal = self._jeff_proposes(board_text, banned)
            last = proposal
            self.last_tries.append(proposal)
            try:
                move = chess.Move.from_uci(proposal)
                if move not in board.legal_moves:
                    banned.add(proposal)
                    continue
            except Exception:
                banned.add(proposal)
                continue
            imagined = board.copy(stack=False)
            imagined.push(move)
            imagined_text = format_board_text(
                imagined, bottom_color="white" if imagined.turn == chess.WHITE else "black"
            )
            # Compare from the mover's perspective: after the move it is opponent's turn,
            # but we ask whether B is better for the side who just moved.
            if self._jeff_prefers_imagined(
                real_text=board_text, imagined_text=imagined_text, side=side
            ):
                return proposal
            banned.add(proposal)
        return last or legal_uci(board)[0]

    def choose_placement(self, *, board_text: str, board_png: Optional[bytes] = None):
        return self.inner.choose_placement(board_text=board_text, board_png=board_png)

    def probe(self, *, board_text: str, board_png: Optional[bytes] = None) -> None:
        self.inner.probe(board_text=board_text, board_png=board_png)
''',
    encoding="utf-8",
)

print("adapters written")

# Patch prompt_packs.py kinds
text = PROMPT_PACKS_PY.read_text(encoding="utf-8")
old = 'if kind not in {"overlay", "committee", "jeff_council"}:'
new = 'if kind not in {"overlay", "committee", "jeff_council", "jeff_phase", "jeff_checklist", "jeff_imagine"}:'
if old not in text:
    raise SystemExit("kind check not found")
PROMPT_PACKS_PY.write_text(text.replace(old, new, 1), encoding="utf-8")
print("prompt_packs kinds ok")

# Patch adapters __init__.py build_adapter_for_pack
init_path = ADAPTERS / "__init__.py"
init = init_path.read_text(encoding="utf-8")
if "jeff_phase" not in init:
    init = init.replace(
        "from .jeff_council import JeffCouncilAdapter\n",
        "from .jeff_checklist import JeffChecklistAdapter\n"
        "from .jeff_council import JeffCouncilAdapter\n"
        "from .jeff_imagine import JeffImagineAdapter\n"
        "from .jeff_phase import JeffPhaseAdapter\n",
    )
    needle = """    if pack.kind == "jeff_council":
        seat_ids = pack.seat_packs or ()
        s.council_spirits = [load_pack(pid).body.strip() for pid in seat_ids]
        s.duplicate_board = False
    if pack.observation:
        s.observation = pack.observation
    return build_adapter(s, transport, stub_moves=stub_moves)
"""
    repl = """    if pack.kind == "jeff_council":
        seat_ids = pack.seat_packs or ()
        s.council_spirits = [load_pack(pid).body.strip() for pid in seat_ids]
        s.duplicate_board = False
    if pack.observation:
        s.observation = pack.observation
    base = build_adapter(s, transport, stub_moves=stub_moves)
    if pack.kind == "jeff_phase":
        return JeffPhaseAdapter(base)
    if pack.kind == "jeff_checklist":
        return JeffChecklistAdapter(base)
    if pack.kind == "jeff_imagine":
        return JeffImagineAdapter(base)
    return base
"""
    if needle not in init:
        raise SystemExit("build_adapter_for_pack tail not found")
    init_path.write_text(init.replace(needle, repl, 1), encoding="utf-8")
    print("adapters __init__ patched")
else:
    print("adapters __init__ already patched")

# Runner slots for j1-j5
slots = {
    "version": 1,
    "max_concurrent_games": 1,
    "harness_base_url": "http://127.0.0.1:8765",
    "slots": [],
}
for pid in ["j1", "j2", "j3", "j4", "j5"]:
    slots["slots"].append(
        {
            "inscribed_id": "jev-latest",
            "provider": "typesafe",
            "observation": "text",
            "provider_model": "jev-latest",
            "base_url": "https://api.typesafe.ai/v1",
            "env_key": "TYPESAFE_API_KEY",
            "rpm": 60,
            "rpd": 5000,
            "kind": "ave",
            "agent_color": "white",
            "prompt_pack": pid,
            "_comment": f"Jeff rebuild seat {pid}",
        }
    )
(ROOT / "config" / "runner_slots_jeff_j1j5.json").write_text(
    json.dumps(slots, indent=2) + "\n", encoding="utf-8"
)

# Update compare_wave default packs if present
cw = EXP / "compare_wave.py"
if cw.exists():
    t = cw.read_text(encoding="utf-8")
    t2 = t.replace(
        'DEFAULT_PACKS = ["ja", "jb", "jc", "jd", "ji", "j2", "je"]',
        'DEFAULT_PACKS = ["j1", "j2", "j3", "j4", "j5"]',
    )
    if t2 == t:
        # try other quote styles
        t2 = t.replace(
            "DEFAULT_PACKS = ['ja', 'jb', 'jc', 'jd', 'ji', 'j2', 'je']",
            "DEFAULT_PACKS = ['j1', 'j2', 'j3', 'j4', 'j5']",
        )
    cw.write_text(t2, encoding="utf-8")
    print("compare_wave defaults updated" if t2 != t else "compare_wave defaults unchanged")

readme = EXP / "README_J1J5.md"
readme.write_text(
    """# Jeff seats J1–J5 (rebuild)

| Id | Role |
|----|------|
| j1 | Baseline single Choice |
| j2 | Careful single Choice |
| j3 | Code classifies opening/middle/end + ahead/even/behind, then Choice with that spirit |
| j4 | Checklist of Jeff yes/no questions, then final Choice |
| j5 | **Jeff** proposes a move → we imagine board text → Jeff says better/worse → keep or ban+retry |

Legacy packs ja–je / ji / j2_double stay in the index for old runs.

## Launch compare (same slate as before)

```powershell
cd "C:\\Users\\jordi\\Desktop\\coding stuff\\chess-vision-harness"
$env:PYTHONPATH = (Resolve-Path .\\python\\src).Path
python experiments\\prompt-packs-jeff\\compare_wave.py --packs j1,j2,j3,j4,j5
python experiments\\prompt-packs-jeff\\compare_wave.py --go --packs j1,j2,j3,j4,j5 --parallel 1
```

Or runner config: `config\\runner_slots_jeff_j1j5.json`
""",
    encoding="utf-8",
)

# smoke import
import sys

sys.path.insert(0, str(ROOT / "python" / "src"))
from chess_harness.prompt_packs import load_pack
from chess_harness.runner.adapters.jeff_phase_detect import phase_key
import chess

for pid in ["j1", "j2", "j3", "j4", "j5"]:
    p = load_pack(pid)
    print("loaded", pid, p.kind, p.title)

b = chess.Board()
print("start phase_key", phase_key(b))
print("done")
