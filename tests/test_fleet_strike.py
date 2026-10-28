"""Fleet Strike rules: placement, firing, sinking, and the three computer levels."""

from __future__ import annotations

import random
import statistics

import pygame

from apps.fleet_strike.logic import (
    FLEET,
    LEVELS,
    SIZE,
    Admiral,
    Board,
    Level,
    Ship,
    in_bounds,
    ship_cells,
)
from core.base_app import AppContext


def test_random_fleets_are_legal() -> None:
    for seed in range(50):
        board = Board.random(random.Random(seed))
        assert [(s.name, len(s.cells)) for s in board.ships] == list(FLEET)
        cells = [c for s in board.ships for c in s.cells]
        assert len(cells) == len(set(cells)) == 17
        assert all(in_bounds(c) for c in cells)
        for s in board.ships:  # straight lines
            rows = {r for r, _ in s.cells}
            cols = {c for _, c in s.cells}
            assert len(rows) == 1 or len(cols) == 1


def test_can_place_rejects_overlap_and_edges() -> None:
    board = Board([Ship("A", ship_cells(0, 0, 3, True))])
    assert not board.can_place(ship_cells(0, 2, 2, False))  # overlaps (0, 2)
    assert board.can_place(ship_cells(1, 0, 3, True))  # touching is allowed
    assert not board.can_place(ship_cells(0, SIZE - 1, 2, True))
    ship = board.ships[0]
    assert board.can_place(ship_cells(0, 1, 3, True), ignore=ship)  # moving a ship over itself


def test_fire_hits_misses_sinks_and_repeats() -> None:
    board = Board([Ship("A", ship_cells(2, 2, 2, False))])
    assert board.fire((0, 0)) == "miss"
    assert board.fire((0, 0)) is None and board.fire((-1, 3)) is None
    assert board.fire((2, 2)) == "hit"
    assert not board.defeated
    assert board.fire((3, 2)) == "sunk"
    assert board.defeated and board.sunk_ships()[0].name == "A"


def play_out(level: Level, seed: int) -> int:
    board = Board.random(random.Random(seed))
    admiral = Admiral(level, random.Random(seed + 1000))
    shots = 0
    while not board.defeated:
        cell = admiral.choose(board)
        assert board.fire(cell) is not None  # never repeats or leaves the board
        shots += 1
        assert shots <= SIZE * SIZE
    return shots


def test_every_level_finishes_and_harder_is_better() -> None:
    averages = {lv: statistics.mean(play_out(lv, s) for s in range(30)) for lv in LEVELS}
    assert averages["easy"] > averages["normal"] > averages["hard"]
    assert averages["easy"] > 85 and averages["hard"] < 60


def test_normal_follows_a_line_after_two_hits() -> None:
    board = Board([Ship("A", ship_cells(5, 3, 4, True))])
    board.fire((5, 4))
    board.fire((5, 5))
    for _ in range(10):
        r, c = Admiral("normal", random.Random()).choose(board)
        assert (r, c) in {(5, 3), (5, 6)}


def test_admiral_never_peeks_at_ships() -> None:
    """Same shots and sunk ships, different hidden layouts: the hard choice is identical."""
    a = Board([Ship("Carrier", ship_cells(0, 0, 5, True))])
    b = Board([Ship("Carrier", ship_cells(9, 5, 5, True))])
    for board in (a, b):
        board.shots = {(4, 4): "miss", (5, 5): "miss"}
    ca = Admiral("hard", random.Random(1)).choose(a)
    cb = Admiral("hard", random.Random(1)).choose(b)
    assert ca == cb


def test_app_placement_and_a_full_battle(app_context: AppContext) -> None:
    from apps.fleet_strike.app import OWN, FleetStrikeApp, cell_rect

    app = FleetStrikeApp(app_context)
    app.on_enter()
    app.own = Board([Ship("Carrier", ship_cells(0, 0, 5, True))])

    # Pick the carrier up by its first cell, rotate it, and drop it lower down.
    def mouse(kind: int, cell: tuple[int, int], button: int = 1) -> None:
        pos = cell_rect(OWN, cell).center
        app.handle_event(
            pygame.event.Event(pygame.MOUSEMOTION, pos=pos, rel=(0, 0), buttons=(0, 0, 0))
        )
        if kind:
            app.handle_event(pygame.event.Event(kind, pos=pos, button=button))

    mouse(pygame.MOUSEBUTTONDOWN, (0, 0))
    assert app.held is not None
    mouse(0, (3, 2))
    app.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_r, unicode="r", mod=0))
    mouse(pygame.MOUSEBUTTONDOWN, (3, 2))
    assert app.held is None and app.own.ships[0].cells == ship_cells(3, 2, 5, False)

    app.own = Board.random(random.Random(1))
    app.enemy = Board([Ship("Patrol boat", ship_cells(9, 8, 2, True))])
    app._start()
    assert app.phase == "battle"
    app._fire((0, 0))
    app._fire((0, 1))  # ignored: waiting for the computer
    assert app.shots == 1
    app.update(1.0)
    assert len(app.own.shots) == 1
    app._fire((9, 8))
    app.update(1.0)
    app._fire((9, 9))
    assert app.phase == "over" and app.menu is not None
    best = app.best_score(app.level)
    assert best is not None and best.score == 3
