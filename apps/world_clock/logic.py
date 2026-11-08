"""Time zones, clock formatting and countdowns. No pygame.

Zones come from the standard ``zoneinfo`` module (the OS's time zone database,
or the ``tzdata`` package where there is none). If a zone still can't be
loaded, a city falls back to its standard UTC offset, without daylight saving,
and :func:`has_dst_rules` says so.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta, timezone, tzinfo
from functools import cache
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


@dataclass(frozen=True)
class City:
    name: str
    zone: str  # IANA id, e.g. "Europe/London"
    standard_offset: int  # minutes east of UTC outside daylight saving (the fallback)


CITIES: tuple[City, ...] = (
    City("Honolulu", "Pacific/Honolulu", -600),
    City("Anchorage", "America/Anchorage", -540),
    City("Los Angeles", "America/Los_Angeles", -480),
    City("Denver", "America/Denver", -420),
    City("Chicago", "America/Chicago", -360),
    City("Mexico City", "America/Mexico_City", -360),
    City("New York", "America/New_York", -300),
    City("Toronto", "America/Toronto", -300),
    City("Bogotá", "America/Bogota", -300),
    City("Santiago", "America/Santiago", -240),
    City("São Paulo", "America/Sao_Paulo", -180),
    City("Buenos Aires", "America/Argentina/Buenos_Aires", -180),
    City("Reykjavík", "Atlantic/Reykjavik", 0),
    City("London", "Europe/London", 0),
    City("Lisbon", "Europe/Lisbon", 0),
    City("Lagos", "Africa/Lagos", 60),
    City("Paris", "Europe/Paris", 60),
    City("Berlin", "Europe/Berlin", 60),
    City("Rome", "Europe/Rome", 60),
    City("Cairo", "Africa/Cairo", 120),
    City("Johannesburg", "Africa/Johannesburg", 120),
    City("Athens", "Europe/Athens", 120),
    City("Istanbul", "Europe/Istanbul", 180),
    City("Moscow", "Europe/Moscow", 180),
    City("Nairobi", "Africa/Nairobi", 180),
    City("Dubai", "Asia/Dubai", 240),
    City("Karachi", "Asia/Karachi", 300),
    City("Mumbai", "Asia/Kolkata", 330),
    City("Kathmandu", "Asia/Kathmandu", 345),
    City("Dhaka", "Asia/Dhaka", 360),
    City("Bangkok", "Asia/Bangkok", 420),
    City("Jakarta", "Asia/Jakarta", 420),
    City("Singapore", "Asia/Singapore", 480),
    City("Hong Kong", "Asia/Hong_Kong", 480),
    City("Shanghai", "Asia/Shanghai", 480),
    City("Perth", "Australia/Perth", 480),
    City("Seoul", "Asia/Seoul", 540),
    City("Tokyo", "Asia/Tokyo", 540),
    City("Adelaide", "Australia/Adelaide", 570),
    City("Brisbane", "Australia/Brisbane", 600),
    City("Sydney", "Australia/Sydney", 600),
    City("Melbourne", "Australia/Melbourne", 600),
    City("Auckland", "Pacific/Auckland", 720),
)
CITY_BY_NAME = {c.name: c for c in CITIES}
DEFAULT_CITIES = ("London", "New York", "Tokyo", "Sydney")
MAX_CITIES = 6
MAX_EVENTS = 8
MAX_EVENT_NAME = 32


def fold(text: str) -> str:
    """Lowercase without accents, so "sao" finds "São Paulo"."""
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def search_cities(query: str, exclude: tuple[City, ...] = ()) -> list[City]:
    """Cities whose name contains ``query`` (accent- and case-insensitive)."""
    needle = fold(query.strip())
    return [c for c in CITIES if c not in exclude and needle in fold(c.name)]


@cache
def _load_zone(zone: str) -> tzinfo | None:
    try:
        return ZoneInfo(zone)
    except (ZoneInfoNotFoundError, ValueError, OSError):
        return None


def has_dst_rules(city: City) -> bool:
    """Whether the real time zone (with daylight saving) is available."""
    return _load_zone(city.zone) is not None


def zone_of(city: City) -> tzinfo:
    return _load_zone(city.zone) or timezone(timedelta(minutes=city.standard_offset))


def city_time(city: City, now: datetime) -> datetime:
    """``now`` (timezone-aware) as wall time in ``city``."""
    return now.astimezone(zone_of(city))


def utc_offset_text(offset: timedelta | None) -> str:
    """``"UTC+5:30"``, ``"UTC−8"`` or ``"UTC"``."""
    minutes = round((offset or timedelta()).total_seconds() / 60)
    if minutes == 0:
        return "UTC"
    sign = "+" if minutes > 0 else "−"
    h, m = divmod(abs(minutes), 60)
    return f"UTC{sign}{h}" + (f":{m:02d}" if m else "")


def difference_text(here: datetime, there: datetime) -> str:
    """How far ``there``'s clock is ahead of ``here``'s.

    ``"+3 h"``, ``"−9 h 30 m"`` or ``"Same time"``.
    """
    delta = (there.utcoffset() or timedelta()) - (here.utcoffset() or timedelta())
    minutes = round(delta.total_seconds() / 60)
    if minutes == 0:
        return "Same time"
    sign = "+" if minutes > 0 else "−"
    h, m = divmod(abs(minutes), 60)
    return f"{sign}{h} h" + (f" {m} m" if m else "")


def day_text(here: datetime, there: datetime) -> str:
    """``"Today"``, ``"Tomorrow"`` or ``"Yesterday"`` for ``there`` relative to ``here``."""
    days = (there.date() - here.date()).days
    return {0: "Today", 1: "Tomorrow", -1: "Yesterday"}.get(days, there.strftime("%a %d %b"))


def is_daytime(local: datetime) -> bool:
    return 6 <= local.hour < 18


# ---------------------------------------------------------------------- countdowns
@dataclass(frozen=True)
class Event:
    """A named moment to count down to, stored in UTC."""

    name: str
    at: datetime  # timezone-aware

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "at": self.at.astimezone(UTC).isoformat()}

    @classmethod
    def from_dict(cls, data: object) -> Event | None:
        if not isinstance(data, dict):
            return None
        name, at = data.get("name"), data.get("at")
        if not isinstance(name, str) or not isinstance(at, str) or not name.strip():
            return None
        try:
            moment = datetime.fromisoformat(at)
        except ValueError:
            return None
        if moment.tzinfo is None:
            return None
        return cls(name.strip()[:MAX_EVENT_NAME], moment)


_DATE = re.compile(r"^\s*(\d{4})-(\d{1,2})-(\d{1,2})\s*$")
_TIME = re.compile(r"^\s*(\d{1,2})(?::(\d{2}))?\s*$")


def parse_date(text: str) -> date | None:
    """``"2026-12-25"`` → a date; anything else (including impossible dates) → ``None``."""
    match = _DATE.match(text)
    if match is None:
        return None
    try:
        return date(*(int(g) for g in match.groups()))
    except ValueError:
        return None


def parse_time(text: str) -> time | None:
    """``"9"``, ``"09:30"`` or ``""`` (midnight) → a time; anything else → ``None``."""
    if not text.strip():
        return time(0, 0)
    match = _TIME.match(text)
    if match is None:
        return None
    hour, minute = int(match.group(1)), int(match.group(2) or 0)
    if hour > 23 or minute > 59:
        return None
    return time(hour, minute)


def make_event(name: str, day: str, at: str, zone: tzinfo) -> Event | str:
    """Validate the form fields and build an :class:`Event`, or return the problem."""
    name = " ".join(name.split())[:MAX_EVENT_NAME]
    if not name:
        return "Give the event a name."
    parsed_day = parse_date(day)
    if parsed_day is None:
        return "There's no such date." if _DATE.match(day) else "Enter the date as YYYY-MM-DD."
    parsed_time = parse_time(at)
    if parsed_time is None:
        return "Enter the time as HH:MM (24-hour)."
    return Event(name, datetime.combine(parsed_day, parsed_time, tzinfo=zone))


def countdown_parts(seconds: float) -> tuple[int, int, int, int]:
    """Whole (days, hours, minutes, seconds) in ``abs(seconds)``, rounding down."""
    total = int(abs(seconds))
    days, rem = divmod(total, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)
    return days, hours, minutes, secs


def countdown_text(seconds: float) -> str:
    """``"12d 04:05:06"``, ``"04:05:06"`` within a day, or ``"Now"`` once reached."""
    if seconds <= 0:
        return "Now"
    days, h, m, s = countdown_parts(seconds)
    clock = f"{h:02d}:{m:02d}:{s:02d}"
    return f"{days}d {clock}" if days else clock


def ago_text(seconds: float) -> str:
    """How long ago a past event was: ``"3 days ago"``, ``"5 hours ago"``, ``"just now"``."""
    days, h, m, _ = countdown_parts(seconds)
    for value, unit in ((days, "day"), (h, "hour"), (m, "minute")):
        if value:
            return f"{value} {unit}{'s' if value != 1 else ''} ago"
    return "just now"
