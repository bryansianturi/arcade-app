"""The wheel: options, slices and a spin that lands on a fairly chosen winner. No pygame.

Angles are radians measured clockwise from the top, where the pointer is. Slice
``i`` covers ``[i·w, (i+1)·w)`` of the wheel (``w = 2π / n``); turning the wheel
clockwise by ``angle`` puts the wheel's ``-angle`` under the pointer.

The winner is drawn uniformly *before* the animation starts, then the spin is
planned to stop inside that slice, so the result never depends on frame timing.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

TAU = math.tau
MAX_OPTIONS = 20
MAX_LABEL = 30
DEFAULT_OPTIONS = ("Pizza", "Sushi", "Tacos", "Curry", "Burgers", "Salad")


def clean_option(text: str) -> str:
    return " ".join(text.split())[:MAX_LABEL]


def slice_at(angle: float, n: int) -> int:
    """Index of the slice under the pointer when the wheel is turned by ``angle``."""
    width = TAU / n
    return min(n - 1, int(((-angle) % TAU) / width))


def ease_out(t: float) -> float:
    """Quick start, long gentle stop (quartic ease-out)."""
    t = min(1.0, max(0.0, t))
    return 1 - (1 - t) ** 4


@dataclass
class Wheel:
    options: list[str] = field(default_factory=lambda: list(DEFAULT_OPTIONS))
    angle: float = 0.0
    winner: int | None = None  # index of the last result
    _from: float = 0.0
    _to: float = 0.0
    _duration: float = 0.0
    _elapsed: float = 0.0

    @property
    def spinning(self) -> bool:
        return self._elapsed < self._duration

    @property
    def progress(self) -> float:
        return self._elapsed / self._duration if self._duration else 1.0

    def add(self, text: str) -> bool:
        text = clean_option(text)
        if not text or len(self.options) >= MAX_OPTIONS or self.spinning:
            return False
        self.options.append(text)
        self.winner = None
        return True

    def remove(self, index: int) -> bool:
        if self.spinning or not 0 <= index < len(self.options):
            return False
        del self.options[index]
        self.winner = None
        return True

    def clear(self) -> None:
        if not self.spinning:
            self.options.clear()
            self.winner = None

    def spin(self, rng: random.Random, seconds: float | None = None) -> int | None:
        """Pick the winner now and plan a spin that stops on it. ``None`` if it can't spin."""
        n = len(self.options)
        if n < 2 or self.spinning:
            return None
        winner = rng.randrange(n)
        width = TAU / n
        # Stop somewhere inside the slice, away from its edges, so it's never ambiguous.
        target = (winner + rng.uniform(0.15, 0.85)) * width
        delta = (-target - self.angle) % TAU
        turns = rng.randint(4, 6)
        self._from = self.angle
        self._to = self.angle + turns * TAU + delta
        self._duration = seconds if seconds is not None else rng.uniform(4.0, 5.5)
        self._elapsed = 0.0
        self.winner = winner
        return winner

    def update(self, dt: float) -> bool:
        """Advance the spin; returns ``True`` on the frame it stops."""
        if not self.spinning:
            return False
        self._elapsed = min(self._duration, self._elapsed + dt)
        self.angle = self._from + (self._to - self._from) * ease_out(self.progress)
        stopped = self._elapsed >= self._duration
        if stopped:
            self.angle %= TAU
        return stopped

    def under_pointer(self) -> int:
        return slice_at(self.angle, len(self.options)) if self.options else -1
