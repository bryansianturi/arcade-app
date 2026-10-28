"""Usage statistics: play time, sessions and last-played time per app.

Tracked automatically by :class:`core.app_host.AppHost`; apps don't need any
code for it. Play time only counts while the app is running (not while the
pause menu is open). Saved to ``stats.json``, at the end of each session and
every :data:`SAVE_EVERY` seconds of play so a crash loses little.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from core.storage import Storage

STATS_FILE = "stats.json"
SAVE_EVERY = 30.0


@dataclass
class AppStats:
    seconds: float = 0.0
    sessions: int = 0
    last_played: str = ""  # ISO timestamp

    @classmethod
    def from_dict(cls, data: object) -> AppStats:
        if not isinstance(data, dict):
            return cls()
        seconds = data.get("seconds", 0.0)
        sessions = data.get("sessions", 0)
        last = data.get("last_played", "")
        return cls(
            float(seconds) if isinstance(seconds, int | float) and seconds >= 0 else 0.0,
            sessions if isinstance(sessions, int) and sessions >= 0 else 0,
            last if isinstance(last, str) else "",
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "seconds": round(self.seconds, 1),
            "sessions": self.sessions,
            "last_played": self.last_played,
        }


class StatsService:
    """Per-app usage counters."""

    def __init__(self, storage: Storage, clock: Callable[[], datetime] = datetime.now) -> None:
        self.storage = storage
        self.clock = clock
        raw = storage.load_json(STATS_FILE)
        self.apps: dict[str, AppStats] = {k: AppStats.from_dict(v) for k, v in raw.items()}
        self._unsaved = 0.0

    def get(self, app_id: str) -> AppStats:
        return self.apps.get(app_id, AppStats())

    def start_session(self, app_id: str) -> None:
        entry = self.apps.setdefault(app_id, AppStats())
        entry.sessions += 1
        entry.last_played = self.clock().isoformat(timespec="seconds")
        self.save()

    def add_time(self, app_id: str, seconds: float) -> None:
        if seconds <= 0:
            return
        self.apps.setdefault(app_id, AppStats()).seconds += seconds
        self._unsaved += seconds
        if self._unsaved >= SAVE_EVERY:
            self.save()

    def end_session(self, app_id: str) -> None:
        entry = self.apps.get(app_id)
        if entry is not None:
            entry.last_played = self.clock().isoformat(timespec="seconds")
        self.save()

    def save(self) -> None:
        self._unsaved = 0.0
        self.storage.save_json(STATS_FILE, {k: v.to_dict() for k, v in self.apps.items()})

    # ------------------------------------------------------------------ queries
    @property
    def total_seconds(self) -> float:
        return sum(s.seconds for s in self.apps.values())

    @property
    def total_sessions(self) -> int:
        return sum(s.sessions for s in self.apps.values())

    def most_played(self, known: set[str] | None = None) -> str | None:
        """The app id with the most play time (ties: most sessions)."""
        candidates = [
            (s.seconds, s.sessions, app_id)
            for app_id, s in self.apps.items()
            if s.sessions and (known is None or app_id in known)
        ]
        return max(candidates)[2] if candidates else None

    def recent(self, limit: int, known: set[str] | None = None) -> list[str]:
        """App ids by last played, newest first."""
        played = [
            (s.last_played, app_id)
            for app_id, s in self.apps.items()
            if s.last_played and (known is None or app_id in known)
        ]
        return [app_id for _, app_id in sorted(played, reverse=True)[:limit]]


def format_duration(seconds: float) -> str:
    """``42`` → ``"42s"``, ``754`` → ``"12m"``, ``5400`` → ``"1h 30m"``."""
    total = int(seconds)
    if total < 60:
        return f"{total}s"
    hours, rem = divmod(total, 3600)
    minutes = rem // 60
    return f"{hours}h {minutes:02d}m" if hours else f"{minutes}m"


def format_ago(iso: str, now: datetime) -> str:
    """A friendly relative time: "just now", "5 min ago", "yesterday", "3 days ago"."""
    if not iso:
        return "never"
    try:
        then = datetime.fromisoformat(iso)
    except ValueError:
        return "—"
    seconds = (now - then).total_seconds()
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        return f"{int(seconds // 60)} min ago"
    if seconds < 86400 and then.date() == now.date():
        return f"{int(seconds // 3600)} h ago"
    days = (now.date() - then.date()).days
    if days <= 1:
        return "yesterday"
    if days < 30:
        return f"{days} days ago"
    return then.strftime("%b %d, %Y")
