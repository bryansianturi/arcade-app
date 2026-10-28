"""Daily challenges: one date-seeded puzzle per app per day, the same for everyone.

The seed is a hash of the app id and the calendar date, so any app can offer a
daily mode by building its puzzle from ``self.daily.rng()``::

    game = Puzzle.generate(self.daily.rng())
    ...
    if solved:
        self.daily.record(seconds, order="lower")

Everyone running the same version of an app on the same (local) date gets the
same puzzle. :class:`DailyChallenge` also remembers each day's result in the
app's private data, so the UI can show "done today" and a streak.
"""

from __future__ import annotations

import hashlib
import random
from collections.abc import Callable, MutableMapping
from datetime import date, timedelta
from typing import Any, Literal

DATA_KEY = "daily"
KEEP_DAYS = 400  # results older than this are pruned


def daily_seed(app_id: str, day: date) -> int:
    """A stable 64-bit seed for ``app_id`` on ``day`` (independent of PYTHONHASHSEED)."""
    digest = hashlib.sha256(f"arcade-daily:{app_id}:{day.isoformat()}".encode()).digest()
    return int.from_bytes(digest[:8], "big")


class DailyChallenge:
    """Today's seed plus a per-day results log stored in an app's data mapping."""

    def __init__(
        self,
        app_id: str,
        data: MutableMapping[str, Any],
        today: Callable[[], date] | None = None,
    ) -> None:
        self.app_id = app_id
        self.data = data
        self._today = today or (lambda: date.today())  # looked up per call (patchable)

    @property
    def today(self) -> date:
        return self._today()

    def seed(self, day: date | None = None) -> int:
        return daily_seed(self.app_id, day or self.today)

    def rng(self, day: date | None = None) -> random.Random:
        """A fresh RNG seeded for ``day`` (default: today)."""
        return random.Random(self.seed(day))

    # ------------------------------------------------------------------ results
    def _results(self) -> dict[str, float]:
        raw = self.data.get(DATA_KEY)
        if not isinstance(raw, dict):
            return {}
        return {k: float(v) for k, v in raw.items() if isinstance(v, int | float)}

    def result(self, day: date | None = None) -> float | None:
        """The recorded result for ``day`` (default today), if completed."""
        return self._results().get((day or self.today).isoformat())

    def completed(self, day: date | None = None) -> bool:
        return self.result(day) is not None

    def record(
        self, value: float, order: Literal["higher", "lower"] = "higher", day: date | None = None
    ) -> bool:
        """Store ``day``'s result, keeping the better one. Returns ``True`` if it improved.

        The caller should ``self.data.save()`` (``AppData``) afterwards, or rely on
        the app saving its data on exit.
        """
        key = (day or self.today).isoformat()
        results = self._results()
        old = results.get(key)
        better = old is None or (value < old if order == "lower" else value > old)
        if better:
            results[key] = value
            cutoff = (self.today - timedelta(days=KEEP_DAYS)).isoformat()
            self.data[DATA_KEY] = {k: v for k, v in results.items() if k >= cutoff}
        return better

    def streak(self) -> int:
        """Consecutive days completed, ending today (or yesterday if today isn't done yet)."""
        results = self._results()
        day = self.today
        if day.isoformat() not in results:
            day -= timedelta(days=1)
        count = 0
        while day.isoformat() in results:
            count += 1
            day -= timedelta(days=1)
        return count
