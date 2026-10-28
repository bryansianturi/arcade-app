from __future__ import annotations

import random

import pytest

from apps.stackfall.logic import (
    HIDDEN,
    KINDS,
    LINE_POINTS,
    LOCK_DELAY,
    TOTAL_ROWS,
    WIDTH,
    Bag,
    Kind,
    Piece,
    Stackfall,
    gravity_interval,
    rotated_cells,
)
from core.base_app import AppContext


def game(first: Kind = "T") -> Stackfall:
    g = Stackfall(random.Random(0))
    g.piece = g._spawn(first)
    return g


def fill_row(g: Stackfall, y: int, gap: int | None = None) -> None:
    g.grid[y] = ["O" if x != gap else None for x in range(WIDTH)]


@pytest.mark.parametrize("kind", KINDS)
def test_rotations_are_cyclic_and_keep_four_cells(kind: Kind) -> None:
    assert rotated_cells(kind, 4) == rotated_cells(kind, 0)
    for r in range(4):
        assert len(set(rotated_cells(kind, r))) == 4


def test_bag_contains_each_kind_once_per_seven() -> None:
    bag = Bag(random.Random(3))
    for _ in range(4):
        assert sorted(bag.next() for _ in range(7)) == sorted(KINDS)


def test_spawn_is_centred_in_hidden_rows() -> None:
    g = game("T")
    xs = [x for x, _ in g.piece.cells()]
    assert min(xs) >= 3 and max(xs) <= 6
    assert all(y < HIDDEN + 1 for _, y in g.piece.cells())


def test_move_stops_at_walls() -> None:
    g = game("O")
    for _ in range(10):
        g.move(-1)
    assert min(x for x, _ in g.piece.cells()) == 0
    assert not g.move(-1)


def test_rotation_kicks_off_the_wall() -> None:
    g = game("I")
    g.rotate(1)  # vertical
    for _ in range(10):
        g.move(1)
    assert max(x for x, _ in g.piece.cells()) == WIDTH - 1
    assert g.rotate(1)  # horizontal again: needs a kick to the left
    assert max(x for x, _ in g.piece.cells()) <= WIDTH - 1


def test_rotation_fails_when_blocked_everywhere() -> None:
    g = game("I")
    g.grid = [["O"] * WIDTH for _ in range(TOTAL_ROWS)]
    for x, y in g.piece.cells():
        g.grid[y][x] = None
    assert not g.rotate(1)


def test_gravity_and_lock_delay() -> None:
    g = game("O")
    start = g.piece.y
    g.update(gravity_interval(1) + 0.001)
    assert g.piece.y == start + 1
    g.piece = g.ghost()
    assert not g.update(LOCK_DELAY / 2).locked
    assert g.update(LOCK_DELAY / 2 + 0.01).locked


def test_moving_resets_lock_delay() -> None:
    g = game("O")
    g.piece = g.ghost()
    g.update(LOCK_DELAY * 0.8)
    g.move(1)
    assert not g.update(LOCK_DELAY * 0.8).locked  # timer restarted


def test_hard_drop_scores_and_locks() -> None:
    g = game("O")
    distance = g.ghost().y - g.piece.y
    result = g.hard_drop()
    assert result.locked and g.score == 2 * distance
    assert g.grid[TOTAL_ROWS - 1][4] == "O"


def test_soft_drop_scores_one_per_row() -> None:
    g = game("T")
    assert g.soft_drop() and g.score == 1


@pytest.mark.parametrize("n", [1, 2, 3, 4])
def test_line_clears_and_scoring(n: int) -> None:
    g = game("I")
    for i in range(n):
        fill_row(g, TOTAL_ROWS - 1 - i, gap=0)
    g.rotate(1)  # vertical I
    while g.move(-1):
        pass
    result = g.hard_drop()
    assert len(result.cleared) == n
    assert g.lines == n
    assert g.score >= LINE_POINTS[n]
    # Whatever is left of the I piece (4 - n cells) has dropped to the bottom of column 0.
    assert [g.grid[TOTAL_ROWS - 1 - i][0] for i in range(4 - n)] == ["I"] * (4 - n)


def test_rows_above_a_clear_shift_down() -> None:
    g = game("O")
    fill_row(g, TOTAL_ROWS - 1, gap=4)
    fill_row(g, TOTAL_ROWS - 2, gap=4)
    g.grid[TOTAL_ROWS - 3][0] = "Z"
    g.piece = Piece("I", 2, 0, 1)  # vertical I sits in box column 2, so this is board column 4
    assert g.fits(g.piece)
    g.hard_drop()
    assert g.lines == 2
    assert g.grid[TOTAL_ROWS - 1][0] == "Z"


def test_level_and_speed_increase() -> None:
    g = game()
    g.lines = 25
    assert g.level == 3
    assert gravity_interval(3) < gravity_interval(1)


def test_hold_swaps_once_per_piece() -> None:
    g = game("T")
    assert g.hold()
    assert g.hold_kind == "T"
    assert not g.hold()  # only once until the next lock
    g.hard_drop()
    current = g.piece.kind
    assert g.hold()
    assert g.piece.kind == "T" and g.hold_kind == current


def stack_to_spawn(g: Stackfall) -> None:
    """Fill every row just below the spawn area, leaving the last column open so none clear."""
    for y in range(HIDDEN + 1, TOTAL_ROWS):
        fill_row(g, y, gap=WIDTH - 1)


def test_game_over_when_spawn_is_blocked() -> None:
    g = game("O")
    stack_to_spawn(g)
    result = g.hard_drop()  # the O can't fall, so it locks inside the spawn area...
    assert result.game_over and g.over  # ...and the next piece has nowhere to appear
    assert g.update(1).game_over


def test_app_game_over_records_score(app_context: AppContext) -> None:
    from apps.stackfall.app import StackfallApp

    app = StackfallApp(app_context)
    app.on_enter()
    app.rng = random.Random(0)  # deterministic pieces
    app._start()
    app.game.score = 4321
    stack_to_spawn(app.game)
    app._after_step(app.game.hard_drop())
    assert app.state == "over" and app.new_best
    best = app.best_score()
    assert best is not None and best.score >= 4321


def test_app_ignores_os_key_repeat(app_context: AppContext) -> None:
    import pygame

    from apps.stackfall.app import StackfallApp
    from tests.conftest import hold

    app = StackfallApp(app_context)
    app.on_enter()
    app._start()
    x = app.game.piece.x
    hold(app, pygame.K_LEFT)
    hold(app, pygame.K_LEFT)  # an OS repeat while held: ignored
    assert app.game.piece.x == x - 1
