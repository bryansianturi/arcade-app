"""Updraft rules: generation is always climbable, bounces, platform kinds, and a bot run."""

from __future__ import annotations

import itertools
import random

from apps.updraft.logic import (
    FIELD_W,
    GRAVITY,
    JUMP_V,
    MAX_GAP,
    MAX_JUMP,
    SPRING_V,
    Platform,
    Updraft,
)
from core.base_app import AppContext


def test_gaps_never_exceed_a_jump() -> None:
    for seed in range(5):
        game = Updraft(random.Random(seed))
        for camera in range(0, 40000, 400):  # pretend the player climbs
            game.camera = float(camera)
            game._generate()
        ys = sorted(p.y for p in game.platforms)
        assert ys[-1] > 40000
        assert max(b - a for a, b in itertools.pairwise(ys)) <= MAX_GAP < MAX_JUMP
        assert all(p.x >= 0 and p.x + p.w <= FIELD_W for p in game.platforms)


def falling_onto(game: Updraft, platform: Platform) -> None:
    game.platforms = [platform]
    game.state = "playing"
    game.x = platform.x + platform.w / 2
    game.y = platform.y + 30
    game.vy = -300


def test_landing_while_falling_bounces_and_rising_passes_through() -> None:
    game = Updraft(random.Random(1))
    falling_onto(game, Platform(100, 500, 100))
    game.camera = 300
    assert game.update(0.1, 0)
    assert game.vy > 0 and game.since_bounce < 0.1
    rising = Updraft(random.Random(1))
    falling_onto(rising, Platform(100, 500, 100))
    rising.camera = 300
    rising.y, rising.vy = 480, JUMP_V
    assert not rising.update(0.05, 0) and rising.y > 500


def test_crumble_breaks_and_spring_launches() -> None:
    game = Updraft(random.Random(2))
    crumble = Platform(100, 500, 100, "crumble")
    falling_onto(game, crumble)
    game.camera = 300
    game.update(0.1, 0)
    assert crumble.broken
    spring = Updraft(random.Random(2))
    falling_onto(spring, Platform(100, 500, 100, "spring"))
    spring.camera = 300
    spring.update(0.1, 0)
    assert spring.springs_used == 1 and spring.vy > JUMP_V
    assert SPRING_V > JUMP_V


def test_sides_wrap_and_falling_off_ends_the_run() -> None:
    game = Updraft(random.Random(3))
    game.start()
    game.x = FIELD_W - 2
    game.update(0.2, 1.0)
    assert 0 <= game.x < 100
    game.platforms = []
    for _ in range(100):
        game.update(0.05, 0)
    assert game.state == "over"


def wrapped_offset(a: float, b: float) -> float:
    """Shortest signed horizontal distance from ``a`` to ``b`` on the wrapping field."""
    return (b - a + FIELD_W / 2) % FIELD_W - FIELD_W / 2


def test_a_simple_bot_can_climb() -> None:
    """A greedy bot climbs every seed: evidence the generated tower is playable."""
    for seed in range(4):
        game = Updraft(random.Random(seed))
        game.start()
        for _ in range(60 * 120):
            game.update(1 / 60, steer(game))
            if game.state == "over" or game.score >= 500:
                break
        assert game.score >= 500, f"seed {seed} fell at {game.score}"


def steer(game: Updraft) -> float:
    """Aim for the highest platform at or below the current arc's peak."""
    apex = game.y + max(game.vy, 0.0) ** 2 / (2 * GRAVITY)
    ceiling = apex if game.vy > 0 else game.y
    reachable = [p for p in game.platforms if not p.broken and p.y <= ceiling - 4]
    if not reachable:
        return 0.0
    target = max(reachable, key=lambda p: p.y)
    dx = wrapped_offset(game.x, target.x + target.w / 2)
    return max(-1.0, min(1.0, dx / 30))


def test_app_runs_and_records_height(app_context: AppContext) -> None:
    from apps.updraft.app import UpdraftApp

    app = UpdraftApp(app_context)
    app.on_enter()
    app.game.start()
    app.game.best_height = 1234
    app.game.platforms = []
    for _ in range(200):
        app.update(0.05)
    assert app.menu is not None
    best = app.best_score()
    assert best is not None and best.score == 123
