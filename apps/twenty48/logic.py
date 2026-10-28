"""2048 rules: sliding, merging, spawning and game over. No pygame.

:meth:`Game2048.move` returns a :class:`MoveResult` describing where every
tile travelled, so the UI can animate the slide without re-deriving it.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Literal

SIZE = 4
GOAL = 2048
FOUR_CHANCE = 0.1

Pos = tuple[int, int]  # (row, col)
Grid = list[list[int]]
Direction = Literal["up", "down", "left", "right"]


@dataclass(frozen=True)
class Slide:
    value: int  # value of the tile before merging
    start: Pos
    end: Pos


@dataclass
class MoveResult:
    moved: bool = False
    gained: int = 0
    slides: list[Slide] = field(default_factory=list)
    merged: list[Pos] = field(default_factory=list)
    spawned: Pos | None = None


def line(direction: Direction, i: int) -> list[Pos]:
    """Cells of row/column ``i`` ordered from the edge tiles move towards."""
    if direction == "left":
        return [(i, c) for c in range(SIZE)]
    if direction == "right":
        return [(i, c) for c in reversed(range(SIZE))]
    if direction == "up":
        return [(r, i) for r in range(SIZE)]
    return [(r, i) for r in reversed(range(SIZE))]


@dataclass
class Game2048:
    """A game of 2048 on a 4×4 grid."""

    rng: random.Random = field(default_factory=random.Random)
    grid: Grid = field(default_factory=lambda: [[0] * SIZE for _ in range(SIZE)])
    score: int = 0
    won: bool = False  # reached GOAL at least once
    over: bool = False

    @classmethod
    def new(cls, rng: random.Random | None = None) -> Game2048:
        game = cls(rng or random.Random())
        game.spawn()
        game.spawn()
        return game

    # ------------------------------------------------------------------ queries
    def empty_cells(self) -> list[Pos]:
        return [(r, c) for r in range(SIZE) for c in range(SIZE) if self.grid[r][c] == 0]

    def max_tile(self) -> int:
        return max(max(row) for row in self.grid)

    def can_move(self) -> bool:
        if self.empty_cells():
            return True
        for r in range(SIZE):
            for c in range(SIZE):
                v = self.grid[r][c]
                if (c + 1 < SIZE and self.grid[r][c + 1] == v) or (
                    r + 1 < SIZE and self.grid[r + 1][c] == v
                ):
                    return True
        return False

    # ------------------------------------------------------------------ actions
    def spawn(self) -> Pos | None:
        """Place a 2 (or sometimes a 4) in a random empty cell."""
        empty = self.empty_cells()
        if not empty:
            return None
        r, c = self.rng.choice(empty)
        self.grid[r][c] = 4 if self.rng.random() < FOUR_CHANCE else 2
        return (r, c)

    def move(self, direction: Direction) -> MoveResult:
        """Slide every tile towards ``direction``, merging equal neighbours once per move."""
        result = MoveResult()
        if self.over:
            return result
        new: Grid = [[0] * SIZE for _ in range(SIZE)]
        for i in range(SIZE):
            cells = line(direction, i)
            out = 0
            can_merge = False  # whether the last placed tile may still merge
            for pos in cells:
                value = self.grid[pos[0]][pos[1]]
                if not value:
                    continue
                prev = cells[out - 1] if out else None
                if prev is not None and can_merge and new[prev[0]][prev[1]] == value:
                    new[prev[0]][prev[1]] = value * 2
                    result.gained += value * 2
                    result.merged.append(prev)
                    result.slides.append(Slide(value, pos, prev))
                    can_merge = False
                else:
                    target = cells[out]
                    new[target[0]][target[1]] = value
                    result.slides.append(Slide(value, pos, target))
                    out += 1
                    can_merge = True
        if new == self.grid:
            return result
        self.grid = new
        self.score += result.gained
        result.moved = True
        result.spawned = self.spawn()
        if self.max_tile() >= GOAL:
            self.won = True
        self.over = not self.can_move()
        return result
