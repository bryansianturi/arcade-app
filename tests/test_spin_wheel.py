from __future__ import annotations

import math
import random
from collections import Counter

import pygame
import pytest

from apps.spin_wheel.logic import MAX_OPTIONS, TAU, Wheel, clean_option, ease_out, slice_at
from core.base_app import AppContext
from tests.conftest import tap


def run_until_stopped(wheel: Wheel, dt: float = 1 / 60) -> int:
    frames = 0
    while not wheel.update(dt):
        frames += 1
        assert frames < 10_000
    return frames


def test_slice_under_pointer() -> None:
    w = TAU / 4
    assert slice_at(0.0, 4) == 0
    assert slice_at(-w * 1.5, 4) == 1  # turning anticlockwise brings later slices round
    assert slice_at(w * 0.5, 4) == 3  # a small clockwise turn shows the last slice
    assert slice_at(5 * TAU - w * 2.5, 4) == 2


@pytest.mark.parametrize("n", [2, 3, 7, 20])
def test_spin_stops_on_the_chosen_winner(n: int) -> None:
    rng = random.Random(n)
    wheel = Wheel([f"o{i}" for i in range(n)], angle=rng.uniform(0, TAU))
    for _ in range(30):
        winner = wheel.spin(rng, seconds=1.0)
        assert winner is not None and wheel.spinning
        before = wheel.angle
        run_until_stopped(wheel, dt=0.07)
        assert wheel.under_pointer() == winner == wheel.winner
        assert 0 <= wheel.angle < TAU and before != wheel.angle


def test_winners_are_uniform() -> None:
    rng = random.Random(1)
    wheel = Wheel(["a", "b", "c", "d"])
    counts: Counter[int] = Counter()
    for _ in range(4000):
        winner = wheel.spin(rng, seconds=0.01)
        assert winner is not None
        wheel.update(1)
        counts[winner] += 1
    assert all(abs(c - 1000) < 100 for c in counts.values())


def test_spin_turns_several_times_and_eases() -> None:
    wheel = Wheel(["a", "b"])
    wheel.spin(random.Random(2), seconds=2.0)
    total = wheel._to - wheel._from
    assert total >= 4 * TAU
    wheel.update(0.5)
    first_quarter = wheel.angle
    assert first_quarter > total * 0.5  # most of the turning happens early
    assert ease_out(0) == 0 and ease_out(1) == 1 and ease_out(2) == 1


def test_editing_rules() -> None:
    wheel = Wheel([])
    assert wheel.spin(random.Random()) is None  # needs two options
    assert not wheel.add("   ")
    assert wheel.add("  very   long " + "x" * 50)
    assert wheel.options[0] == clean_option("very long " + "x" * 50) and len(wheel.options[0]) == 30
    wheel.add("b")
    wheel.spin(random.Random(), seconds=1)
    assert not wheel.add("c") and not wheel.remove(0)  # no edits mid-spin
    run_until_stopped(wheel)
    assert wheel.remove(0) and wheel.winner is None
    wheel.options = [str(i) for i in range(MAX_OPTIONS)]
    assert not wheel.add("one too many")
    wheel.clear()
    assert wheel.options == [] and wheel.under_pointer() == -1


def test_app_remove_winner_mode(app_context: AppContext) -> None:
    from apps.spin_wheel.app import SpinWheelApp

    app = SpinWheelApp(app_context)
    app.on_enter()
    app.rng = random.Random(7)
    app.remove_toggle.toggle()
    tap(app, pygame.K_SPACE)
    assert app.wheel.spinning
    for _ in range(60 * 6):
        app.update(1 / 60)
    winner = app.wheel.options[app.wheel.winner or 0]
    assert app.showing_result and app.pending_removal is not None and app.confetti
    tap(app, pygame.K_SPACE)  # the winner leaves, then the next spin starts
    assert winner not in app.wheel.options and len(app.wheel.options) == 5
    app.on_exit()
    again = SpinWheelApp(app_context)
    again.on_enter()
    assert again.remove_winner and again.wheel.options == app.wheel.options


def test_app_typing_adds_options(app_context: AppContext) -> None:
    from apps.spin_wheel.app import SpinWheelApp

    app = SpinWheelApp(app_context)
    app.on_enter()
    for ch in "Ramen":
        app.handle_event(pygame.event.Event(pygame.TEXTINPUT, text=ch))
    assert app.uses_text_input()
    tap(app, pygame.K_RETURN)
    assert app.wheel.options[-1] == "Ramen"
    assert math.isclose(app.wheel.angle, 0)
