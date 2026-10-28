from __future__ import annotations

import random

import pytest

from apps.minesweeper.logic import DIFFICULTIES, SIZES, Difficulty, Minefield
from core.base_app import AppContext


def field_with(mines: set[tuple[int, int]], w: int = 5, h: int = 5) -> Minefield:
    """A field with mines placed by hand (skips random placement)."""
    f = Minefield(w, h, len(mines), random.Random(0))
    f.mines = set(mines)
    f.status = "playing"
    return f


@pytest.mark.parametrize("difficulty", DIFFICULTIES)
@pytest.mark.parametrize("seed", range(5))
def test_first_click_is_always_safe_and_opens_an_area(difficulty: Difficulty, seed: int) -> None:
    f = Minefield.for_difficulty(difficulty, random.Random(seed))
    w, h, m = SIZES[difficulty]
    click = (seed % w, (seed * 3) % h)  # includes corners and edges
    f.reveal(click)
    assert f.status in ("playing", "won")
    assert len(f.mines) == m
    assert click not in f.mines and not any(n in f.mines for n in f.neighbors(click))
    assert f.adjacent_mines(click) == 0 and len(f.revealed) > 1


def test_too_many_mines_rejected() -> None:
    with pytest.raises(ValueError):
        Minefield(3, 3, 1)


def test_neighbors_and_counts() -> None:
    f = field_with({(0, 0), (1, 0)})
    assert sorted(f.neighbors((0, 0))) == [(0, 1), (1, 0), (1, 1)]
    assert len(list(f.neighbors((2, 2)))) == 8
    assert f.adjacent_mines((0, 1)) == 2 and f.adjacent_mines((4, 4)) == 0


def test_flood_fill_stops_at_numbers() -> None:
    f = field_with({(4, 4)})
    f.reveal((0, 0))
    assert (4, 4) not in f.revealed
    assert f.status == "won"  # only one mine, so the flood fill opens everything else
    assert f.flags == {(4, 4)}  # winning auto-flags remaining mines


def test_revealing_a_mine_loses() -> None:
    f = field_with({(2, 2), (0, 4)})
    f.reveal((2, 2))
    assert f.status == "lost" and f.exploded == (2, 2)
    f.reveal((0, 0))
    assert (0, 0) not in f.revealed  # board is frozen


def test_flags_block_reveal_and_count_down() -> None:
    f = field_with({(2, 2), (0, 4)})
    f.toggle_flag((2, 2))
    assert f.mines_left == 1
    f.reveal((2, 2))
    assert f.status == "playing"
    f.toggle_flag((2, 2))
    assert f.mines_left == 2


def test_cannot_flag_revealed_cells() -> None:
    f = field_with({(4, 4), (4, 3)})
    f.reveal((0, 0))
    f.toggle_flag((0, 0))
    assert (0, 0) not in f.flags


def test_chord_opens_neighbours_when_flags_match() -> None:
    f = field_with({(0, 0), (4, 4)})
    f.reveal((1, 1))
    assert f.revealed == {(1, 1)}
    f.chord((1, 1))  # no flags yet: nothing happens
    assert f.revealed == {(1, 1)}
    f.toggle_flag((0, 0))
    f.chord((1, 1))
    assert {(0, 1), (1, 0), (2, 2)} <= f.revealed
    assert f.status == "won"  # (2, 2) is a zero, so the flood fill clears the rest


def test_chord_with_wrong_flag_loses() -> None:
    f = field_with({(0, 0), (4, 4)})
    f.reveal((1, 1))
    f.toggle_flag((0, 1))  # wrong cell
    f.chord((1, 1))
    assert f.status == "lost" and f.exploded == (0, 0)


def test_timer_runs_only_while_playing() -> None:
    f = Minefield.for_difficulty("easy", random.Random(1))
    f.tick(5)
    assert f.elapsed == 0
    f.reveal((4, 4))
    f.tick(2)
    assert f.elapsed == 2
    f.status = "won"
    f.tick(3)
    assert f.elapsed == 2


def test_app_records_best_time_per_difficulty(app_context: AppContext) -> None:
    from apps.minesweeper.app import MinesweeperApp

    app = MinesweeperApp(app_context)
    app.on_enter()
    app._set_difficulty(2)
    assert (
        app.field.width == 30
        and app_context.storage.app_data("minesweeper")["difficulty"] == "hard"
    )
    app.field = field_with({(4, 4)})
    app.field.elapsed = 61.6
    app._open((0, 0))
    assert app.field.status == "won" and app.new_best
    best = app.best_score("hard")
    assert best is not None and best.score == 62


def test_app_mouse_flag_and_reveal(app_context: AppContext) -> None:
    import pygame

    from apps.minesweeper.app import MinesweeperApp
    from tests.conftest import click

    app = MinesweeperApp(app_context)
    app.on_enter()
    center = app._cell_rect((4, 4)).center
    app.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=center, button=3))
    assert (4, 4) in app.field.flags
    corner = app._cell_rect((0, 0)).center
    for event in click(corner):
        app.handle_event(event)
    assert app.field.status in ("playing", "won") and (0, 0) in app.field.revealed
