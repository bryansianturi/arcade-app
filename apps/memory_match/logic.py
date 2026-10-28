"""Memory Match rules: shuffled pairs, flipping, matching, moves and time. No pygame."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Literal

Size = Literal["easy", "medium", "hard"]
SIZES: tuple[Size, ...] = ("easy", "medium", "hard")
#: (columns, rows) per size. Every board has an even number of cards.
LAYOUTS: dict[Size, tuple[int, int]] = {"easy": (4, 3), "medium": (4, 4), "hard": (6, 4)}

FlipResult = Literal["ignored", "first", "match", "mismatch"]


@dataclass
class MemoryGame:
    """A board of face-down cards. ``cards[i]`` is the symbol id on card ``i``.

    Flipping a second card that doesn't match leaves both face up until
    :meth:`hide_mismatch` is called (the UI waits a moment so the player can
    see them); flipping a third card hides them automatically.
    """

    cols: int
    rows: int
    rng: random.Random = field(default_factory=random.Random)
    cards: list[int] = field(default_factory=list)
    matched: set[int] = field(default_factory=set)
    open: list[int] = field(default_factory=list)  # face-up, not yet matched (max 2)
    moves: int = 0
    elapsed: float = 0.0
    started: bool = False

    def __post_init__(self) -> None:
        if (self.cols * self.rows) % 2:
            raise ValueError("Board needs an even number of cards")
        if not self.cards:
            pairs = self.cols * self.rows // 2
            self.cards = [i for i in range(pairs) for _ in range(2)]
            self.rng.shuffle(self.cards)

    @classmethod
    def for_size(cls, size: Size, rng: random.Random | None = None) -> MemoryGame:
        cols, rows = LAYOUTS[size]
        return cls(cols, rows, rng or random.Random())

    @property
    def won(self) -> bool:
        return len(self.matched) == len(self.cards)

    @property
    def pairs_left(self) -> int:
        return (len(self.cards) - len(self.matched)) // 2

    def face_up(self, index: int) -> bool:
        return index in self.matched or index in self.open

    def flip(self, index: int) -> FlipResult:
        if self.won or not 0 <= index < len(self.cards) or self.face_up(index):
            return "ignored"
        if len(self.open) == 2:
            self.hide_mismatch()
        self.started = True
        self.open.append(index)
        if len(self.open) == 1:
            return "first"
        self.moves += 1
        a, b = self.open
        if self.cards[a] == self.cards[b]:
            self.matched.update(self.open)
            self.open.clear()
            return "match"
        return "mismatch"

    def hide_mismatch(self) -> None:
        if len(self.open) == 2:
            self.open.clear()

    def tick(self, dt: float) -> None:
        if self.started and not self.won:
            self.elapsed += dt
