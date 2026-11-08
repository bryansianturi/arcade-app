"""Cellular automata on a finite grid: rules, stepping, patterns (RLE) and stamping. No pygame.

Live cells are a set of ``(x, y)``, so stepping costs time in proportion to the
population rather than the grid size. Edges either wrap (a torus) or are dead.
"""

from __future__ import annotations

import random
import re
from collections import Counter
from dataclasses import dataclass, field

Cell = tuple[int, int]
NEIGHBORS: tuple[Cell, ...] = tuple(
    (dx, dy) for dy in (-1, 0, 1) for dx in (-1, 0, 1) if (dx, dy) != (0, 0)
)


@dataclass(frozen=True)
class Rule:
    """Birth/survival counts in B/S notation, e.g. Conway's Life is ``B3/S23``."""

    name: str
    birth: frozenset[int]
    survive: frozenset[int]

    @property
    def notation(self) -> str:
        return "B{}/S{}".format(
            "".join(map(str, sorted(self.birth))), "".join(map(str, sorted(self.survive)))
        )


def parse_rule(text: str, name: str = "") -> Rule:
    """Parse ``"B3/S23"`` (case-insensitive). Raises ``ValueError`` if malformed."""
    match = re.fullmatch(r"\s*B([0-8]*)\s*/\s*S([0-8]*)\s*", text, re.IGNORECASE)
    if match is None:
        raise ValueError(f"not a B/S rule: {text!r}")
    birth, survive = (frozenset(int(c) for c in group) for group in match.groups())
    return Rule(name or text.strip().upper(), birth, survive)


RULES: tuple[Rule, ...] = (
    parse_rule("B3/S23", "Conway"),
    parse_rule("B36/S23", "HighLife"),
    parse_rule("B3678/S34678", "Day & Night"),
    parse_rule("B2/S", "Seeds"),
)


def parse_rle(text: str) -> frozenset[Cell]:
    """Cells from run-length encoded pattern text (``b`` dead, ``o`` alive, ``$`` new row).

    Header lines (``x = 3, y = 3``) and ``#`` comments are ignored; ``!`` ends it.
    Raises ``ValueError`` on characters RLE doesn't use.
    """
    body = "".join(
        line.strip()
        for line in text.splitlines()
        if line.strip() and not line.lstrip().startswith(("#", "x"))
    )
    cells: set[Cell] = set()
    x = y = 0
    for count, tag in re.findall(r"(\d*)([bo$!]|.)", body):
        n = int(count) if count else 1
        if tag == "!":
            break
        if tag == "b":
            x += n
        elif tag == "o":
            cells.update((x + i, y) for i in range(n))
            x += n
        elif tag == "$":
            y += n
            x = 0
        else:
            raise ValueError(f"unexpected {tag!r} in RLE")
    return frozenset(cells)


@dataclass(frozen=True)
class Pattern:
    name: str
    cells: frozenset[Cell]

    @property
    def size(self) -> tuple[int, int]:
        if not self.cells:
            return 0, 0
        return max(x for x, _ in self.cells) + 1, max(y for _, y in self.cells) + 1


def rotate(cells: frozenset[Cell]) -> frozenset[Cell]:
    """Rotate a pattern a quarter turn clockwise, keeping it at the origin."""
    height = max((y for _, y in cells), default=0) + 1
    return frozenset((height - 1 - y, x) for x, y in cells)


PATTERNS: tuple[Pattern, ...] = tuple(
    Pattern(name, parse_rle(rle))
    for name, rle in (
        ("Glider", "bob$2bo$3o!"),
        ("Spaceship", "bo2bo$o4b$o3bo$4o!"),
        (
            "Pulsar",
            "2b3o3b3o2b2$o4bobo4bo$o4bobo4bo$o4bobo4bo$2b3o3b3o2b2$2b3o3b3o2b$"
            "o4bobo4bo$o4bobo4bo$o4bobo4bo2$2b3o3b3o!",
        ),
        ("Pentadecathlon", "2bo4bo2b$2ob4ob2o$2bo4bo2b!"),
        (
            "Glider gun",
            "24bo$22bobo$12b2o6b2o12b2o$11bo3bo4b2o12b2o$2o8bo5bo3b2o$"
            "2o8bo3bob2o4bobo$10bo5bo7bo$11bo3bo$12b2o!",
        ),
        ("R-pentomino", "b2o$2o$bo!"),
        ("Acorn", "bo5b$3bo3b$2o2b3o!"),
        ("Diehard", "6bob$2o6b$bo3b3o!"),
    )
)


@dataclass
class Life:
    """A grid of ``width × height`` cells evolving under ``rule``."""

    width: int
    height: int
    rule: Rule = RULES[0]
    wrap: bool = True
    cells: set[Cell] = field(default_factory=set)
    generation: int = 0

    def inside(self, cell: Cell) -> bool:
        return 0 <= cell[0] < self.width and 0 <= cell[1] < self.height

    def set(self, cell: Cell, alive: bool) -> None:
        if not self.inside(cell):
            return
        if alive:
            self.cells.add(cell)
        else:
            self.cells.discard(cell)

    def toggle(self, cell: Cell) -> bool:
        """Flip a cell and return its new state."""
        alive = cell not in self.cells
        self.set(cell, alive)
        return alive

    def clear(self) -> None:
        self.cells.clear()
        self.generation = 0

    def randomize(self, rng: random.Random, density: float = 0.3) -> None:
        self.cells = {
            (x, y) for y in range(self.height) for x in range(self.width) if rng.random() < density
        }
        self.generation = 0

    def stamp(self, cells: frozenset[Cell], origin: Cell) -> None:
        """Add a pattern with its top-left corner at ``origin`` (wrapping if enabled)."""
        for x, y in cells:
            cell = (origin[0] + x, origin[1] + y)
            if self.wrap:
                cell = (cell[0] % self.width, cell[1] % self.height)
            self.set(cell, True)

    def neighbor_counts(self) -> Counter[Cell]:
        counts: Counter[Cell] = Counter()
        w, h = self.width, self.height
        for x, y in self.cells:
            for dx, dy in NEIGHBORS:
                nx, ny = x + dx, y + dy
                if self.wrap:
                    counts[(nx % w, ny % h)] += 1
                elif 0 <= nx < w and 0 <= ny < h:
                    counts[(nx, ny)] += 1
        return counts

    def step(self) -> None:
        """Advance one generation."""
        counts = self.neighbor_counts()
        birth, survive = self.rule.birth, self.rule.survive
        nxt = {
            cell
            for cell, n in counts.items()
            if (n in survive if cell in self.cells else n in birth)
        }
        if 0 in survive:  # lonely cells never appear in the counts
            nxt |= {cell for cell in self.cells if cell not in counts}
        self.cells = nxt
        self.generation += 1
