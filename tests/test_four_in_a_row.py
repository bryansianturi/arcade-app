from __future__ import annotations

import random
import time

import pytest

from apps.four_in_a_row.logic import (
    COLS,
    LEVELS,
    ROWS,
    WINDOWS,
    Board,
    FourInARow,
    Level,
    Player,
    choose_move,
)
from core.base_app import AppContext


def play(cols: list[int]) -> Board:
    """Drop discs alternately (player 1 first) into the given columns."""
    b = Board()
    for i, c in enumerate(cols):
        b.drop(c, 1 if i % 2 == 0 else 2)
    return b


def test_windows_count() -> None:
    assert len(WINDOWS) == 69  # 24 horizontal + 21 vertical + 12 + 12 diagonal


def test_gravity_and_full_columns() -> None:
    b = Board()
    assert [b.drop(3, 1) for _ in range(ROWS)] == list(range(ROWS))
    assert not b.can_drop(3)
    with pytest.raises(ValueError):
        b.drop(3, 2)
    assert 3 not in b.legal()


def test_undo_restores_state() -> None:
    b = play([3, 3, 4])
    b.undo(4)
    assert b.heights[4] == 0 and b.grid[0][4] == 0 and b.moves == 2


@pytest.mark.parametrize(
    ("moves", "expected"),
    [
        ([0, 6, 1, 6, 2, 6, 3], [(0, 0), (0, 1), (0, 2), (0, 3)]),  # horizontal
        ([0, 1, 0, 1, 0, 1, 0], [(0, 0), (1, 0), (2, 0), (3, 0)]),  # vertical
        ([0, 1, 1, 2, 2, 3, 2, 3, 3, 6, 3], [(0, 0), (1, 1), (2, 2), (3, 3)]),  # diagonal /
        ([6, 5, 5, 4, 4, 3, 4, 3, 3, 0, 3], [(0, 6), (1, 5), (2, 4), (3, 3)]),  # diagonal \\
    ],
)
def test_win_detection(moves: list[int], expected: list[tuple[int, int]]) -> None:
    g = FourInARow()
    for c in moves:
        g.drop(c)
    assert g.winner == 1 and g.win_cells == expected
    assert g.drop(5) is None  # no moves after the game ends


def test_draw_on_full_board() -> None:
    # Fill columns in an order that never makes four: pairs of columns stacked in a 2-2 pattern.
    g = FourInARow()
    order = [
        0,
        1,
        0,
        1,
        1,
        0,
        1,
        0,
        0,
        1,
        0,
        1,
        2,
        3,
        2,
        3,
        3,
        2,
        3,
        2,
        2,
        3,
        2,
        3,
        4,
        5,
        4,
        5,
        5,
        4,
        5,
        4,
        4,
        5,
        4,
        5,
        6,
        6,
        6,
        6,
        6,
        6,
    ]
    for c in order:
        assert g.drop(c) is not None
    assert g.winner is None and g.board.full() and g.over


@pytest.mark.parametrize("level", ["medium", "hard"])
def test_cpu_takes_a_win(level: Level) -> None:
    b = play([0, 6, 1, 6, 2, 5])  # player 1 threatens column 3
    assert choose_move(b, 1, level, random.Random(0)) == 3


@pytest.mark.parametrize("level", ["medium", "hard"])
def test_cpu_blocks_a_threat(level: Level) -> None:
    b = play([0, 6, 1, 6, 2])  # player 1 has three in a row; player 2 must block 3
    assert choose_move(b, 2, level, random.Random(0)) == 3


def test_hard_sees_a_two_way_trap() -> None:
    # Player 1 can play column 3 to create two threats (2 and 5) at once.
    b = play([2, 2, 4, 4])
    # bottom row: 1 at columns 2 and 4. Dropping 3 gives _ 1 1 1 _ with both ends open.
    assert choose_move(b, 1, "hard", random.Random(0)) == 3
    # And player 2 must prevent that setup.
    b = play([2, 6, 4])
    assert choose_move(b, 2, "hard", random.Random(0)) in (1, 3, 5)


@pytest.mark.parametrize("level", LEVELS)
def test_cpu_always_returns_a_legal_move_quickly(level: Level) -> None:
    rng = random.Random(4)
    b = Board()
    player: Player = 1
    worst = 0.0
    while not b.full():
        start = time.perf_counter()
        col = choose_move(b, player, level, rng)
        worst = max(worst, time.perf_counter() - start)
        assert b.can_drop(col)
        row = b.drop(col, player)
        if b.winning_cells(row, col):
            break
        player = 2 if player == 1 else 1
    assert worst < 2.0


def test_hard_beats_easy_most_of_the_time() -> None:
    rng = random.Random(9)
    hard_wins = 0
    for game in range(6):
        b = Board()
        levels: dict[int, Level] = {1: "hard", 2: "easy"} if game % 2 else {1: "easy", 2: "hard"}
        player: Player = 1
        while not b.full():
            col = choose_move(b, player, levels[player], rng)
            row = b.drop(col, player)
            if b.winning_cells(row, col):
                hard_wins += levels[player] == "hard"
                break
            player = 2 if player == 1 else 1
    assert hard_wins >= 5


def test_app_cpu_moves_in_background(app_context: AppContext) -> None:
    from apps.four_in_a_row.app import FourInARowApp

    app = FourInARowApp(app_context)
    app.on_enter()
    app._set_first(1)  # CPU starts
    deadline = time.monotonic() + 5
    while app.game.board.moves == 0 and time.monotonic() < deadline:
        app.update(1 / 30)
    assert app.game.board.moves == 1
    while app.busy:
        app.update(1 / 30)
    app._human_drop(0)
    assert app.game.board.moves == 2 and app.game.board.grid[0][0] == app.game.human


def test_app_records_tally(app_context: AppContext) -> None:
    from apps.four_in_a_row.app import FourInARowApp

    app = FourInARowApp(app_context)
    app.on_enter()
    app._set_level(0)
    for c in (0, 6, 1, 6, 2, 6):
        app.game.drop(c)
    app._human_drop(3)
    while app.busy:
        app.update(1 / 30)
    app.update(1 / 30)
    assert app.game.winner == 1 and app.tally() == [1, 0, 0]
    assert COLS == 7
