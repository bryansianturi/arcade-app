from __future__ import annotations

import itertools
import random
from collections.abc import Iterator

import pygame
import pytest

from apps.algo_visualizer import pathfinding, sorting  # noqa: F401 (registers the algorithms)
from apps.algo_visualizer.logic import (
    PATHFINDERS,
    SORTS,
    Compare,
    Grid,
    PathRun,
    SortRun,
    SortStep,
    Swap,
    make_values,
    sorting_algorithm,
)
from core.base_app import AppContext
from tests.conftest import tap


def test_registries_hold_the_required_algorithms() -> None:
    assert list(SORTS) == ["Bubble", "Insertion", "Merge", "Quick"]
    assert list(PATHFINDERS) == ["BFS", "Dijkstra", "A*"]


@pytest.mark.parametrize("name", list(SORTS))
@pytest.mark.parametrize("order", ["random", "reversed", "nearly"])
def test_every_sort_sorts(name: str, order: str) -> None:
    rng = random.Random(name + order)
    for n in (0, 1, 2, 3, 17, 64):
        values = make_values(n, order, rng) if n else []
        run = SortRun(values, SORTS[name])
        run.finish()
        assert run.done and values == sorted(values) == list(range(1, n + 1))


def test_sorts_with_duplicates() -> None:
    for name, algorithm in SORTS.items():
        values = [3, 1, 3, 2, 1, 3, 2, 2]
        SortRun(values, algorithm).finish()
        assert values == sorted(values), name


def test_step_counts_match_the_algorithms() -> None:
    n = 32
    worst = list(range(n, 0, -1))
    bubble = SortRun(list(worst), SORTS["Bubble"])
    bubble.finish()
    assert bubble.swaps == n * (n - 1) // 2  # every pair is inverted
    sorted_input = SortRun(list(range(n)), SORTS["Insertion"])
    sorted_input.finish()
    assert sorted_input.comparisons == n - 1 and sorted_input.swaps == 0
    merge = SortRun(make_values(n, "random", random.Random(1)), SORTS["Merge"])
    merge.finish()
    assert merge.swaps == 0 and merge.writes == n * 5  # log2(32) levels, n writes each
    quick = SortRun(list(range(1, 257)), SORTS["Quick"])
    quick.finish()
    assert quick.comparisons < 256 * 12  # median of three: no quadratic blow-up on sorted input


def test_sort_run_highlights() -> None:
    run = SortRun([2, 1], SORTS["Bubble"])
    run.advance()
    assert run.last == Compare(0, 1) and run.highlighted() == (0, 1)
    run.advance()
    assert run.last == Swap(0, 1) and run.values == [1, 2]
    run.finish()
    assert run.highlighted() == () and not run.advance()


def test_a_new_algorithm_is_one_decorated_function(app_context: AppContext) -> None:
    @sorting_algorithm("Selection")
    def selection_sort(values: list[int]) -> Iterator[SortStep]:
        for i in range(len(values)):
            low = i
            for j in range(i + 1, len(values)):
                yield Compare(low, j)
                if values[j] < values[low]:
                    low = j
            if low != i:
                values[i], values[low] = values[low], values[i]
                yield Swap(i, low)

    try:
        values = [4, 2, 5, 1, 3]
        SortRun(values, SORTS["Selection"]).finish()
        assert values == [1, 2, 3, 4, 5]
        from apps.algo_visualizer.app import AlgoVisualizerApp

        app = AlgoVisualizerApp(app_context)
        app.on_enter()
        assert "Selection" in [b.text for b in app.sort_buttons]
    finally:
        del SORTS["Selection"]


def open_grid(**kwargs: object) -> Grid:
    return Grid(12, 8, (0, 0), (11, 7), **kwargs)  # type: ignore[arg-type]


def solve(name: str, grid: Grid) -> PathRun:
    run = PathRun(grid, PATHFINDERS[name])
    run.finish()
    assert run.done
    return run


