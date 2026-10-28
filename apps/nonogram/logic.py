"""Nonogram rules, a line-logic solver and a random puzzle generator. Pure Python.

A puzzle is a grid of ``#`` (filled) and ``.`` (empty). Each row and column
has a clue: the lengths of its runs of filled cells, in order (``[0]`` for an
empty line).

:func:`solve` uses only line logic, deducing what each row or column must be
from its clue and what is already known, until nothing changes. A puzzle it
solves completely has a unique solution and needs no guessing, which is the
bar for the bundled puzzles and for the random generator.
"""

from __future__ import annotations

import json
import random
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

UNKNOWN, EMPTY, FILLED = -1, 0, 1
Line = tuple[int, ...]
PUZZLES_FILE = Path(__file__).parent / "puzzles.json"

# Player marks
BLANK, FILL, CROSS = 0, 1, 2


def runs(cells: Sequence[bool]) -> list[int]:
    """Clue for a line of booleans: ``[True, True, False, True]`` → ``[2, 1]``."""
    out, count = [], 0
    for filled in cells:
        if filled:
            count += 1
        elif count:
            out.append(count)
            count = 0
    if count:
        out.append(count)
    return out or [0]


@dataclass(frozen=True)
class Puzzle:
    name: str
    rows: tuple[str, ...]  # "#" and "."
    color: tuple[int, int, int] = (99, 102, 241)

    @property
    def width(self) -> int:
        return len(self.rows[0])

    @property
    def height(self) -> int:
        return len(self.rows)

    def filled(self, r: int, c: int) -> bool:
        return self.rows[r][c] == "#"

    @property
    def row_clues(self) -> list[list[int]]:
        return [runs([ch == "#" for ch in row]) for row in self.rows]

    @property
    def col_clues(self) -> list[list[int]]:
        return [runs([row[c] == "#" for row in self.rows]) for c in range(self.width)]


def load_puzzles(path: Path = PUZZLES_FILE) -> list[Puzzle]:
    data = json.loads(path.read_text(encoding="utf-8"))
    puzzles = []
    for item in data:
        rows = tuple(item["rows"])
        if len({len(r) for r in rows}) != 1 or any(set(r) - {"#", "."} for r in rows):
            raise ValueError(f"puzzle {item.get('name')!r} has ragged rows or bad characters")
        r, g, b = item.get("color", (99, 102, 241))
        puzzles.append(Puzzle(item["name"], rows, (int(r), int(g), int(b))))
    return puzzles


# ---------------------------------------------------------------------- line logic
@lru_cache(maxsize=65536)
def _placements(clues: tuple[int, ...], known: Line) -> tuple[Line, ...]:
    """Every way to lay ``clues`` out on a line consistent with ``known``."""
    length = len(known)
    if clues == (0,):
        clues = ()
    out: list[Line] = []

    def place(i: int, start: int, prefix: list[int]) -> None:
        if i == len(clues):
            line = prefix + [EMPTY] * (length - len(prefix))
            if all(
                k in (UNKNOWN, v)
                for k, v in zip(known[len(prefix) :], line[len(prefix) :], strict=True)
            ):
                out.append(tuple(line))
            return
        run = clues[i]
        remaining = sum(clues[i + 1 :]) + len(clues) - i - 1
        for pos in range(start, length - run - remaining + 1):
            gap = [EMPTY] * (pos - len(prefix))
            block = [FILLED] * run
            segment = gap + block
            sep = [EMPTY] if i + 1 < len(clues) else []
            candidate = prefix + segment + sep
            offset = len(prefix)
            if all(known[offset + j] in (UNKNOWN, v) for j, v in enumerate(segment + sep)):
                place(i + 1, pos + run + 1, candidate)
            if known[pos] == FILLED:  # a filled cell can't be skipped over
                break

    place(0, 0, [])
    return tuple(out)


