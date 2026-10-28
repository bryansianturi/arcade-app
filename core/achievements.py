"""Achievements: per-app goals declared in ``app.toml`` and unlocked from app code.

An app declares its achievements in its manifest::

    [[achievements]]
    id = "length_25"
    name = "Noodle"
    description = "Grow to a length of 25."

and unlocks one with ``self.unlock("length_25")``. Ids are namespaced by app id
when stored (``"snake/length_25"``), so different apps can reuse short names.
Unlocking is idempotent; the first unlock is saved and announced with a toast.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime

from core.storage import Storage

log = logging.getLogger(__name__)

ACHIEVEMENTS_FILE = "achievements.json"


@dataclass(frozen=True)
class Achievement:
    """One achievement definition (from an app manifest)."""

    id: str
    name: str
    description: str
    hidden: bool = False  # description shown as "???" until unlocked


def key(app_id: str, achievement_id: str) -> str:
    return f"{app_id}/{achievement_id}"


class AchievementService:
    """Stores unlocks and announces new ones.

    ``on_unlock`` is called with ``(app_id, achievement)`` for every *new* unlock;
    the main program uses it to show a toast.
    """

    def __init__(
        self,
        storage: Storage,
        on_unlock: Callable[[str, Achievement], None] | None = None,
    ) -> None:
        self.storage = storage
        self.on_unlock = on_unlock
        self._defs: dict[str, dict[str, Achievement]] = {}
        raw = storage.load_json(ACHIEVEMENTS_FILE)
        self._unlocked: dict[str, str] = {
            k: v for k, v in raw.items() if isinstance(k, str) and isinstance(v, str)
        }

    def define(self, app_id: str, achievements: Iterable[Achievement]) -> None:
        """Register the achievements an app declares (done for every discovered app)."""
        self._defs[app_id] = {a.id: a for a in achievements}

    def definitions(self, app_id: str) -> list[Achievement]:
        return list(self._defs.get(app_id, {}).values())

    def unlock(self, app_id: str, achievement_id: str) -> bool:
        """Unlock an achievement. Returns ``True`` only the first time.

        Unknown ids are logged and ignored so a typo can never crash a game.
        """
        definition = self._defs.get(app_id, {}).get(achievement_id)
        if definition is None:
            log.warning("Unknown achievement %r for app %r", achievement_id, app_id)
            return False
        k = key(app_id, achievement_id)
        if k in self._unlocked:
            return False
        self._unlocked[k] = datetime.now().isoformat(timespec="seconds")
        self.storage.save_json(ACHIEVEMENTS_FILE, dict(self._unlocked))
        if self.on_unlock is not None:
            self.on_unlock(app_id, definition)
        return True

    def is_unlocked(self, app_id: str, achievement_id: str) -> bool:
        return key(app_id, achievement_id) in self._unlocked

    def unlocked_at(self, app_id: str, achievement_id: str) -> str | None:
        """ISO timestamp of the unlock, if unlocked."""
        return self._unlocked.get(key(app_id, achievement_id))

    def progress(self, app_id: str | None = None) -> tuple[int, int]:
        """``(unlocked, total)`` for one app, or across all apps."""
        apps = [app_id] if app_id is not None else list(self._defs)
        total = done = 0
        for a in apps:
            for d in self._defs.get(a, {}).values():
                total += 1
                done += key(a, d.id) in self._unlocked
        return done, total

    def reset(self) -> None:
        """Forget every unlock."""
        self._unlocked.clear()
        self.storage.save_json(ACHIEVEMENTS_FILE, {})
