"""Nonogram: clues, the line solver, bundled puzzles, the generator and the board."""

from __future__ import annotations

import random

import pytest

from apps.nonogram.logic import (
    CROSS,
    EMPTY,
    FILL,
    FILLED,
    UNKNOWN,
    Board,
    Puzzle,
    generate,
    is_logic_solvable,
    load_puzzles,
    runs,
    solve_line,
)
from core.base_app import AppContext

PUZZLES = load_puzzles()


def test_runs() -> None:
    assert runs([True, True, False, True]) == [2, 1]
    assert runs([False, False]) == [0]
    assert runs([True] * 5) == [5]


def test_line_solver_overlap_and_contradiction() -> None:
    # A run of 4 on 6 cells: the middle two must be filled.
    assert solve_line([4], (UNKNOWN,) * 6) == (UNKNOWN, UNKNOWN, FILLED, FILLED, UNKNOWN, UNKNOWN)
    assert solve_line([0], (UNKNOWN,) * 3) == (EMPTY,) * 3
    assert solve_line([1, 1], (UNKNOWN, UNKNOWN, UNKNOWN)) == (FILLED, EMPTY, FILLED)
    assert solve_line([3], (UNKNOWN, EMPTY, UNKNOWN)) is None
    known = (FILLED, UNKNOWN, UNKNOWN, UNKNOWN, UNKNOWN)
    assert solve_line([2], known) == (FILLED, FILLED, EMPTY, EMPTY, EMPTY)


def test_bundled_puzzles_are_unique_and_logic_solvable() -> None:
    assert len(PUZZLES) >= 6 and len({p.name for p in PUZZLES}) == len(PUZZLES)
    for puzzle in PUZZLES:
        assert is_logic_solvable(puzzle), puzzle.name


def test_an_ambiguous_puzzle_is_rejected() -> None:
    # Two diagonal cells: the clues allow both diagonals.
    assert not is_logic_solvable(Puzzle("x", ("#.", ".#")))


@pytest.mark.parametrize("size", [5, 10, 15])
def test_generator_makes_solvable_puzzles(size: int) -> None:
    puzzle = generate(size, random.Random(size))
    assert puzzle.width == puzzle.height == size and is_logic_solvable(puzzle)


def test_board_solving_ignores_crosses_and_undo() -> None:
    board = Board(Puzzle("t", ("#.", ".#")))
    board.checkpoint()
    board.set(0, 0, FILL)
    board.set(0, 1, CROSS)
    assert board.row_done(0) and not board.solved
    board.set(1, 1, FILL)
    assert board.solved
    assert board.undo() and board.marks == [[0, 0], [0, 0]]


def test_board_round_trips() -> None:
    puzzle = PUZZLES[0]
    board = Board(puzzle)
    board.set(2, 3, FILL)
    board.set(4, 4, CROSS)
    again = Board.from_json(puzzle, board.to_json())
    assert again.marks == board.marks
    assert Board.from_json(puzzle, ["junk"]).marks == Board(puzzle).marks


def test_app_paints_and_solves(app_context: AppContext) -> None:
    import pygame

    from apps.nonogram.app import NonogramApp

    app = NonogramApp(app_context)
    app.on_enter()
    app._random(5)
    puzzle = app.board.puzzle
    filled = [(r, c) for r in range(5) for c in range(5) if puzzle.filled(r, c)]
    (r0, c0) = filled[0]
    down = pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=app.cell_rect(r0, c0).center, button=1)
    app.handle_event(down)
    assert app.board.marks[r0][c0] == FILL
    for r, c in filled[1:]:
        app.board.set(r, c, FILL)
    r, c = filled[-1]
    app.board.set(r, c, 0)
    app.stroke = FILL
    app._paint(r, c)
    assert app.board.solved and app.solved_at is not None
