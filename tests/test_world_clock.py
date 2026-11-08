from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta, timezone

import pygame
import pytest

from apps.world_clock.logic import (
    CITIES,
    CITY_BY_NAME,
    City,
    Event,
    ago_text,
    city_time,
    countdown_parts,
    countdown_text,
    day_text,
    difference_text,
    has_dst_rules,
    make_event,
    parse_date,
    parse_time,
    search_cities,
    utc_offset_text,
    zone_of,
)
from core.base_app import AppContext
from tests.conftest import tap


def test_city_list_is_consistent() -> None:
    assert len({c.name for c in CITIES}) == len(CITIES)
    for city in CITIES:
        assert has_dst_rules(city), city.zone  # every zone exists in the database
        january = datetime(2026, 1, 15, 12, tzinfo=UTC)
        july = datetime(2026, 7, 15, 12, tzinfo=UTC)
        offsets = {city_time(city, d).utcoffset() for d in (january, july)}
        # The fallback offset is the zone's standard (non-summer) offset.
        assert timedelta(minutes=city.standard_offset) == min(offsets)  # type: ignore[type-var]


def test_daylight_saving_is_applied() -> None:
    london, sydney = CITY_BY_NAME["London"], CITY_BY_NAME["Sydney"]
    summer = datetime(2026, 7, 1, 12, tzinfo=UTC)
    winter = datetime(2026, 1, 1, 12, tzinfo=UTC)
    assert city_time(london, summer).hour == 13 and city_time(london, winter).hour == 12
    assert city_time(sydney, summer).hour == 22 and city_time(sydney, winter).hour == 23


def test_missing_zone_falls_back_to_standard_offset() -> None:
    fake = City("Nowhere", "Mars/Olympus_Mons", 330)
    assert not has_dst_rules(fake)
    assert zone_of(fake) == timezone(timedelta(minutes=330))
    assert city_time(fake, datetime(2026, 1, 1, tzinfo=UTC)).strftime("%H:%M") == "05:30"


def test_offset_difference_and_day_text() -> None:
    assert utc_offset_text(timedelta(hours=5, minutes=30)) == "UTC+5:30"
    assert utc_offset_text(timedelta(hours=-8)) == "UTC−8"
    assert utc_offset_text(None) == "UTC"
    now = datetime(2026, 1, 1, 23, 30, tzinfo=UTC)
    here = city_time(CITY_BY_NAME["London"], now)
    for name, diff, day in (
        ("Mumbai", "+5 h 30 m", "Tomorrow"),
        ("New York", "−5 h", "Today"),
        ("Honolulu", "−10 h", "Today"),
        ("Lisbon", "Same time", "Today"),
    ):
        there = city_time(CITY_BY_NAME[name], now)
        assert (difference_text(here, there), day_text(here, there)) == (diff, day)
    assert day_text(there, here) == "Today"


def test_search_ignores_case_and_accents() -> None:
    assert [c.name for c in search_cities("SAO")] == ["São Paulo"]
    assert [c.name for c in search_cities("bogota")] == ["Bogotá"]
    assert CITY_BY_NAME["Tokyo"] not in search_cities("", (CITY_BY_NAME["Tokyo"],))
    assert search_cities("zzz") == []


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2026-12-25", date(2026, 12, 25)),
        (" 2028-2-29 ", date(2028, 2, 29)),
        ("2026-02-29", None),
        ("25/12/2026", None),
        ("", None),
    ],
)
def test_parse_date(text: str, expected: date | None) -> None:
    assert parse_date(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("", time(0)),
        ("9", time(9)),
        ("09:30", time(9, 30)),
        ("24:00", None),
        ("9:5", None),
        ("noon", None),
    ],
)
def test_parse_time(text: str, expected: time | None) -> None:
    assert parse_time(text) == expected


def test_make_event_validates() -> None:
    zone = timezone(timedelta(hours=11))
    event = make_event("  Launch   day ", "2026-12-01", "18:30", zone)
    assert isinstance(event, Event)
    assert event.name == "Launch day" and event.at == datetime(2026, 12, 1, 7, 30, tzinfo=UTC)
    assert make_event("", "2026-12-01", "", zone) == "Give the event a name."
    assert make_event("x", "2026-02-30", "", zone) == "There's no such date."
    assert make_event("x", "tomorrow", "", zone) == "Enter the date as YYYY-MM-DD."
    assert make_event("x", "2026-12-01", "7pm", zone) == "Enter the time as HH:MM (24-hour)."


def test_event_round_trip_and_bad_data() -> None:
    event = Event("Trip", datetime(2026, 12, 20, 7, 45, tzinfo=timezone(timedelta(hours=9))))
    again = Event.from_dict(event.to_dict())
    assert again is not None and again.at == event.at and again.name == "Trip"
    assert Event.from_dict({"name": "x", "at": "2026-12-20T07:45"}) is None  # no zone
    assert Event.from_dict({"name": " ", "at": "2026-12-20T07:45+00:00"}) is None
    assert Event.from_dict({"name": "x", "at": "soon"}) is None


def test_countdown_formatting() -> None:
    assert countdown_parts(90061.9) == (1, 1, 1, 1)
    assert countdown_text(90061) == "1d 01:01:01"
    assert countdown_text(59) == "00:00:59"
    assert countdown_text(0) == "Now"
    assert ago_text(3 * 86400 + 5) == "3 days ago"
    assert ago_text(3600) == "1 hour ago"
    assert ago_text(30) == "just now"


def test_app_adds_and_removes_cities_and_events(
    app_context: AppContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    from apps.world_clock.app import WorldClockApp

    fixed = datetime(2026, 11, 8, 12, tzinfo=UTC)
    monkeypatch.setattr(WorldClockApp, "now", staticmethod(lambda: fixed))
    app = WorldClockApp(app_context)
    app.on_enter()
    assert [c.name for c in app.cities] == ["London", "New York", "Tokyo", "Sydney"]
    tap(app, pygame.K_SPACE)  # open the picker
    assert app.picking and app.captures_pause()
    for ch in "dub":
        app.handle_event(pygame.event.Event(pygame.TEXTINPUT, text=ch))
    tap(app, pygame.K_RETURN)
    assert not app.picking and app.cities[-1].name == "Dubai"
    tap(app, pygame.K_SPACE)
    tap(app, pygame.K_ESCAPE)
    assert not app.picking and len(app.cities) == 5

    tap(app, pygame.K_RIGHT)  # countdowns
    app.name_input.set_text("Holiday")
    app.date_input.set_text("2026-12-24")
    app.name_input.focus()
    tap(app, pygame.K_RETURN)
    assert [e.name for e in app.events] == ["Holiday"]
    app.on_exit()
    again = WorldClockApp(app_context)
    again.on_enter()
    assert [c.name for c in again.cities][-1] == "Dubai" and again.events == app.events
