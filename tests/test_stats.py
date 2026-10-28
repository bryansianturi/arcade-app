"""Usage statistics: sessions, play time, persistence and formatting."""

from __future__ import annotations

from datetime import datetime, timedelta

import pygame

from core.canvas import Canvas
from core.services import Services
from core.stats import SAVE_EVERY, StatsService, format_ago, format_duration
from core.storage import Storage
from screens.stats import StatsScreen, build_rows
from tests.conftest import host_app, tap
from tests.test_framework import Exploding


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 5, 1, 12, 0, 0)

    def __call__(self) -> datetime:
        return self.now


def test_sessions_time_and_persistence(storage: Storage) -> None:
    clock = Clock()
    stats = StatsService(storage, clock)
    stats.start_session("snake")
    stats.add_time("snake", 12.5)
    clock.now += timedelta(minutes=5)
    stats.end_session("snake")
    stats.start_session("2048")
    stats.add_time("2048", 3)
    again = StatsService(storage)  # end_session/start_session saved everything
    assert again.get("snake").sessions == 1 and again.get("snake").seconds == 12.5
    assert again.get("snake").last_played == "2026-05-01T12:05:00"
    assert again.get("2048").seconds == 0  # time since the last save isn't flushed yet
    assert stats.total_seconds == 15.5 and stats.total_sessions == 2
    assert stats.most_played() == "snake"
    assert stats.recent(5) == ["snake", "2048"]
    assert stats.recent(5, known={"2048"}) == ["2048"]
    assert again.get("never").sessions == 0


def test_time_is_saved_periodically(storage: Storage) -> None:
    stats = StatsService(storage)
    stats.start_session("snake")
    for _ in range(int(SAVE_EVERY) + 1):
        stats.add_time("snake", 1.0)
    assert StatsService(storage).get("snake").seconds >= SAVE_EVERY


def test_corrupt_entries_are_ignored(storage: Storage) -> None:
    storage.save_json("stats.json", {"a": "x", "b": {"seconds": -4, "sessions": "2"}})
    stats = StatsService(storage)
    assert stats.get("a").seconds == 0 and stats.get("b").sessions == 0


def test_formatting() -> None:
    assert format_duration(42) == "42s"
    assert format_duration(754) == "12m"
    assert format_duration(5400) == "1h 30m"
    now = datetime(2026, 5, 10, 18, 0)
    assert format_ago("", now) == "never"
    assert format_ago("2026-05-10T17:59:30", now) == "just now"
    assert format_ago("2026-05-10T17:30:00", now) == "30 min ago"
    assert format_ago("2026-05-10T09:00:00", now) == "9 h ago"
    assert format_ago("2026-05-09T23:00:00", now) == "yesterday"
    assert format_ago("2026-05-01T10:00:00", now) == "9 days ago"
    assert format_ago("2026-01-01T10:00:00", now) == "Jan 01, 2026"
    assert format_ago("garbage", now) == "—"


def test_app_host_tracks_play_time_but_not_pauses(services: Services) -> None:
    host = host_app(services, Exploding)
    host.update(0.5)
    tap(host, pygame.K_ESCAPE)  # paused: time stops
    host.update(5.0)
    tap(host, pygame.K_ESCAPE)
    host.update(0.25)
    services.scenes.pop()
    entry = services.stats.get("exploding")
    assert entry.sessions == 1 and entry.seconds == 0.75 and entry.last_played


def test_stats_screen(services: Services) -> None:
    services.apps = [Exploding]
    canvas = Canvas.new(services.scenes.size)
    StatsScreen(services).draw(canvas)  # empty state
    services.stats.start_session("exploding")
    services.stats.add_time("exploding", 90)
    assert [r.app for r in build_rows(services)] == [Exploding]
    StatsScreen(services).draw(canvas)
