"""Fleet Strike rules and the computer admiral. Pure Python, no pygame.

Two 10×10 grids, five ships each (5, 4, 3, 3 and 2 cells) placed in straight
lines that may touch but not overlap. Players alternate single shots; a ship
sinks when every cell is hit, and sinking it reveals it to the shooter.

The computer only ever sees what a player would: its own shot results and the
ships it has sunk. Three levels:

- ``easy``: random untried cells.
- ``normal``: hunts on a checkerboard (every ship covers at least one dark
  square), then targets around hits, following a line once two hits align.
- ``hard``: probability density. For every remaining ship, count each
  placement consistent with the shots so far; placements through unresolved
  hits count far more. It fires at the cell covered by the most placements.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Literal

SIZE = 10
FLEET: tuple[tuple[str, int], ...] = (
    ("Carrier", 5),
    ("Cruiser", 4),
    ("Destroyer", 3),
    ("Submarine", 3),
    ("Patrol boat", 2),
)
HIT_WEIGHT = 40

Cell = tuple[int, int]  # (row, col)
ShotResult = Literal["miss", "hit", "sunk"]
Level = Literal["easy", "normal", "hard"]
LEVELS: tuple[Level, ...] = ("easy", "normal", "hard")


def ship_cells(row: int, col: int, length: int, horizontal: bool) -> list[Cell]:
    return [(row, col + i) if horizontal else (row + i, col) for i in range(length)]


def in_bounds(cell: Cell) -> bool:
    return 0 <= cell[0] < SIZE and 0 <= cell[1] < SIZE


@dataclass
class Ship:
    name: str
    cells: list[Cell]
    hits: set[Cell] = field(default_factory=set)

    @property
    def sunk(self) -> bool:
        return len(self.hits) == len(self.cells)

    @property
    def horizontal(self) -> bool:
        return len(self.cells) < 2 or self.cells[0][0] == self.cells[1][0]


@dataclass
class Board:
    ships: list[Ship] = field(default_factory=list)
    #: Shots received: cell → "miss" or "hit".
    shots: dict[Cell, Literal["miss", "hit"]] = field(default_factory=dict)

    @classmethod
    def random(cls, rng: random.Random) -> Board:
        board = cls()
        for name, length in FLEET:
            while True:
                horizontal = rng.random() < 0.5
                row = rng.randrange(SIZE - (0 if horizontal else length - 1))
                col = rng.randrange(SIZE - (length - 1 if horizontal else 0))
                cells = ship_cells(row, col, length, horizontal)
                if board.can_place(cells):
                    board.ships.append(Ship(name, cells))
                    break
        return board

    def occupied(self, ignore: Ship | None = None) -> set[Cell]:
        return {c for s in self.ships if s is not ignore for c in s.cells}

    def can_place(self, cells: list[Cell], ignore: Ship | None = None) -> bool:
        return all(in_bounds(c) for c in cells) and not set(cells) & self.occupied(ignore)

    def ship_at(self, cell: Cell) -> Ship | None:
        return next((s for s in self.ships if cell in s.cells), None)

    def fire(self, cell: Cell) -> ShotResult | None:
        """Shoot at ``cell``. ``None`` if it's off the board or already shot."""
        if not in_bounds(cell) or cell in self.shots:
            return None
        ship = self.ship_at(cell)
        if ship is None:
            self.shots[cell] = "miss"
            return "miss"
        self.shots[cell] = "hit"
        ship.hits.add(cell)
        return "sunk" if ship.sunk else "hit"

    @property
    def defeated(self) -> bool:
        return all(s.sunk for s in self.ships)

    def sunk_ships(self) -> list[Ship]:
        return [s for s in self.ships if s.sunk]


@dataclass
class Admiral:
    """The computer's shooting strategy against ``board`` (it never reads the ships)."""

    level: Level = "normal"
    rng: random.Random = field(default_factory=random.Random)

    def choose(self, board: Board) -> Cell:
        untried = [(r, c) for r in range(SIZE) for c in range(SIZE) if (r, c) not in board.shots]
        if self.level == "easy":
            return self.rng.choice(untried)
        sunk = {c for s in board.sunk_ships() for c in s.cells}
        open_hits = [c for c, res in board.shots.items() if res == "hit" and c not in sunk]
        if self.level == "hard":
            return self._densest(board, untried, open_hits, sunk)
        if open_hits:
            return self._target(board, open_hits)
        checker = [c for c in untried if (c[0] + c[1]) % 2 == 0]
        return self.rng.choice(checker or untried)

    def _target(self, board: Board, hits: list[Cell]) -> Cell:
        """Extend a line of two or more aligned hits, else try around any hit."""
        hit_set = set(hits)
        for r, c in hits:
            for dr, dc in ((0, 1), (1, 0)):
                if (r + dr, c + dc) in hit_set:
                    # Walk both ways along the line to the first untried cell.
                    for sign in (1, -1):
                        rr, cc = r, c
                        while (rr, cc) in hit_set:
                            rr, cc = rr + sign * dr, cc + sign * dc
                        if in_bounds((rr, cc)) and (rr, cc) not in board.shots:
                            return (rr, cc)
        around = [
            (r + dr, c + dc)
            for r, c in hits
            for dr, dc in ((0, 1), (1, 0), (0, -1), (-1, 0))
            if in_bounds((r + dr, c + dc)) and (r + dr, c + dc) not in board.shots
        ]
        if around:
            return self.rng.choice(around)
        untried = [(r, c) for r in range(SIZE) for c in range(SIZE) if (r, c) not in board.shots]
        return self.rng.choice(untried)

    def _densest(
        self, board: Board, untried: list[Cell], open_hits: list[Cell], sunk: set[Cell]
    ) -> Cell:
        sunk_names = [s.name for s in board.sunk_ships()]
        remaining = [length for name, length in FLEET if name not in sunk_names]
        misses = {c for c, res in board.shots.items() if res == "miss"}
        blocked = misses | sunk
        hit_set = set(open_hits)
        score: dict[Cell, int] = dict.fromkeys(untried, 0)
        for length in remaining:
            for horizontal in (True, False):
                for r in range(SIZE):
                    for c in range(SIZE):
                        cells = ship_cells(r, c, length, horizontal)
                        if not all(in_bounds(x) for x in cells) or blocked & set(cells):
                            continue
                        weight = 1 + HIT_WEIGHT * len(hit_set.intersection(cells))
                        for x in cells:
                            if x in score:
                                score[x] += weight
        best = max(score.values())
        return self.rng.choice([c for c, v in score.items() if v == best])
