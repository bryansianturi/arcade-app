"""Minesweeper rules: lazy mine placement, flood fill, flags and chording. No pygame."""

from __future__ import annotations

import random
from collections import deque
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Literal

Cell = tuple[int, int]  # (x, y)
Difficulty = Literal["easy", "medium", "hard"]
Status = Literal["ready", "playing", "won", "lost"]

DIFFICULTIES: tuple[Difficulty, ...] = ("easy", "medium", "hard")
#: (columns, rows, mines) per difficulty.
SIZES: dict[Difficulty, tuple[int, int, int]] = {
    "easy": (9, 9, 10),
    "medium": (16, 16, 40),
    "hard": (30, 16, 99),
}


@dataclass
class Minefield:
    """A Minesweeper board.

    Mines are placed on the first reveal, never on or next to the clicked cell,
    so the first click is always safe and always opens an area.
    """

    width: int
    height: int
    mine_count: int
    rng: random.Random = field(default_factory=random.Random)
    mines: set[Cell] = field(default_factory=set)
    revealed: set[Cell] = field(default_factory=set)
    flags: set[Cell] = field(default_factory=set)
    status: Status = "ready"
    exploded: Cell | None = None
    elapsed: float = 0.0

    def __post_init__(self) -> None:
        if not 0 < self.mine_count <= self.width * self.height - 9:
            raise ValueError("Too many mines for this board")

    @classmethod
    def for_difficulty(cls, difficulty: Difficulty, rng: random.Random | None = None) -> Minefield:
        w, h, m = SIZES[difficulty]
        return cls(w, h, m, rng or random.Random())

    # ------------------------------------------------------------------ queries
    def in_bounds(self, cell: Cell) -> bool:
        return 0 <= cell[0] < self.width and 0 <= cell[1] < self.height

    def neighbors(self, cell: Cell) -> Iterator[Cell]:
        x, y = cell
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                n = (x + dx, y + dy)
                if (dx or dy) and self.in_bounds(n):
                    yield n

    def adjacent_mines(self, cell: Cell) -> int:
        return sum(1 for n in self.neighbors(cell) if n in self.mines)

    @property
    def mines_left(self) -> int:
        """Mine counter shown to the player (may go negative with too many flags)."""
        return self.mine_count - len(self.flags)

    @property
    def finished(self) -> bool:
        return self.status in ("won", "lost")

    # ------------------------------------------------------------------ actions
    def place_mines(self, safe: Cell) -> None:
        """Randomly place mines, keeping ``safe`` and its neighbours clear."""
        protected = {safe, *self.neighbors(safe)}
        candidates = [
            (x, y) for y in range(self.height) for x in range(self.width) if (x, y) not in protected
        ]
        self.mines = set(self.rng.sample(candidates, self.mine_count))
        self.status = "playing"

    def reveal(self, cell: Cell) -> None:
        """Open a cell. Opening a zero flood-fills its neighbours."""
        if self.finished or not self.in_bounds(cell) or cell in self.flags:
            return
        if self.status == "ready":
            self.place_mines(cell)
        if cell in self.revealed:
            return
        if cell in self.mines:
            self.exploded = cell
            self.status = "lost"
            return
        queue = deque([cell])
        while queue:
            current = queue.popleft()
            if current in self.revealed or current in self.flags:
                continue
            self.revealed.add(current)
            if self.adjacent_mines(current) == 0:
                queue.extend(n for n in self.neighbors(current) if n not in self.revealed)
        self._check_win()

    def chord(self, cell: Cell) -> None:
        """On a revealed number with that many flags around it, open the other neighbours."""
        if self.finished or cell not in self.revealed:
            return
        number = self.adjacent_mines(cell)
        around = list(self.neighbors(cell))
        if number == 0 or sum(1 for n in around if n in self.flags) != number:
            return
        for n in around:
            if n not in self.flags and n not in self.revealed:
                self.reveal(n)
                if self.status == "lost":
                    return

    def toggle_flag(self, cell: Cell) -> None:
        if self.finished or not self.in_bounds(cell) or cell in self.revealed:
            return
        self.flags ^= {cell}

    def tick(self, dt: float) -> None:
        """Advance the timer (it only runs between the first click and the end)."""
        if self.status == "playing":
            self.elapsed += dt

    def _check_win(self) -> None:
        if len(self.revealed) == self.width * self.height - self.mine_count:
            self.status = "won"
            self.flags = set(self.mines)
