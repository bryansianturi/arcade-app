"""Klondike rules: dealing, legal moves, drawing, undo and auto-complete."""

from __future__ import annotations

import random

import pytest

from apps.solitaire.logic import (
    FOUNDATIONS,
    SUITS,
    TABLEAU,
    Card,
    Klondike,
    stacks_on_foundation,
    stacks_on_tableau,
)
from core.base_app import AppContext


def up(rank: int, suit: str) -> Card:
    return Card(rank, suit, True)  # type: ignore[arg-type]


def empty_game(draw: int = 1) -> Klondike:
    g = Klondike(random.Random(1), draw)  # type: ignore[arg-type]
    g.piles = {k: [] for k in g.piles}
    return g


def test_deal() -> None:
    g = Klondike(random.Random(4))
    assert [len(g.piles[t]) for t in TABLEAU] == [1, 2, 3, 4, 5, 6, 7]
    assert all(g.piles[t][-1].face_up for t in TABLEAU)
    assert not any(c.face_up for t in TABLEAU for c in g.piles[t][:-1])
    assert len(g.piles["stock"]) == 24 and not g.piles["waste"]
    cards = [(c.rank, c.suit) for p in g.piles.values() for c in p]
    assert len(set(cards)) == 52
    assert Klondike(random.Random(4)).piles == g.piles  # seeded deals repeat


def test_stacking_rules() -> None:
    assert stacks_on_tableau(up(12, "hearts"), up(13, "spades"))
    assert not stacks_on_tableau(up(12, "clubs"), up(13, "spades"))  # same colour
    assert not stacks_on_tableau(up(11, "hearts"), up(13, "spades"))  # gap
    assert stacks_on_tableau(up(13, "hearts"), None) and not stacks_on_tableau(
        up(12, "hearts"), None
    )
    assert not stacks_on_tableau(up(12, "hearts"), Card(13, "spades"))  # face down
    assert stacks_on_foundation(up(1, "clubs"), None)
    assert stacks_on_foundation(up(2, "clubs"), up(1, "clubs"))
    assert not stacks_on_foundation(up(2, "hearts"), up(1, "clubs"))


def test_moving_a_run_flips_the_new_top() -> None:
    g = empty_game()
    g.piles["t0"] = [Card(5, "clubs"), up(13, "spades"), up(12, "hearts"), up(11, "clubs")]
    assert not g.move("t0", 0, "t1")  # face-down cards don't move
    assert g.move("t0", 1, "t1")  # a king run into an empty column
    assert [c.rank for c in g.piles["t1"]] == [13, 12, 11]
    assert g.piles["t0"] == [up(5, "clubs")]
    assert g.moves == 1


def test_waste_and_foundation_move_one_card() -> None:
    g = empty_game()
    g.piles["waste"] = [up(1, "hearts"), up(1, "spades")]
    g.piles["t0"] = [up(2, "hearts")]
    assert not g.move("waste", 0, "f0")
    assert g.auto_move("waste") == "f0"
    assert g.top("f0") == up(1, "spades")
    assert not g.move("t0", 0, "f0")  # wrong suit
    g.piles["f1"] = [up(1, "hearts")]
    assert g.auto_move("t0") == "f1"
    assert g.move("f1", 1, "t2") is False  # a 2 can't start an empty column
    g.piles["t2"] = [up(3, "clubs")]
    assert g.move("f1", 1, "t2")  # cards can come back down from a foundation


@pytest.mark.parametrize("draw", [1, 3])
def test_drawing_and_recycling(draw: int) -> None:
    g = empty_game(draw)
    g.piles["stock"] = [Card(r, "clubs") for r in range(1, 6)]
    g.draw()
    assert len(g.piles["waste"]) == draw and all(c.face_up for c in g.piles["waste"])
    assert g.top("waste") == up(6 - draw, "clubs")  # the last card turned is on top
    while g.piles["stock"]:
        g.draw()
    order = list(g.piles["waste"])
    g.draw()  # recycle
    assert not g.piles["waste"] and len(g.piles["stock"]) == 5
    assert not any(c.face_up for c in g.piles["stock"])
    while g.piles["stock"]:
        g.draw()
    assert g.piles["waste"] == order  # same order on the next pass
    g.piles = {k: [] for k in g.piles}
    assert not g.draw()


def test_undo_restores_everything() -> None:
    g = Klondike(random.Random(2))
    before = {k: list(v) for k, v in g.piles.items()}
    g.draw()
    move = g.legal_moves()
    if move:
        g.move(*move[0])
    while g.undo():
        pass
    assert g.piles == before and g.moves == 0 and not g.can_undo


def test_autocomplete_finishes_a_solved_layout() -> None:
    g = empty_game()
    # Four face-up columns of one suit each, king at the bottom.
    for i, suit in enumerate(SUITS):
        g.piles[TABLEAU[i]] = [up(r, suit) for r in range(13, 0, -1)]
    assert g.can_autocomplete
    steps = 0
    while g.autocomplete_step() is not None:
        steps += 1
    assert steps == 52 and g.won and not g.can_autocomplete


def test_autocomplete_needs_everything_face_up() -> None:
    g = Klondike(random.Random(1))
    assert not g.can_autocomplete


def test_random_play_never_breaks_invariants() -> None:
    rng = random.Random(7)
    for seed in range(5):
        g = Klondike(random.Random(seed), rng.choice((1, 3)))
        for _ in range(300):
            moves = g.legal_moves()
            if moves and rng.random() < 0.7:
                assert g.move(*rng.choice(moves))
            else:
                g.draw()
            if rng.random() < 0.05:
                g.undo()
            total = sum(len(p) for p in g.piles.values())
            assert total == 52
            for f in FOUNDATIONS:
                cards = g.piles[f]
                assert [c.rank for c in cards] == list(range(1, len(cards) + 1))
                assert len({c.suit for c in cards}) <= 1


def test_app_drag_and_drop_and_keyboard(app_context: AppContext) -> None:
    import pygame

    from apps.solitaire.app import SolitaireApp
    from tests.conftest import feed, tap

    app = SolitaireApp(app_context)
    app.on_enter()
    g = app.game
    g.piles = {k: [] for k in g.piles}
    g.piles["t0"] = [up(13, "spades")]
    g.piles["t1"] = [up(12, "hearts")]
    g.piles["f0"] = []
    g.piles["waste"] = [up(1, "clubs")]
    app.update(0)
    start = app.card_rect("t1", 0).center
    drop = app.card_rect("t0", 0).center
    feed(
        app,
        pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=start, button=1),
        pygame.event.Event(pygame.MOUSEMOTION, pos=drop, rel=(0, 0), buttons=(1, 0, 0)),
        pygame.event.Event(pygame.MOUSEBUTTONUP, pos=drop, button=1),
    )
    assert [c.rank for c in g.piles["t0"]] == [13, 12]
    tap(app, pygame.K_u)  # undo
    assert [c.rank for c in g.piles["t0"]] == [13]
    # Double-click the waste ace: it goes home.
    ace = app.card_rect("waste", 0).center
    for _ in range(2):
        feed(
            app,
            pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=ace, button=1),
            pygame.event.Event(pygame.MOUSEBUTTONUP, pos=ace, button=1),
        )
    assert g.top("f0") == up(1, "clubs")
