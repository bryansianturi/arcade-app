from __future__ import annotations

import random

import pytest

from apps.twenty48.logic import GOAL, SIZE, Direction, Game2048, Slide, line
from core.base_app import AppContext


def game_with(grid: list[list[int]], seed: int = 0) -> Game2048:
    return Game2048(random.Random(seed), [row[:] for row in grid])


def row_after(values: list[int], direction: Direction = "left") -> list[int]:
    g = game_with([values, [0] * 4, [0] * 4, [0] * 4])
    g.rng = random.Random(0)
    g.spawn = lambda: None  # type: ignore[method-assign]  # keep the board deterministic
    g.move(direction)
    return g.grid[0]


@pytest.mark.parametrize(
    ("before", "after"),
    [
        ([2, 2, 0, 0], [4, 0, 0, 0]),
        ([2, 0, 0, 2], [4, 0, 0, 0]),
        ([2, 2, 2, 0], [4, 2, 0, 0]),
        ([2, 2, 2, 2], [4, 4, 0, 0]),  # each tile merges at most once
        ([4, 4, 8, 0], [8, 8, 0, 0]),  # a merged tile can't merge again this move
        ([2, 4, 2, 4], [2, 4, 2, 4]),
        ([0, 0, 0, 2], [2, 0, 0, 0]),
        ([8, 0, 8, 8], [16, 8, 0, 0]),
    ],
)
def test_slide_left(before: list[int], after: list[int]) -> None:
    assert row_after(before) == after


def test_slide_right_merges_from_the_right() -> None:
    assert row_after([2, 2, 2, 0], "right") == [0, 0, 2, 4]


def test_vertical_moves() -> None:
    g = game_with([[2, 0, 0, 0], [2, 0, 0, 0], [4, 0, 0, 0], [0, 0, 0, 0]])
    g.spawn = lambda: None  # type: ignore[method-assign]
    g.move("down")
    assert [g.grid[r][0] for r in range(SIZE)] == [0, 0, 4, 4]
    g.move("up")
    assert [g.grid[r][0] for r in range(SIZE)] == [8, 0, 0, 0]


def test_line_order() -> None:
    assert line("left", 1) == [(1, 0), (1, 1), (1, 2), (1, 3)]
    assert line("down", 2) == [(3, 2), (2, 2), (1, 2), (0, 2)]


def test_move_result_and_score() -> None:
    g = game_with([[2, 2, 4, 0], [0] * 4, [0] * 4, [0] * 4])
    result = g.move("left")
    assert result.moved and result.gained == 4 and g.score == 4
    assert result.merged == [(0, 0)]
    assert Slide(2, (0, 1), (0, 0)) in result.slides
    assert Slide(4, (0, 2), (0, 1)) in result.slides
    assert result.spawned is not None and g.grid[result.spawned[0]][result.spawned[1]] in (2, 4)


def test_no_op_move_does_not_spawn() -> None:
    g = game_with([[2, 4, 0, 0], [0] * 4, [0] * 4, [0] * 4])
    result = g.move("left")
    assert not result.moved and result.spawned is None
    assert sum(v != 0 for row in g.grid for v in row) == 2


def test_new_game_has_two_tiles() -> None:
    g = Game2048.new(random.Random(3))
    tiles = [v for row in g.grid for v in row if v]
    assert len(tiles) == 2 and set(tiles) <= {2, 4}


def test_game_over_detection() -> None:
    full = [[2, 4, 2, 4], [4, 2, 4, 2], [2, 4, 2, 4], [4, 2, 4, 2]]
    assert not game_with(full).can_move()
    full[3][3] = 4  # now (3,2) and (3,3) are both 4
    assert game_with(full).can_move()


# Moving right leaves only (3, 0) empty; a 4 spawns there and no moves remain.
LAST_MOVE = [[2, 4, 2, 4], [4, 2, 4, 2], [2, 4, 2, 4], [8, 16, 32, 0]]


def force_four(g: Game2048) -> None:
    g.rng.random = lambda: 0.0  # type: ignore[method-assign]  # next spawn is a 4


def test_last_move_ends_the_game() -> None:
    g = game_with(LAST_MOVE)
    force_four(g)
    result = g.move("right")
    assert result.spawned == (3, 0) and g.grid[3] == [4, 8, 16, 32]
    assert g.over
    assert not g.move("left").moved  # nothing happens after game over


def test_reaching_goal_sets_won() -> None:
    half = GOAL // 2
    g = game_with([[half, half, 0, 0], [0] * 4, [0] * 4, [0] * 4])
    g.move("left")
    assert g.won and g.grid[0][0] == GOAL


def test_app_saves_and_resumes(app_context: AppContext) -> None:
    from apps.twenty48.app import Twenty48App

    app = Twenty48App(app_context)
    app.on_enter()
    app.game = game_with([[2, 2, 0, 0], [0] * 4, [0] * 4, [0] * 4])
    app._move("left")
    app.on_exit()
    best = app.best_score()
    assert best is not None and best.score == 4

    again = Twenty48App(app_context)
    again.on_enter()
    assert again.game.score == 4 and again.game.grid == app.game.grid


def test_app_game_over_dialog(app_context: AppContext) -> None:
    from apps.twenty48.app import Twenty48App

    app = Twenty48App(app_context)
    app.on_enter()
    app.game = game_with(LAST_MOVE)
    app.game.score = 500
    force_four(app.game)
    app._move("right")
    assert app.dialog == "over" and app.new_best
    app.on_exit()
    assert "saved_game" not in app_context.storage.app_data("2048")  # finished games aren't resumed
