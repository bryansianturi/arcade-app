from __future__ import annotations

import random
from collections import Counter

import pytest

from apps.memory_match.logic import LAYOUTS, SIZES, MemoryGame, Size
from core.base_app import AppContext


def pair_of(g: MemoryGame, index: int) -> int:
    return next(i for i, s in enumerate(g.cards) if s == g.cards[index] and i != index)


def non_pair_of(g: MemoryGame, index: int) -> int:
    return next(i for i, s in enumerate(g.cards) if s != g.cards[index])


@pytest.mark.parametrize("size", SIZES)
def test_every_symbol_appears_exactly_twice(size: Size) -> None:
    g = MemoryGame.for_size(size, random.Random(1))
    cols, rows = LAYOUTS[size]
    assert len(g.cards) == cols * rows
    assert set(Counter(g.cards).values()) == {2}


def test_odd_boards_are_rejected() -> None:
    with pytest.raises(ValueError):
        MemoryGame(3, 3)


def test_match_and_mismatch() -> None:
    g = MemoryGame.for_size("easy", random.Random(2))
    assert g.flip(0) == "first"
    assert g.flip(0) == "ignored"  # already face up
    assert g.flip(pair_of(g, 0)) == "match" and g.moves == 1
    assert {0, pair_of(g, 0)} <= g.matched and not g.open

    other = next(i for i in range(len(g.cards)) if i not in g.matched)
    wrong = next(
        i for i in range(len(g.cards)) if i not in g.matched and g.cards[i] != g.cards[other]
    )
    g.flip(other)
    assert g.flip(wrong) == "mismatch" and g.moves == 2 and len(g.open) == 2
    g.hide_mismatch()
    assert not g.open


def test_third_flip_hides_a_mismatch() -> None:
    g = MemoryGame.for_size("easy", random.Random(3))
    g.flip(0)
    g.flip(non_pair_of(g, 0))
    third = next(i for i in range(len(g.cards)) if not g.face_up(i))
    assert g.flip(third) == "first" and g.open == [third]


def test_win_and_timer() -> None:
    g = MemoryGame.for_size("easy", random.Random(4))
    g.tick(5)
    assert g.elapsed == 0  # timer waits for the first flip
    done: set[int] = set()
    for i in range(len(g.cards)):
        if i in done:
            continue
        j = pair_of(g, i)
        g.flip(i)
        g.tick(1)
        g.flip(j)
        done |= {i, j}
    assert g.won and g.pairs_left == 0 and g.moves == len(g.cards) // 2
    elapsed = g.elapsed
    g.tick(10)
    assert g.elapsed == elapsed
    assert g.flip(0) == "ignored"


def test_app_records_best_time(app_context: AppContext) -> None:
    from apps.memory_match.app import MemoryMatchApp

    app = MemoryMatchApp(app_context)
    app.on_enter()
    app._set_size(0)
    g = app.game
    done: set[int] = set()
    for i in range(len(g.cards)):
        if i not in done:
            j = pair_of(g, i)
            app._flip(i)
            app.update(2)
            app._flip(j)
            done |= {i, j}
    assert g.won and app.new_best
    best = app.best_score("easy")
    assert best is not None and best.score == round(g.elapsed)
