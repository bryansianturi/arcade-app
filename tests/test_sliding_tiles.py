"""Sliding Tiles rules: solvability, sliding and the app."""

from __future__ import annotations

import random

import pytest

from apps.sliding_tiles.logic import GAP, SlidingPuzzle, is_solvable, solved_tiles
from core.base_app import AppContext


def test_solvability_parity() -> None:
    assert is_solvable(solved_tiles(4), 4) and is_solvable(solved_tiles(3), 3)
    swapped = solved_tiles(4)
    swapped[13], swapped[14] = swapped[14], swapped[13]  # the famous 14-15 swap
    assert not is_solvable(swapped, 4)
    swapped3 = solved_tiles(3)
    swapped3[0], swapped3[1] = swapped3[1], swapped3[0]
    assert not is_solvable(swapped3, 3)


@pytest.mark.parametrize("size", [3, 4])
def test_shuffles_are_solvable_permutations(size: int) -> None:
    rng = random.Random(size)
    for _ in range(20):
        p = SlidingPuzzle.shuffled(size, rng)
        assert sorted(p.tiles) == list(range(size * size))
        assert is_solvable(p.tiles, size) and not p.solved


def test_sliding_moves_and_multi_slides() -> None:
    p = SlidingPuzzle(4)
    assert p.gap == (3, 3)
    assert p.push((1, 0)) == [15]  # "right" moves the tile left of the gap to the right
    assert p.gap == (3, 2) and p.at(3, 3) == 15
    assert p.slide(3, 0) == [14, 13]  # two tiles slide at once
    assert p.gap == (3, 0) and p.moves == 2
    assert p.slide(1, 1) == []  # not in the gap's row or column
    assert p.push((-1, 0)) == [13]
    assert p.undo() and p.undo() and p.undo()
    assert p.solved and p.moves == 0


def test_random_moves_keep_a_permutation() -> None:
    p = SlidingPuzzle.shuffled(4, random.Random(3))
    rng = random.Random(4)
    for _ in range(500):
        p.push(rng.choice([(1, 0), (-1, 0), (0, 1), (0, -1)]))
    assert sorted(p.tiles) == list(range(16)) and p.tiles.count(GAP) == 1


def test_sliding_app_solves_and_records_time(app_context: AppContext) -> None:
    from apps.sliding_tiles.app import SlidingTilesApp

    app = SlidingTilesApp(app_context)
    app.on_enter()
    app.puzzle = SlidingPuzzle(app.size)
    app.puzzle.push((1, 0))  # one move away from solved
    app.elapsed = 33
    app._push((-1, 0))
    assert app.puzzle.solved and app.best_score("4x4") is not None
