"""Reaction Test rules: waits, false starts, targets and the app."""

from __future__ import annotations

import math
import random

import pygame

from apps.reaction_test.logic import (
    MAX_DELAY,
    MIN_DELAY,
    MIN_JUMP,
    ROUNDS,
    TARGET_R,
    TARGETS,
    ClassicTest,
    TargetRun,
)
from core.base_app import AppContext
from tests.conftest import feed, key, key_up


def test_classic_measures_from_the_signal() -> None:
    test = ClassicTest(random.Random(1))
    test.press(10.0)
    assert test.state == "waiting"
    assert MIN_DELAY <= test.go_at - 10.0 <= MAX_DELAY
    assert not test.tick(test.go_at - 0.01)
    assert test.tick(test.go_at) and test.state == "go"
    test.press(test.go_at + 0.234)
    assert test.state == "result" and math.isclose(test.last, 234)


def test_false_start_repeats_the_round() -> None:
    test = ClassicTest(random.Random(2))
    test.press(0.0)
    test.press(0.5)  # well before MIN_DELAY
    assert test.state == "early" and test.false_starts == 1 and not test.times
    test.press(1.0)
    assert test.state == "waiting"


def test_a_press_after_the_wait_counts_even_before_the_frame_shows_it() -> None:
    test = ClassicTest(random.Random(3))
    test.press(0.0)
    test.press(test.go_at + 0.180)  # no tick() in between
    assert test.false_starts == 0 and math.isclose(test.last, 180)


def test_classic_finishes_after_five_rounds() -> None:
    test = ClassicTest(random.Random(4))
    now = 0.0
    for i in range(ROUNDS):
        test.press(now)
        now = test.go_at + 0.2 + i * 0.01
        test.tick(test.go_at)
        test.press(now)
    assert test.state == "done" and len(test.times) == ROUNDS
    assert math.isclose(test.average, 220)


def test_targets_spawn_inside_and_apart() -> None:
    run = TargetRun(1000, 400, random.Random(5))
    run.start(0.0)
    last = run.target
    for i in range(TARGETS - 1):
        assert last is not None
        x, y = last
        assert TARGET_R <= x <= 1000 - TARGET_R and TARGET_R <= y <= 400 - TARGET_R
        assert run.click(x, y, i + 0.5)
        assert run.target is not None and math.dist(run.target, last) >= MIN_JUMP
        last = run.target


def test_target_hits_misses_and_finish() -> None:
    run = TargetRun(1000, 400, random.Random(6))
    run.start(1.0)
    assert run.target is not None
    x, y = run.target
    assert not run.click(x + TARGET_R + 1, y, 1.2)
    assert run.misses == 1 and not run.times
    now = 1.0
    for _ in range(TARGETS):
        assert run.target is not None
        now += 0.4
        run.click(*run.target, now)
    assert run.done and run.target is None
    assert math.isclose(run.average, 400)
    assert not run.click(0, 0, now + 1)


def test_app_classic_run_records_a_best(app_context: AppContext) -> None:
    from apps.reaction_test.app import ReactionTestApp

    app = ReactionTestApp(app_context)
    app.on_enter()
    now = [0.0]
    app.clock = lambda: now[0]
    for _ in range(ROUNDS):
        feed(app, key(pygame.K_SPACE, " "), key_up(pygame.K_SPACE))
        now[0] = app.classic.go_at
        app.update(0.016)
        assert app.classic.state == "go"
        now[0] += 0.190
        feed(app, key(pygame.K_SPACE, " "), key_up(pygame.K_SPACE))
    assert app.menu is not None
    best = app.best_score("classic")
    assert best is not None and best.score == 190


def test_pausing_during_a_wait_cancels_the_round(app_context: AppContext) -> None:
    from apps.reaction_test.app import ReactionTestApp

    app = ReactionTestApp(app_context)
    app.on_enter()
    app.clock = lambda: 0.0
    app.classic.press(0.0)
    app.on_pause()
    app.on_resume()
    assert app.classic.state == "idle" and app.classic.false_starts == 0
