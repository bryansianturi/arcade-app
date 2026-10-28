from __future__ import annotations

import random
from typing import cast

import pytest

from apps.tictactoe.logic import (
    EMPTY,
    Board,
    Mark,
    TicTacToe,
    best_move,
    easy_move,
    legal_moves,
    other,
    play,
    winner,
    winning_line,
)
from core.base_app import AppContext


def board(text: str) -> Board:
    """Build a board from 9 chars: X, O or '.'."""
    cells = ["" if ch == "." else ch for ch in text.replace(" ", "")]
    return cast(Board, tuple(cells))


def test_winner_detection() -> None:
    assert winner(board("XXX ... ...")) == "X"
    assert winner(board("O.. O.. O..")) == "O"
    assert winning_line(board("X.O .XO ..X")) == (0, 4, 8)
    assert winner(board("XOX XOO OXX")) == "draw"
    assert winner(board("XO. ... ...")) is None


def test_play_rejects_taken_cells() -> None:
    with pytest.raises(ValueError):
        play(board("X.. ... ..."), 0, "O")


def test_best_move_takes_the_win() -> None:
    assert best_move(board("OO. XX. X.."), "O") == 2


def test_best_move_blocks() -> None:
    assert best_move(board("XX. .O. ..."), "O") == 2


def test_best_move_prefers_the_fastest_win() -> None:
    # O can win now at 2 or set up a later win; it must win immediately.
    b = board("OO. X.. X.X")
    assert best_move(b, "O") == 2


def _never_loses(b: Board, turn: Mark, cpu: Mark) -> bool:
    result = winner(b)
    if result is not None:
        return result != other(cpu)
    if turn == cpu:
        return _never_loses(play(b, best_move(b, cpu, random.Random(0)), cpu), other(turn), cpu)
    return all(_never_loses(play(b, m, turn), other(turn), cpu) for m in legal_moves(b))


@pytest.mark.parametrize("cpu", ["X", "O"])
def test_unbeatable_never_loses_against_any_strategy(cpu: Mark) -> None:
    """Exhaustively tries every possible human move sequence."""
    assert _never_loses(EMPTY, "X", cpu)


def test_easy_mode_is_beatable() -> None:
    rng = random.Random(1)
    human_wins = 0
    for _ in range(200):
        b = EMPTY
        turn: Mark = "X"
        while winner(b) is None:
            move = rng.choice(legal_moves(b)) if turn == "X" else easy_move(b, "O", rng)
            b = play(b, move, turn)
            turn = other(turn)
        human_wins += winner(b) == "X"
    assert human_wins > 20  # a random human still beats the easy CPU fairly often


def test_game_turn_order() -> None:
    g = TicTacToe(human="O", level="unbeatable", rng=random.Random(0))
    assert g.cpu_to_move
    assert not g.human_move(0)  # not the human's turn yet
    g.cpu_move()
    assert g.turn == "O" and not g.cpu_to_move
    free = legal_moves(g.board)[0]
    assert g.human_move(free)
    assert not g.human_move(free)  # cell now taken


def test_app_tracks_results_per_level(app_context: AppContext) -> None:
    from apps.tictactoe.app import TicTacToeApp

    app = TicTacToeApp(app_context)
    app.on_enter()
    app._set_level(0)  # easy, human (X) starts
    app.game.board = board("XX. OO. ...")
    app._play(2)
    assert app.game.result == "X" and app.tally() == [1, 0, 0]
    app._set_level(1)
    assert app.tally() == [0, 0, 0]  # separate record for the unbeatable CPU
    assert app_context.storage.app_data("tictactoe")["level"] == "unbeatable"


def test_app_cpu_moves_after_delay(app_context: AppContext) -> None:
    from apps.tictactoe.app import CPU_DELAY, TicTacToeApp

    app = TicTacToeApp(app_context)
    app.on_enter()
    app._set_first(1)  # CPU starts
    app.update(CPU_DELAY / 2)
    assert app.game.board == EMPTY
    app.update(CPU_DELAY)
    assert sum(1 for c in app.game.board if c) == 1
