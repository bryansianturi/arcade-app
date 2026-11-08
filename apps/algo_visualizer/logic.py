"""The plug-in points and runners for the visualizer. No pygame.

An algorithm is a generator function registered with a decorator. It does its
normal work and *yields a step* whenever there is something to show:

* sorting algorithms take the list to sort, sort it **in place**, and yield
  :class:`Compare`, :class:`Swap` and :class:`Write` steps
  (see :mod:`apps.algo_visualizer.sorting`);
* pathfinding algorithms take a :class:`Grid` and yield :class:`Visit`,
  :class:`Frontier` and finally :class:`Found` or :class:`NotFound`
  (see :mod:`apps.algo_visualizer.pathfinding`).

The runners (:class:`SortRun`, :class:`PathRun`) pull one step at a time, keep
the counters and remember what to highlight. To add an algorithm, write the
generator in either module (or a new one imported by ``app.py``) and decorate
it with :func:`sorting_algorithm` or :func:`pathfinding_algorithm`; the app
builds its buttons from these registries.
"""

from __future__ import annotations

import random
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field

Cell = tuple[int, int]


# ---------------------------------------------------------------------- sorting
@dataclass(frozen=True)
class Compare:
    i: int
    j: int


@dataclass(frozen=True)
class Swap:
    """Yielded *after* ``values[i]`` and ``values[j]`` were swapped."""

    i: int
    j: int


@dataclass(frozen=True)
class Write:
    """Yielded *after* ``values[i]`` was overwritten (merge-style algorithms)."""

    i: int


SortStep = Compare | Swap | Write
SortAlgorithm = Callable[[list[int]], Iterator[SortStep]]
SORTS: dict[str, SortAlgorithm] = {}


def sorting_algorithm(name: str) -> Callable[[SortAlgorithm], SortAlgorithm]:
    """Register a sorting generator under ``name`` (the button label)."""

    def register(fn: SortAlgorithm) -> SortAlgorithm:
        SORTS[name] = fn
        return fn

    return register


@dataclass
class SortRun:
    """Steps one sorting algorithm through ``values`` and counts what it does."""

    values: list[int]
    algorithm: SortAlgorithm
    comparisons: int = 0
    swaps: int = 0
    writes: int = 0
    steps: int = 0
    last: SortStep | None = None
    done: bool = False
    _steps: Iterator[SortStep] | None = None

    def advance(self) -> bool:
        """Do one step. Returns ``False`` once the algorithm has finished."""
        if self.done:
            return False
        if self._steps is None:
            self._steps = self.algorithm(self.values)
        try:
            step = next(self._steps)
        except StopIteration:
            self.done = True
            self.last = None
            return False
        self.steps += 1
        self.last = step
        if isinstance(step, Compare):
            self.comparisons += 1
        elif isinstance(step, Swap):
            self.swaps += 1
        else:
            self.writes += 1
        return True

    def finish(self, limit: int = 10_000_000) -> None:
        for _ in range(limit):
            if not self.advance():
                return

    def highlighted(self) -> tuple[int, ...]:
        if isinstance(self.last, Compare | Swap):
            return (self.last.i, self.last.j)
        if isinstance(self.last, Write):
            return (self.last.i,)
        return ()


