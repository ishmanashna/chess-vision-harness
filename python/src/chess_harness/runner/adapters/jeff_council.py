"""Silent Jeff council: three independent Choices, majority UCI, no chat."""

from __future__ import annotations

from collections import Counter
from typing import Dict, List, Optional, Sequence

from .typesafe import TypesafeAdapter


class JeffCouncilAdapter:
    """Run three Jeff spirits on the same board; play the majority move."""

    provider = "typesafe"

    def __init__(self, voters: Sequence[TypesafeAdapter], *, tie_order: Optional[Sequence[int]] = None):
        if len(voters) < 2:
            raise ValueError("jeff council needs at least 2 voters")
        self.voters = list(voters)
        self.tie_order = list(tie_order) if tie_order is not None else list(range(len(voters)))
        self.last_votes: List[str] = []
        self.last_raw = None
        self.last_usage = None

    def choose_move(self, *, board_text: str, board_png: Optional[bytes] = None) -> str:
        votes: List[str] = []
        for voter in self.voters:
            votes.append(voter.choose_move(board_text=board_text, board_png=board_png))
        self.last_votes = votes
        counts = Counter(votes)
        best = counts.most_common()
        top_n = best[0][1]
        winners = [move for move, n in best if n == top_n]
        if len(winners) == 1:
            return winners[0]
        # Tie: prefer earlier seat in tie_order whose vote is among winners.
        for idx in self.tie_order:
            if 0 <= idx < len(votes) and votes[idx] in winners:
                return votes[idx]
        return winners[0]

    def choose_placement(self, *, board_text: str, board_png: Optional[bytes] = None) -> Dict[str, str]:
        return self.voters[0].choose_placement(board_text=board_text, board_png=board_png)

    def probe(self, *, board_text: str, board_png: Optional[bytes] = None) -> None:
        self.voters[0].probe(board_text=board_text, board_png=board_png)
