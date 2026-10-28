"""Sliding tiles rules (the 8 and 15 puzzles). Pure Python, no pygame.

Tiles are numbered ``1..n²-1`` and ``0`` is the gap. A move slides one or more
tiles in the gap's row or column towards the gap. Shuffles are random
permutations checked for solvability with the standard inversion-parity test.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

GAP = 0


def solved_tiles(size: int) -> list[int]:
    return [*range(1, size * size), GAP]


def is_solvable(tiles: list[int], size: int) -> bool:
    """Inversion-parity test for an ``size``×``size`` sliding puzzle."""
    numbers = [t for t in tiles if t != GAP]
    inversions = sum(1 for i, a in enumerate(numbers) for b in numbers[i + 1 :] if a > b)
    if size % 2 == 1:
        return inversions % 2 == 0
    gap_row_from_bottom = size - tiles.index(GAP) // size
    return (inversions + gap_row_from_bottom) % 2 == 1


@dataclass
class SlidingPuzzle:
    size: int = 4
    tiles: list[int] = field(default_factory=list)
    moves: int = 0
    _undo: list[list[int]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.tiles:
            self.tiles = solved_tiles(self.size)

    @classmethod
    def shuffled(cls, size: int, rng: random.Random) -> SlidingPuzzle:
        tiles = solved_tiles(size)
        while True:
            rng.shuffle(tiles)
            if is_solvable(tiles, size) and tiles != solved_tiles(size):
                return cls(size, list(tiles))

    @property
    def gap(self) -> tuple[int, int]:
        i = self.tiles.index(GAP)
        return divmod(i, self.size)

    def at(self, r: int, c: int) -> int:
        return self.tiles[r * self.size + c]

    @property
    def solved(self) -> bool:
        return self.tiles == solved_tiles(self.size)

    def slide(self, r: int, c: int) -> list[int]:
        """Slide the tile at (r, c), plus any between it and the gap, towards the gap.

        Returns the tiles that moved (empty if the tile isn't in the gap's row/column).
        """
        gr, gc = self.gap
        if (r, c) == (gr, gc) or (r != gr and c != gc):
            return []
        self._undo.append(list(self.tiles))
        moved = []
        dr = (r > gr) - (r < gr)
        dc = (c > gc) - (c < gc)
        while (gr, gc) != (r, c):
            nr, nc = gr + dr, gc + dc
            tile = self.at(nr, nc)
            self.tiles[gr * self.size + gc] = tile
            self.tiles[nr * self.size + nc] = GAP
            moved.append(tile)
            gr, gc = nr, nc
        self.moves += 1
        return moved

    def push(self, direction: tuple[int, int]) -> list[int]:
        """Move the tile next to the gap in ``direction`` (dx, dy) *into* the gap.

        Pressing "left" moves the tile to the right of the gap leftwards.
        """
        dx, dy = direction
        gr, gc = self.gap
        r, c = gr - dy, gc - dx
        if 0 <= r < self.size and 0 <= c < self.size:
            return self.slide(r, c)
        return []

    def undo(self) -> bool:
        if not self._undo:
            return False
        self.tiles = self._undo.pop()
        self.moves -= 1
        return True
