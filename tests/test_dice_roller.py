from __future__ import annotations

import random
from collections import Counter

import pygame
import pytest

from apps.dice_roller.logic import (
    MAX_DICE,
    MAX_MODIFIER,
    CoinStats,
    Pool,
    Roll,
    flip,
    parse_notation,
    roll,
)
from core.base_app import AppContext
from tests.conftest import tap


def test_pool_limits_and_notation() -> None:
    pool = Pool()
    assert pool.notation() == ""
    assert pool.add(20) and pool.add(6, 2)
    assert pool.notation() == "2d6 + 1d20"
    pool.set_modifier(-3)
    assert pool.notation() == "2d6 + 1d20 - 3"
    pool.set_modifier(500)
    assert pool.modifier == MAX_MODIFIER
    assert not pool.add(6, MAX_DICE)  # would go over the cap
    assert not pool.add(1) and not pool.add(101)
    assert pool.remove(20) and not pool.remove(20)
    assert pool.dice() == [6, 6]


def test_bounds_and_average() -> None:
    pool = Pool({6: 2, 20: 1}, modifier=2)
    assert pool.bounds() == (5, 34)
    assert pool.average() == 3.5 * 2 + 10.5 + 2


@pytest.mark.parametrize(
    ("text", "counts", "modifier"),
    [
        ("3d6+2", {6: 3}, 2),
        ("d20 + d4 - 1", {20: 1, 4: 1}, -1),
        ("2D8+1d6+3-5", {8: 2, 6: 1}, -2),
        ("  1d100 ", {100: 1}, 0),
        ("-1 + 2d6", {6: 2}, -1),
    ],
)
def test_parse_notation(text: str, counts: dict[int, int], modifier: int) -> None:
    pool = parse_notation(text)
    assert pool is not None and pool.counts == counts and pool.modifier == modifier


@pytest.mark.parametrize(
    "text", ["", "5", "d", "3d", "2d6 3", "2d6 - 1d4", "13d6", "d1", "1d6 + 200", "2d6+x"]
)
def test_parse_notation_rejects(text: str) -> None:
    assert parse_notation(text) is None


def test_rolls_stay_in_range_and_cover_every_face() -> None:
    rng = random.Random(5)
    pool = Pool({4: 1, 20: 1}, modifier=1)
    seen: dict[int, set[int]] = {4: set(), 20: set()}
    for _ in range(2000):
        r = roll(pool, rng)
        assert r.notation == "1d4 + 1d20 + 1"
        for sides, value in r.dice:
            seen[sides].add(value)
        assert r.total == sum(v for _, v in r.dice) + 1
    assert seen == {4: set(range(1, 5)), 20: set(range(1, 21))}


def test_roll_and_pool_round_trip() -> None:
    r = roll(Pool({6: 2}, 3), random.Random(1))
    assert Roll.from_dict(r.to_dict()) == r
    assert Roll.from_dict({"dice": [[6, 7]], "modifier": 0, "notation": "1d6"}) is None
    assert Roll.from_dict("junk") is None
    pool = Pool({8: 3}, -2)
    assert Pool.from_dict(pool.to_dict()) == pool
    assert Pool.from_dict({"counts": {"6": 50, "x": 1}, "modifier": "a"}) == Pool()


def test_coin_is_fair_and_streaks() -> None:
    rng = random.Random(9)
    counts = Counter(flip(rng) for _ in range(10_000))
    assert abs(counts["heads"] - 5000) < 200
    stats = CoinStats()
    for side in ("heads", "heads", "tails", "tails", "tails", "heads"):
        stats.record(side)
    assert (stats.heads, stats.tails, stats.total) == (3, 3, 6)
    assert stats.streak == 1 and stats.streak_side == "heads" and stats.best_streak == 3
    assert stats.share("heads") == 0.5 and CoinStats().share("tails") == 0
    for _ in range(40):
        stats.record("tails")
    assert len(stats.recent) == CoinStats.RECENT


def test_app_builds_rolls_and_flips(app_context: AppContext) -> None:
    from apps.dice_roller.app import DiceRollerApp

    app = DiceRollerApp(app_context)
    app.on_enter()
    tap(app, pygame.K_BACKSPACE)
    assert app.pool.size == 0
    tap(app, pygame.K_6)  # d20
    tap(app, pygame.K_2)  # d6
    tap(app, pygame.K_UP)
    assert app.pool.notation() == "1d6 + 1d20 + 1"
    tap(app, pygame.K_SPACE)
    assert app.last is not None and len(app.history) == 1
    app.notation_input.focus()
    app.notation_input.set_text("4d4")
    tap(app, pygame.K_RETURN)
    assert app.pool.counts == {4: 4} and app.last.notation == "4d4"

    tap(app, pygame.K_RIGHT)  # coin tab
    tap(app, pygame.K_SPACE)
    for _ in range(90):
        app.update(1 / 60)
    assert app.coins.total == 1
    app.on_exit()
    again = DiceRollerApp(app_context)
    again.on_enter()
    assert again.tab == 1 and again.pool.counts == {4: 4} and len(again.history) == 2
