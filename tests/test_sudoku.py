from __future__ import annotations

import random

import pytest

from apps.sudoku.logic import (
    CLUES,
    DIFFICULTIES,
    PEERS,
    Difficulty,
    SudokuGame,
    conflicts,
    count_solutions,
    generate_puzzle,
    solve,
)
from core.base_app import AppContext

# A well-known puzzle and its solution.
PUZZLE = [
    int(c)
    for c in ("530070000600195000098000060800060003400803001700020006060000280000419005000080079")
]
SOLUTION = [
    int(c)
    for c in ("534678912672195348198342567859761423426853791713924856961537284287419635345286179")
]


def test_peers() -> None:
    assert all(len(p) == 20 for p in PEERS)
    assert 8 in PEERS[0] and 72 in PEERS[0] and 20 in PEERS[0] and 30 not in PEERS[0]


def test_solve_known_puzzle() -> None:
    assert solve(PUZZLE) == SOLUTION
    assert count_solutions(PUZZLE) == 1


def test_solve_does_not_mutate_input() -> None:
    board = PUZZLE.copy()
    solve(board)
    assert board == PUZZLE


def test_multiple_and_zero_solutions() -> None:
    assert count_solutions([0] * 81) == 2  # stops at the limit
    broken = PUZZLE.copy()
    broken[2] = 5  # duplicate 5 in the first row
    assert count_solutions(broken) == 0 and solve(broken) is None


def test_conflicts() -> None:
    board = [0] * 81
    board[0] = board[8] = 5  # same row
    board[40] = 7
    assert conflicts(board) == {0, 8}
    board[30] = 7  # same box as 40
    assert conflicts(board) == {0, 8, 30, 40}


@pytest.mark.parametrize("difficulty", DIFFICULTIES)
@pytest.mark.parametrize("seed", [1, 2, 3])
def test_generated_puzzles_are_unique_and_consistent(difficulty: Difficulty, seed: int) -> None:
    puzzle, solution = generate_puzzle(difficulty, random.Random(seed))
    assert count_solutions(puzzle) == 1
    assert solve(puzzle) == solution
    assert all(p in (0, s) for p, s in zip(puzzle, solution, strict=True))
    assert not conflicts(solution) and 0 not in solution
    clues = sum(1 for v in puzzle if v)
    assert CLUES[difficulty] - 1 <= clues <= CLUES[difficulty] + 2


def test_difficulties_are_ordered() -> None:
    rng = random.Random(7)
    counts = [sum(1 for v in generate_puzzle(d, rng)[0] if v) for d in DIFFICULTIES]
    assert counts[0] > counts[1] > counts[2]


def make_game() -> SudokuGame:
    return SudokuGame(PUZZLE.copy(), SOLUTION.copy(), "easy")


def test_givens_cannot_be_changed() -> None:
    game = make_game()
    game.select(0)  # given 5
    game.enter(9)
    game.erase()
    assert game.values[0] == 5


def test_enter_check_and_remaining() -> None:
    game = make_game()
    game.select(2)  # empty; solution is 4
    game.enter(9)
    assert game.wrong_cells() == {2}
    assert 2 in game.conflicts()  # 9 is already in that box
    game.enter(4)
    assert game.wrong_cells() == set()
    assert game.remaining(4) == 9 - sum(1 for v in game.values if v == 4)


def test_notes_and_peer_cleanup_with_undo() -> None:
    game = make_game()
    game.toggle_pencil()
    game.select(2)
    game.enter(1)
    game.enter(2)
    game.enter(1)  # toggles 1 off again
    assert game.note_digits(2) == [2]
    game.select(3)
    game.enter(2)
    game.toggle_pencil()
    game.select(5)
    game.enter(2)  # placing a 2 in row 0 removes the 2 notes from cells 2 and 3
    assert game.notes[2] == 0 and game.notes[3] == 0 and game.values[5] == 2
    assert game.undo()
    assert game.values[5] == 0 and game.note_digits(2) == [2] and game.note_digits(3) == [2]


def test_selection_wraps() -> None:
    game = make_game()
    game.select(0)
    game.move(-1, -1)
    assert game.selected == 80


def test_solving_completes_and_stops_timer() -> None:
    game = make_game()
    for i in range(81):
        if not game.is_given(i):
            game.select(i)
            game.enter(SOLUTION[i])
    assert game.solved
    game.tick(5)
    assert game.elapsed == 0
    assert not game.undo()  # board is locked once solved


def test_app_saves_and_restores_unfinished_game(app_context: AppContext) -> None:
    from apps.sudoku.app import SudokuApp

    app = SudokuApp(app_context)
    app.on_enter()
    assert app.mode == "choose" and app.dialog is not None
    app.dialog.buttons[0].activate()  # Easy
    assert app.mode == "playing" and app.game is not None
    first_empty = next(i for i in range(81) if not app.game.is_given(i))
    app.game.select(first_empty)
    app.game.enter(app.game.solution[first_empty])
    app.game.elapsed = 42
    app.on_exit()

    again = SudokuApp(app_context)
    again.on_enter()
    assert again.dialog is not None and again.dialog.buttons[0].text.startswith("Continue")
    again.dialog.buttons[0].activate()
    assert again.game is not None
    assert again.game.values[first_empty] == app.game.values[first_empty]
    assert again.game.elapsed == 42


def test_app_records_best_time(app_context: AppContext) -> None:
    from apps.sudoku.app import SudokuApp

    app = SudokuApp(app_context)
    app.on_enter()
    app._begin(SudokuGame(PUZZLE.copy(), SOLUTION.copy(), "hard"))
    assert app.game is not None
    app.game.elapsed = 125.4
    for i in range(81):
        if not app.game.is_given(i):
            app.game.select(i)
            app._enter(SOLUTION[i])
    assert app.mode == "solved" and app.new_best
    best = app.best_score("hard")
    assert best is not None and best.score == 125