def make_values(n: int, order: str, rng: random.Random) -> list[int]:
    """``1..n`` arranged as ``"random"``, ``"reversed"`` or ``"nearly"`` (sorted)."""
    values = list(range(1, n + 1))
    if order == "reversed":
        values.reverse()
    elif order == "nearly" and n > 1:
        for _ in range(max(1, n // 10)):
            i = rng.randrange(n - 1)
            values[i], values[i + 1] = values[i + 1], values[i]
    else:
        rng.shuffle(values)
    return values


# ---------------------------------------------------------------------- pathfinding
@dataclass
class Grid:
    """A 4-connected grid with walls and costlier "mud" cells."""

    width: int
    height: int
    start: Cell
    goal: Cell
    walls: set[Cell] = field(default_factory=set)
    mud: set[Cell] = field(default_factory=set)

    MUD_COST = 5

    def inside(self, cell: Cell) -> bool:
        return 0 <= cell[0] < self.width and 0 <= cell[1] < self.height

    def passable(self, cell: Cell) -> bool:
        return self.inside(cell) and cell not in self.walls

    def cost(self, cell: Cell) -> int:
        """Cost of stepping *into* ``cell``."""
        return self.MUD_COST if cell in self.mud else 1

    def neighbors(self, cell: Cell) -> Iterator[Cell]:
        x, y = cell
        for nxt in ((x + 1, y), (x, y + 1), (x - 1, y), (x, y - 1)):
            if self.passable(nxt):
                yield nxt

    def path_cost(self, path: list[Cell]) -> int:
        return sum(self.cost(c) for c in path[1:])

    def clear(self) -> None:
        self.walls.clear()
        self.mud.clear()

    def random_walls(self, rng: random.Random, density: float = 0.28) -> None:
        self.clear()
        for y in range(self.height):
            for x in range(self.width):
                if (x, y) not in (self.start, self.goal) and rng.random() < density:
                    self.walls.add((x, y))

    def maze(self, rng: random.Random) -> None:
        """Carve a perfect maze (randomised depth-first search) on the odd cells.

        Start and goal are moved onto the nearest carved cells, so a path always exists.
        """
        self.clear()
        self.walls = {(x, y) for y in range(self.height) for x in range(self.width)}
        first = (1, 1)
        self.walls.discard(first)
        stack = [first]
        while stack:
            x, y = stack[-1]
            options = [
                (x + dx, y + dy)
                for dx, dy in ((2, 0), (-2, 0), (0, 2), (0, -2))
                if 0 < x + dx < self.width - 1
                and 0 < y + dy < self.height - 1
                and (x + dx, y + dy) in self.walls
            ]
            if not options:
                stack.pop()
                continue
            nx, ny = rng.choice(options)
            self.walls.discard(((x + nx) // 2, (y + ny) // 2))
            self.walls.discard((nx, ny))
            stack.append((nx, ny))
        self.start = self._nearest_open(self.start)
        self.goal = self._nearest_open(self.goal)

    def _nearest_open(self, cell: Cell) -> Cell:
        open_cells = [
            (x, y)
            for y in range(self.height)
            for x in range(self.width)
            if (x, y) not in self.walls
        ]
        return min(open_cells, key=lambda c: abs(c[0] - cell[0]) + abs(c[1] - cell[1]))


@dataclass(frozen=True)
class Visit:
    """A cell taken off the frontier and expanded."""

    cell: Cell


@dataclass(frozen=True)
class Frontier:
    """A cell discovered and queued for a visit."""

    cell: Cell


@dataclass(frozen=True)
class Found:
    path: tuple[Cell, ...]  # start to goal, inclusive


@dataclass(frozen=True)
class NotFound:
    pass


PathStep = Visit | Frontier | Found | NotFound
PathAlgorithm = Callable[[Grid], Iterator[PathStep]]
PATHFINDERS: dict[str, PathAlgorithm] = {}


def pathfinding_algorithm(name: str) -> Callable[[PathAlgorithm], PathAlgorithm]:
    """Register a pathfinding generator under ``name`` (the button label)."""

    def register(fn: PathAlgorithm) -> PathAlgorithm:
        PATHFINDERS[name] = fn
        return fn

    return register


def trace(came_from: dict[Cell, Cell | None], goal: Cell) -> tuple[Cell, ...]:
    """Follow ``came_from`` links back from ``goal`` to the start."""
    path: list[Cell] = []
    cell: Cell | None = goal
    while cell is not None:
        path.append(cell)
        cell = came_from[cell]
    return tuple(reversed(path))


@dataclass
class PathRun:
    """Steps one pathfinding algorithm and keeps what the grid should show."""

    grid: Grid
    algorithm: PathAlgorithm
    visited: set[Cell] = field(default_factory=set)
    frontier: set[Cell] = field(default_factory=set)
    order: dict[Cell, int] = field(default_factory=dict)  # visit number, for the color ramp
    path: tuple[Cell, ...] = ()
    steps: int = 0
    done: bool = False
    found: bool | None = None
    current: Cell | None = None
    _steps: Iterator[PathStep] | None = None

    def advance(self) -> bool:
        if self.done:
            return False
        if self._steps is None:
            self._steps = self.algorithm(self.grid)
        try:
            step = next(self._steps)
        except StopIteration:
            step = NotFound()
        self.steps += 1
        if isinstance(step, Visit):
            self.visited.add(step.cell)
            self.frontier.discard(step.cell)
            self.order.setdefault(step.cell, len(self.order))
            self.current = step.cell
        elif isinstance(step, Frontier):
            if step.cell not in self.visited:
                self.frontier.add(step.cell)
        else:
            self.done = True
            self.current = None
            self.found = isinstance(step, Found)
            if isinstance(step, Found):
                self.path = step.path
        return not self.done

    def finish(self, limit: int = 10_000_000) -> None:
        for _ in range(limit):
            if not self.advance():
                return
