"""Switchboard rules: press a light to flip it and its four neighbours; turn them all off.

Pure Python, no pygame. Puzzles are made by pressing random lights on a dark
board, so every puzzle can be solved. :func:`solve` finds the fewest presses
with Gaussian elimination over GF(2) (pressing a light twice cancels out, so a
solution is just a set of lights to press once), trying every combination of
the free variables to get the minimum.
"""

from __future__ import annotations

import itertools
import random
from dataclasses import dataclass, field

Cell = tuple[int, int]  # (row, col)


def neighbourhood(size: int, cell: Cell) -> list[Cell]:
    r, c = cell
    out = [(r, c)]
    for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        if 0 <= r + dr < size and 0 <= c + dc < size:
            out.append((r + dr, c + dc))
    return out


@dataclass
class Switchboard:
    size: int = 5
    lights: set[Cell] = field(default_factory=set)  # cells that are on
    presses: int = 0
    _undo: list[set[Cell]] = field(default_factory=list)

    def press(self, cell: Cell, record: bool = True) -> None:
        if record:
            self._undo.append(set(self.lights))
            self.presses += 1
        for n in neighbourhood(self.size, cell):
            self.lights ^= {n}

    def undo(self) -> bool:
        if not self._undo:
            return False
        self.lights = self._undo.pop()
        self.presses -= 1
        return True

    @property
    def solved(self) -> bool:
        return not self.lights

    @classmethod
    def random(cls, size: int, rng: random.Random, presses: int | None = None) -> Switchboard:
        """A puzzle made by ``presses`` random distinct presses on a dark board."""
        cells = [(r, c) for r in range(size) for c in range(size)]
        count = presses if presses is not None else rng.randint(size + 2, size * 2 + 2)
        board = cls(size)
        while board.solved:  # (pressing can, rarely, cancel out completely)
            board.lights.clear()
            for cell in rng.sample(cells, min(count, len(cells))):
                board.press(cell, record=False)
        return board


def solve(size: int, lights: set[Cell]) -> list[Cell] | None:
    """The smallest set of presses that turns every light off (``None`` if impossible)."""
    n = size * size
    index = {(r, c): r * size + c for r in range(size) for c in range(size)}
    # One row per cell (in index order): which presses flip it, plus whether it is on.
    rows = []
    for r, c in index:
        mask = 0
        for cell in neighbourhood(size, (r, c)):
            mask |= 1 << index[cell]
        rows.append(mask | (int((r, c) in lights) << n))
    pivots: list[int] = []
    rank = 0
    for col in range(n):
        pivot = next((i for i in range(rank, n) if rows[i] >> col & 1), None)
        if pivot is None:
            continue
        rows[rank], rows[pivot] = rows[pivot], rows[rank]
        for i in range(n):
            if i != rank and rows[i] >> col & 1:
                rows[i] ^= rows[rank]
        pivots.append(col)
        rank += 1
    if any(rows[i] >> n & 1 for i in range(rank, n)):
        return None  # inconsistent: unsolvable
    free = [c for c in range(n) if c not in pivots]
    best: list[int] | None = None
    for choice in itertools.product((0, 1), repeat=len(free)):
        x = [0] * n
        for col, bit in zip(free, choice, strict=True):
            x[col] = bit
        for i, col in enumerate(pivots):
            value = rows[i] >> n & 1
            for other in free:
                if rows[i] >> other & 1:
                    value ^= x[other]
            x[col] = value
        if best is None or sum(x) < sum(best):
            best = x
    assert best is not None
    cells = list(index)
    return [cells[i] for i in range(n) if best[i]]
