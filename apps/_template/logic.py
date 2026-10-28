"""Game rules with no pygame dependency, so they can be unit-tested.

Keep everything that decides *what happens* here, and everything that decides
*what it looks like* in ``app.py``.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ClickCounter:
    """The world's smallest game: click the target to score."""

    score: int = 0

    def hit(self) -> None:
        self.score += 1

    def reset(self) -> None:
        self.score = 0
