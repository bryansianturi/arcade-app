"""Checkers rules: forced captures, multi-jumps, crowning, endings and the engine."""

from __future__ import annotations

import random

from apps.checkers.logic import DRAW_PLIES, Checkers, Move, choose_move, evaluate
from core.base_app import AppContext


def empty(turn: str = "dark") -> Checkers:
    return Checkers([["."] * 8 for _ in range(8)], turn)  # type: ignore[arg-type]


def put(game: Checkers, piece: str, *squares: tuple[int, int]) -> None:
    for r, c in squares:
        game.board[r][c] = piece


def test_opening_position() -> None:
    g = Checkers()
    assert len(g.pieces("dark")) == len(g.pieces("light")) == 12
    assert len(g.legal_moves()) == 7
    assert all(m.end[0] == 4 for m in g.legal_moves())  # dark moves up


def test_captures_are_compulsory() -> None:
    g = empty()
    put(g, "d", (5, 2), (5, 6))
    put(g, "l", (4, 3))
    moves = g.legal_moves()
    assert moves == [Move(((5, 2), (3, 4)), ((4, 3),))]
    assert g.must_capture()


def test_multi_jump_must_continue_and_choices_are_offered() -> None:
    g = empty()
    put(g, "d", (7, 0))
    put(g, "l", (6, 1), (4, 3), (4, 1))
    ends = {(m.end, len(m.captures)) for m in g.legal_moves()}
    # From (5, 2) the man can continue over (4, 3) or (4, 1): both are full sequences.
    assert ends == {((3, 4), 2), ((3, 0), 2)}
    g.play(next(m for m in g.legal_moves() if m.end == (3, 4)))
    assert g.piece((6, 1)) == g.piece((4, 3)) == "." and g.piece((3, 4)) == "d"
    assert g.turn == "light"


def test_men_only_capture_forwards_but_kings_go_both_ways() -> None:
    g = empty()
    put(g, "d", (3, 3))
    put(g, "l", (4, 4))  # behind the man
    assert not g.legal_moves()[0].captures
    put(g, "D", (3, 3))
    assert g.legal_moves() == [Move(((3, 3), (5, 5)), ((4, 4),))]


def test_crowning_ends_the_move() -> None:
    g = empty()
    put(g, "d", (2, 1))
    put(g, "l", (1, 2), (1, 4))  # after landing on (0, 3) a king could jump (1, 4)...
    [move] = g.legal_moves()
    assert move.end == (0, 3) and len(move.captures) == 1  # ...but crowning stops the move
    assert g.play(move) is True and g.piece((0, 3)) == "D"


def test_no_moves_loses() -> None:
    g = empty("light")
    put(g, "d", (5, 0))
    assert g.winner() == "dark"  # light has no pieces
    blocked = empty()
    put(blocked, "d", (7, 0))
    put(blocked, "l", (6, 1), (5, 2))
    assert blocked.winner() == "light"


def test_forty_move_draw() -> None:
    g = empty()
    put(g, "D", (7, 0))
    put(g, "L", (0, 7))
    put(g, "l", (0, 1))
    g.quiet_plies = DRAW_PLIES - 2
    g.play(Move(((7, 0), (6, 1))))  # king moves don't count as progress
    assert g.quiet_plies == DRAW_PLIES - 1 and not g.draw
    g.play(Move(((0, 1), (1, 2))))  # a man move resets the count
    assert g.quiet_plies == 0
    g.quiet_plies = DRAW_PLIES - 1
    g.play(Move(((6, 1), (5, 0))))
    assert g.draw and g.over


def test_undo() -> None:
    g = Checkers()
    before = [row[:] for row in g.board]
    g.play(g.legal_moves()[0])
    assert g.undo() and g.board == before and g.turn == "dark" and not g.undo()


def test_engine_takes_the_double_jump_and_avoids_hanging() -> None:
    g = empty()
    put(g, "d", (7, 0), (7, 6))
    put(g, "l", (6, 1), (4, 3), (0, 1))
    move = choose_move(g, 4, rng=random.Random(1))
    assert move is not None and len(move.captures) == 2
    # A dark man must not step next to a light man that would jump it for free.
    safe = empty()
    put(safe, "d", (5, 4))
    put(safe, "l", (2, 1), (3, 6))
    move = choose_move(safe, 4, rng=random.Random(1))
    assert move is not None and move.end != (4, 5)


def test_evaluation_is_symmetric() -> None:
    assert evaluate(Checkers()) == 0


def test_random_games_terminate_consistently() -> None:
    rng = random.Random(3)
    for _ in range(10):
        g = Checkers()
        for _ in range(400):
            if g.over:
                break
            g.play(rng.choice(g.legal_moves()))
            for side in ("dark", "light"):
                for r, c in g.pieces(side):
                    assert (r + c) % 2 == 1
        assert len(g.pieces("dark")) <= 12 and len(g.pieces("light")) <= 12


def test_app_click_through_a_jump(app_context: AppContext) -> None:
    from apps.checkers.app import CheckersApp

    app = CheckersApp(app_context)
    app.on_enter()
    app.vs_cpu = False
    app._new_game()
    g = app.game
    g.board = [["."] * 8 for _ in range(8)]
    put(g, "d", (7, 0))
    put(g, "l", (6, 1), (4, 3), (0, 7))
    app._click((7, 0))
    assert app.selected == (7, 0)
    app._click((5, 2))  # first hop: two sequences continue from here
    assert app.game.piece((7, 0)) == "d"
    app._click((3, 4))
    app.update(5)  # finish the animation
    assert g.piece((3, 4)) == "d" and g.turn == "light"