def test_paths_are_valid_and_shortest_on_open_ground() -> None:
    for name in PATHFINDERS:
        run = solve(name, open_grid())
        path = run.path
        assert run.found and path[0] == (0, 0) and path[-1] == (11, 7)
        assert len(path) - 1 == 11 + 7
        for a, b in itertools.pairwise(path):
            assert abs(a[0] - b[0]) + abs(a[1] - b[1]) == 1


def test_mud_separates_bfs_from_dijkstra_and_a_star() -> None:
    # Two columns of mud across rows 0-1; row 2 is a clean detour.
    grid = Grid(9, 3, (0, 0), (8, 0), mud={(4, 0), (5, 0), (4, 1), (5, 1)})
    bfs, dijkstra, a_star = (solve(n, grid) for n in ("BFS", "Dijkstra", "A*"))
    assert len(bfs.path) - 1 == 8  # fewest steps, straight through the mud...
    assert grid.path_cost(list(bfs.path)) == 6 + 2 * Grid.MUD_COST
    assert grid.path_cost(list(dijkstra.path)) == grid.path_cost(list(a_star.path)) == 12
    assert (4, 2) in dijkstra.path and (4, 2) in a_star.path  # ...the others go round


def test_a_star_explores_less_than_dijkstra() -> None:
    rng = random.Random(4)
    for _ in range(20):
        grid = Grid(30, 20, (2, 10), (27, 10))
        grid.random_walls(rng, 0.25)
        grid.mud = {(x, y) for x in range(30) for y in range(20) if rng.random() < 0.1}
        dijkstra, a_star = solve("Dijkstra", grid), solve("A*", grid)
        assert dijkstra.found == a_star.found
        if dijkstra.found:
            assert grid.path_cost(list(dijkstra.path)) == grid.path_cost(list(a_star.path))
            assert len(a_star.visited) <= len(dijkstra.visited)


def test_walled_off_goal_is_reported() -> None:
    grid = open_grid(walls={(10, 7), (11, 6), (10, 6)})
    for name in PATHFINDERS:
        run = solve(name, grid)
        assert run.found is False and run.path == ()


@pytest.mark.parametrize("seed", range(10))
def test_mazes_are_perfect_and_solvable(seed: int) -> None:
    grid = Grid(37, 24, (5, 12), (31, 12))
    grid.maze(random.Random(seed))
    assert grid.passable(grid.start) and grid.passable(grid.goal)
    open_cells = {(x, y) for y in range(24) for x in range(37) if (x, y) not in grid.walls}
    # One connected tree: every open cell reachable, edges = cells - 1.
    seen = {grid.start}
    stack = [grid.start]
    while stack:
        for nxt in grid.neighbors(stack.pop()):
            if nxt not in seen:
                seen.add(nxt)
                stack.append(nxt)
    assert seen == open_cells
    edges = sum(1 for c in open_cells for n in grid.neighbors(c)) // 2
    assert edges == len(open_cells) - 1
    assert solve("BFS", grid).found


def test_app_runs_both_modes(app_context: AppContext) -> None:
    from apps.algo_visualizer.app import AlgoVisualizerApp

    app = AlgoVisualizerApp(app_context)
    app.on_enter()
    app._set_mode(0)
    tap(app, pygame.K_m)  # maze
    tap(app, pygame.K_f)  # finish instantly
    assert app.path_run is not None and app.path_run.found
    tap(app, pygame.K_TAB)
    assert app.mode == 1
    original = list(app.values)
    tap(app, pygame.K_4)  # quicksort
    tap(app, pygame.K_SPACE)
    for _ in range(600):
        app.update(1 / 30)
    assert app.sort_run is not None and app.sort_run.done
    assert app.values == sorted(original)
    tap(app, pygame.K_r)
    assert app.values == original and app.sort_run is None
    app.on_exit()
    again = AlgoVisualizerApp(app_context)
    again.on_enter()
    assert again.mode == 1 and again.sort_name == "Quick"
