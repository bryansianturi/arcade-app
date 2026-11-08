"""Pathfinding algorithms for the visualizer. Each searches a grid and yields steps.

Add one by writing a generator and decorating it::

    @pathfinding_algorithm("Greedy")
    def greedy(grid: Grid) -> Iterator[PathStep]:
        ...
"""

from __future__ import annotations

import heapq
import itertools
from collections import deque
from collections.abc import Callable, Iterator

from apps.algo_visualizer.logic import (
    Cell,
    Found,
    Frontier,
    Grid,
    NotFound,
    PathStep,
    Visit,
    pathfinding_algorithm,
    trace,
)


@pathfinding_algorithm("BFS")
def breadth_first(grid: Grid) -> Iterator[PathStep]:
    """Explore in rings of equal step count. Fewest steps, but blind to mud."""
    came_from: dict[Cell, Cell | None] = {grid.start: None}
    queue = deque([grid.start])
    while queue:
        cell = queue.popleft()
        yield Visit(cell)
        if cell == grid.goal:
            yield Found(trace(came_from, cell))
            return
        for nxt in grid.neighbors(cell):
            if nxt not in came_from:
                came_from[nxt] = cell
                queue.append(nxt)
                yield Frontier(nxt)
    yield NotFound()


def _best_first(grid: Grid, heuristic: Callable[[Cell], int]) -> Iterator[PathStep]:
    """Shared by Dijkstra (no heuristic) and A*: expand the cheapest estimated cell."""
    came_from: dict[Cell, Cell | None] = {grid.start: None}
    cost: dict[Cell, int] = {grid.start: 0}
    tie = itertools.count()  # FIFO among equal priorities keeps the search tidy
    queue: list[tuple[int, int, Cell]] = [(heuristic(grid.start), next(tie), grid.start)]
    done: set[Cell] = set()
    while queue:
        _, _, cell = heapq.heappop(queue)
        if cell in done:
            continue  # a stale entry: the cell was already reached more cheaply
        done.add(cell)
        yield Visit(cell)
        if cell == grid.goal:
            yield Found(trace(came_from, cell))
            return
        for nxt in grid.neighbors(cell):
            new_cost = cost[cell] + grid.cost(nxt)
            if nxt not in cost or new_cost < cost[nxt]:
                cost[nxt] = new_cost
                came_from[nxt] = cell
                heapq.heappush(queue, (new_cost + heuristic(nxt), next(tie), nxt))
                yield Frontier(nxt)
    yield NotFound()


@pathfinding_algorithm("Dijkstra")
def dijkstra(grid: Grid) -> Iterator[PathStep]:
    """Expand the cheapest cell so far. Cheapest path, mud included."""
    return _best_first(grid, lambda cell: 0)


@pathfinding_algorithm("A*")
def a_star(grid: Grid) -> Iterator[PathStep]:
    """Dijkstra steered by the Manhattan distance to the goal (never overestimates)."""
    gx, gy = grid.goal
    return _best_first(grid, lambda cell: abs(cell[0] - gx) + abs(cell[1] - gy))
