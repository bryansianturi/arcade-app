from __future__ import annotations

import random

import pygame
import pytest

from apps.game_of_life.logic import (
    PATTERNS,
    RULES,
    Life,
    parse_rle,
    parse_rule,
    rotate,
)
from core.base_app import AppContext
from tests.conftest import click, tap

PATTERN = {p.name: p for p in PATTERNS}


def evolve(name: str, generations: int, wrap: bool = False) -> list[frozenset[tuple[int, int]]]:
    life = Life(120, 80, wrap=wrap)
    life.stamp(PATTERN[name].cells, (40, 30))
    history = [frozenset(life.cells)]
    for _ in range(generations):
        life.step()
        history.append(frozenset(life.cells))
    return history


def test_rle_parsing() -> None:
    assert parse_rle("bob$2bo$3o!") == {(1, 0), (2, 1), (0, 2), (1, 2), (2, 2)}
    assert parse_rle("#C comment\nx = 3, y = 2\n2o$\nbo!") == {(0, 0), (1, 0), (1, 1)}
    assert parse_rle("o2$o!") == {(0, 0), (0, 2)}  # "2$" skips a blank row
    with pytest.raises(ValueError):
        parse_rle("o?o!")


def test_rule_parsing() -> None:
    rule = parse_rule("b36/s23")
    assert rule.birth == {3, 6} and rule.survive == {2, 3} and rule.notation == "B36/S23"
    assert parse_rule("B2/S").survive == frozenset()
    with pytest.raises(ValueError):
        parse_rule("23/3")
    assert [r.notation for r in RULES] == ["B3/S23", "B36/S23", "B3678/S34678", "B2/S"]


def test_blinker_oscillates() -> None:
    life = Life(5, 5, wrap=False, cells={(1, 2), (2, 2), (3, 2)})
    life.step()
    assert life.cells == {(2, 1), (2, 2), (2, 3)} and life.generation == 1
    life.step()
    assert life.cells == {(1, 2), (2, 2), (3, 2)}


def test_glider_travels_and_wraps() -> None:
    history = evolve("Glider", 4)
    assert {(x - 1, y - 1) for x, y in history[4]} == history[0]
    life = Life(6, 6, wrap=True)
    life.stamp(PATTERN["Glider"].cells, (0, 0))
    start = set(life.cells)
    for _ in range(24):  # 6 cells diagonally on a 6×6 torus brings it home
        life.step()
    assert life.cells == start


def test_dead_edges_stop_a_glider() -> None:
    life = Life(6, 6, wrap=False)
    life.stamp(PATTERN["Glider"].cells, (0, 0))
    for _ in range(40):
        life.step()
    assert life.cells == {(4, 4), (4, 5), (5, 4), (5, 5)}  # ends as a block in the corner


@pytest.mark.parametrize(
    ("name", "period", "population"), [("Pulsar", 3, 48), ("Pentadecathlon", 15, 12)]
)
def test_oscillator_periods(name: str, period: int, population: int) -> None:
    history = evolve(name, period)
    assert history[period] == history[0] and len(history[0]) == population
    assert all(history[i] != history[0] for i in range(1, period))


def test_glider_gun_fires_every_30_generations() -> None:
    history = evolve("Glider gun", 30)
    assert history[0] <= history[30] and len(history[30]) == 36 + 5


def test_diehard_dies_after_130_generations() -> None:
    history = evolve("Diehard", 130)
    assert history[129] and not history[130]


def test_highlife_replicator_differs_from_conway() -> None:
    # In HighLife, six neighbours also give birth.
    cells = {(0, 0), (1, 0), (2, 0), (0, 1), (2, 1), (1, 2)}  # (1, 1) has six live neighbours
    conway = Life(10, 10, RULES[0], cells=set(cells))
    highlife = Life(10, 10, RULES[1], cells=set(cells))
    conway.step()
    highlife.step()
    assert (1, 1) in highlife.cells and (1, 1) not in conway.cells


def test_survive_zero_keeps_lonely_cells() -> None:
    life = Life(5, 5, parse_rule("B3/S0"), cells={(2, 2)})
    life.step()
    assert life.cells == {(2, 2)}


def test_rotate_and_stamp() -> None:
    glider = PATTERN["Glider"].cells
    assert rotate(rotate(rotate(rotate(glider)))) == glider
    assert rotate(frozenset({(0, 0), (1, 0), (2, 0)})) == {(0, 0), (0, 1), (0, 2)}
    life = Life(4, 4, wrap=True)
    life.stamp(frozenset({(0, 0), (1, 0)}), (3, 3))
    assert life.cells == {(3, 3), (0, 3)}
    life.wrap = False
    life.clear()
    life.stamp(frozenset({(0, 0), (1, 0)}), (3, 3))
    assert life.cells == {(3, 3)}


def test_randomize_density() -> None:
    life = Life(100, 100)
    life.randomize(random.Random(1), 0.3)
    assert 2700 < len(life.cells) < 3300 and life.generation == 0


def test_app_draw_step_and_save(app_context: AppContext) -> None:
    from apps.game_of_life.app import GRID, GameOfLifeApp

    app = GameOfLifeApp(app_context)
    app.on_enter()
    assert len(app.life.cells) == 36  # starts with the glider gun
    tap(app, pygame.K_c)
    for x in range(3):  # a blinker, clicked in
        for event in click((GRID.x + 105 + x * 10, GRID.y + 205)):
            app.handle_event(event)
    assert app.life.cells == {(10, 20), (11, 20), (12, 20)}
    tap(app, pygame.K_RIGHT)
    assert app.life.cells == {(11, 19), (11, 20), (11, 21)}
    tap(app, pygame.K_SPACE)
    for _ in range(30):
        app.update(1 / 60)
    assert app.running and app.life.generation > 1
    tap(app, pygame.K_1)  # pick the glider to stamp
    assert app.captures_pause()
    tap(app, pygame.K_ESCAPE)
    assert app.stamp is None
    app.on_exit()
    again = GameOfLifeApp(app_context)
    again.on_enter()
    assert again.life.cells == app.life.cells
