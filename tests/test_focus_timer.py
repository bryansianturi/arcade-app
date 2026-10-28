from __future__ import annotations

import pytest

from apps.focus_timer.logic import MAX_MINUTES, Clock, Pomodoro, Stopwatch
from core.base_app import AppContext


def test_clock_accumulates_across_starts() -> None:
    c = Clock()
    c.start(100)
    assert c.elapsed(103) == 3
    c.stop(103)
    assert c.elapsed(500) == 3 and not c.running
    c.start(600)
    c.start(650)  # starting twice doesn't reset the start time
    assert c.elapsed(610) == 13


def test_stopwatch_laps() -> None:
    sw = Stopwatch()
    sw.lap(5)  # not running: ignored
    sw.toggle(0)
    sw.lap(10)
    sw.lap(25)
    sw.lap(31)
    assert sw.lap_times() == [10, 15, 6]
    sw.toggle(40)
    assert sw.clock.elapsed(99) == 40
    sw.reset()
    assert sw.laps == [] and sw.clock.elapsed(99) == 0


def test_pomodoro_cycle_with_long_break_every_fourth() -> None:
    p = Pomodoro(minutes={"focus": 1, "short": 1, "long": 2})
    now = 0.0
    phases = []
    for _ in range(8):
        p.toggle(now)  # start the current phase
        now += p.duration() + 0.01
        assert p.update(now)
        phases.append(p.just_finished)
        assert not p.clock.running  # waits for the user to start the next phase
    assert phases == ["focus", "short", "focus", "short", "focus", "short", "focus", "long"]
    assert p.completed == 4 and p.phase == "focus"


def test_pomodoro_pause_and_remaining() -> None:
    p = Pomodoro()
    p.toggle(0)
    p.toggle(60)  # pause after a minute
    assert p.remaining(10_000) == 24 * 60
    assert not p.update(10_000)
    assert 0 < p.progress(10_000) < 0.1


def test_pomodoro_skip_and_reset() -> None:
    p = Pomodoro()
    p.toggle(0)
    p.reset()
    assert p.remaining(50) == p.duration()
    p.skip()
    assert p.phase == "short" and p.completed == 0
    p.skip()
    assert p.phase == "focus"
    p.completed = 3
    p.skip()
    assert p.phase == "long"  # the skipped session would have been the 4th


def test_pomodoro_adjust_limits_and_running_lock() -> None:
    p = Pomodoro()
    for _ in range(200):
        p.adjust("short", 1)
    assert p.minutes["short"] == MAX_MINUTES
    p.toggle(0)
    p.adjust("focus", 5)
    assert p.minutes["focus"] == 25  # can't change the phase that's running


def test_pomodoro_round_trip_and_bad_data() -> None:
    p = Pomodoro(minutes={"focus": 30, "short": 7, "long": 20}, completed=2)
    p.toggle(1234.5)
    again = Pomodoro.from_dict(p.to_dict())
    assert again.minutes == p.minutes and again.completed == 2 and again.clock.started_at == 1234.5
    assert Pomodoro.from_dict({"minutes": {"focus": 999}, "phase": "nap"}) == Pomodoro()


def test_app_keeps_running_while_away(
    app_context: AppContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    from apps.focus_timer.app import FocusTimerApp

    clock = [1000.0]
    monkeypatch.setattr(FocusTimerApp, "now", staticmethod(lambda: clock[0]))
    app = FocusTimerApp(app_context)
    app.on_enter()
    app._toggle()  # start focus
    app.on_exit()  # leave the app...
    clock[0] += 26 * 60  # ...and come back after the session ended
    again = FocusTimerApp(app_context)
    again.on_enter()
    assert again.pomodoro.just_finished == "focus" and again.pomodoro.phase == "short"
    assert again.pomodoro.completed == 1