def solve_line(clues: Sequence[int], known: Line) -> Line | None:
    """Cells forced by ``clues`` given ``known``; ``None`` if contradictory."""
    options = _placements(tuple(clues), known)
    if not options:
        return None
    return tuple(
        options[0][i] if all(o[i] == options[0][i] for o in options) else UNKNOWN
        for i in range(len(known))
    )


def solve(row_clues: list[list[int]], col_clues: list[list[int]]) -> list[list[int]] | None:
    """Line-logic solve. Returns the grid if fully determined, else ``None``."""
    h, w = len(row_clues), len(col_clues)
    grid = [[UNKNOWN] * w for _ in range(h)]
    changed = True
    while changed:
        changed = False
        for r in range(h):
            line = solve_line(row_clues[r], tuple(grid[r]))
            if line is None:
                return None
            if list(line) != grid[r]:
                grid[r] = list(line)
                changed = True
        for c in range(w):
            column = tuple(grid[r][c] for r in range(h))
            line = solve_line(col_clues[c], column)
            if line is None:
                return None
            if line != column:
                for r in range(h):
                    grid[r][c] = line[r]
                changed = True
    if any(UNKNOWN in row for row in grid):
        return None
    return grid


def is_logic_solvable(puzzle: Puzzle) -> bool:
    grid = solve(puzzle.row_clues, puzzle.col_clues)
    if grid is None:
        return False
    return all(
        (grid[r][c] == FILLED) == puzzle.filled(r, c)
        for r in range(puzzle.height)
        for c in range(puzzle.width)
    )


def generate(size: int, rng: random.Random, density: float = 0.58, attempts: int = 400) -> Puzzle:
    """A random ``size``×``size`` puzzle that line logic can solve uniquely."""
    for _ in range(attempts):
        rows = tuple(
            "".join("#" if rng.random() < density else "." for _ in range(size))
            for _ in range(size)
        )
        puzzle = Puzzle(f"Random {size}×{size}", rows, (14, 165, 233))
        if is_logic_solvable(puzzle):
            return puzzle
    raise RuntimeError("could not generate a solvable puzzle")  # pragma: no cover


# ---------------------------------------------------------------------- play state
@dataclass
class Board:
    puzzle: Puzzle
    marks: list[list[int]] = field(default_factory=list)
    _undo: list[list[list[int]]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.marks:
            self.marks = [[BLANK] * self.puzzle.width for _ in range(self.puzzle.height)]

    def cells(self) -> Iterator[tuple[int, int]]:
        for r in range(self.puzzle.height):
            for c in range(self.puzzle.width):
                yield r, c

    def checkpoint(self) -> None:
        """Remember the grid (call once at the start of a stroke) for undo."""
        self._undo.append([row[:] for row in self.marks])

    def set(self, r: int, c: int, mark: int) -> None:
        self.marks[r][c] = mark

    def undo(self) -> bool:
        if not self._undo:
            return False
        self.marks = self._undo.pop()
        return True

    def clear(self) -> None:
        self.checkpoint()
        self.marks = [[BLANK] * self.puzzle.width for _ in range(self.puzzle.height)]

    @property
    def solved(self) -> bool:
        return all((self.marks[r][c] == FILL) == self.puzzle.filled(r, c) for r, c in self.cells())

    def row_done(self, r: int) -> bool:
        """The row's filled cells match its clue (so the clue can be greyed out)."""
        return runs([m == FILL for m in self.marks[r]]) == self.puzzle.row_clues[r]

    def col_done(self, c: int) -> bool:
        return runs([row[c] == FILL for row in self.marks]) == self.puzzle.col_clues[c]

    def to_json(self) -> list[str]:
        return ["".join(str(m) for m in row) for row in self.marks]

    @classmethod
    def from_json(cls, puzzle: Puzzle, data: object) -> Board:
        board = cls(puzzle)
        if (
            isinstance(data, list)
            and len(data) == puzzle.height
            and all(
                isinstance(r, str) and len(r) == puzzle.width and set(r) <= set("012") for r in data
            )
        ):
            board.marks = [[int(ch) for ch in row] for row in data]
        return board
