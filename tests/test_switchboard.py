"""Switchboard (lights puzzle) rules and solver."""

from __future__ import annotations

import random

import pytest

from apps.switchboard.logic import Switchboard, neighbourhood, solve
from core.base_app import AppContext


def test_press_flips_the_plus_shape_and_twice_cancels() -> None:
    b = Switchboard(5)
    b.press((2, 2))
    assert b.lights == {(2, 2), (1, 2), (3, 2), (2, 1), (2, 3)}
    b.press((0, 0))
    assert {(0, 0), (1, 0), (0, 1)} <= b.lights
    b.press((0, 0))
    b.press((2, 2))
    assert b.solved and b.presses == 4
    assert b.undo() and len(b.lights) == 5 and b.presses == 3


def test_neighbourhood_at_edges() -> None:
    assert len(neighbourhood(4, (0, 0))) == 3 and len(neighbourhood(4, (1, 1))) == 5


@pytest.mark.parametrize("size", [3, 4, 5, 6])
def test_solver_finds_a_minimal_valid_solution(size: int) -> None:
    rng = random.Random(size)
    for _ in range(5):
        board = Switchboard.random(size, rng, presses=3)
        presses = solve(size, board.lights)
        assert presses is not None and len(presses) <= 3
        for cell in presses:
            board.press(cell, record=False)
        assert board.solved


def test_unsolvable_pattern_on_5x5() -> None:
    # A single lit corner isn't reachable on 5x5 (the board has a non-trivial null space).
    assert solve(5, {(0, 0)}) is None
    assert solve(4, {(0, 0)}) is None  # 4x4 has an even bigger null space
    assert solve(3, {(0, 0)}) is not None and solve(6, {(0, 0)}) is not None  # full rank


def test_random_puzzles_are_never_already_solved() -> None:
    rng = random.Random(1)
    assert all(not Switchboard.random(5, rng).solved for _ in range(30))


def test_switchboard_app(app_context: AppContext) -> None:
    from apps.switchboard.app import SwitchboardApp

    app = SwitchboardApp(app_context)
    app.on_enter()
    for cell in solve(app.size, app.board.lights) or []:
        app._press(cell)
    assert app.board.solved and app.menu is not None
    assert app.board.presses == app.par
