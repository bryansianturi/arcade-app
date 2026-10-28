"""Reaction test rules. Pure Python, no pygame.

Both modes take explicit timestamps (seconds from any monotonic clock) rather
than frame deltas, so a measured time isn't rounded to the frame rate and tests
can drive the clock directly.

- **Classic:** wait for the signal after a random delay, then press. Pressing
  early is a false start and the round is repeated. Five rounds, averaged.
- **Targets:** click targets that appear one at a time; each time runs from the
  target appearing to the hit. Missed clicks are counted, not timed.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Literal

ROUNDS = 5
MIN_DELAY = 1.5
MAX_DELAY = 4.5
TARGETS = 15
TARGET_R = 34
#: A new target is at least this far from the last one, so every hit needs a move.
MIN_JUMP = 160

ClassicState = Literal["idle", "waiting", "go", "result", "early", "done"]


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


@dataclass
class ClassicTest:
    rng: random.Random = field(default_factory=random.Random)
    state: ClassicState = "idle"
    times: list[float] = field(default_factory=list)  # milliseconds
    false_starts: int = 0
    go_at: float = 0.0  # when the current wait ends (or ended)

    @property
    def average(self) -> float:
        return mean(self.times)

    @property
    def last(self) -> float:
        return self.times[-1] if self.times else 0.0

    def tick(self, now: float) -> bool:
        """Show the signal once the wait is over. Returns ``True`` on the change."""
        if self.state == "waiting" and now >= self.go_at:
            self.state = "go"
            return True
        return False

    def press(self, now: float) -> None:
        if self.state in ("idle", "result", "early"):
            self.state = "waiting"
            self.go_at = now + self.rng.uniform(MIN_DELAY, MAX_DELAY)
        elif self.state == "waiting":
            if now >= self.go_at:  # the frame hasn't shown it yet, but the wait is over
                self.tick(now)
                self.press(now)
                return
            self.state = "early"
            self.false_starts += 1
        elif self.state == "go":
            self.times.append(max(0.0, (now - self.go_at) * 1000))
            self.state = "done" if len(self.times) >= ROUNDS else "result"


@dataclass
class TargetRun:
    width: float
    height: float
    rng: random.Random = field(default_factory=random.Random)
    times: list[float] = field(default_factory=list)  # milliseconds
    misses: int = 0
    target: tuple[float, float] | None = None
    shown_at: float = 0.0

    @property
    def started(self) -> bool:
        return self.target is not None or bool(self.times)

    @property
    def done(self) -> bool:
        return len(self.times) >= TARGETS

    @property
    def average(self) -> float:
        return mean(self.times)

    def start(self, now: float) -> None:
        self._spawn(now)

    def _spawn(self, now: float) -> None:
        pad = TARGET_R + 6
        last = self.target
        for _ in range(100):
            pos = (
                self.rng.uniform(pad, self.width - pad),
                self.rng.uniform(pad, self.height - pad),
            )
            if last is None or math.dist(pos, last) >= MIN_JUMP:
                break
        self.target = pos
        self.shown_at = now

    def click(self, x: float, y: float, now: float) -> bool:
        """Click at (x, y) in arena coordinates. Returns ``True`` on a hit."""
        if self.target is None or self.done:
            return False
        if math.dist((x, y), self.target) > TARGET_R:
            self.misses += 1
            return False
        self.times.append((now - self.shown_at) * 1000)
        if len(self.times) >= TARGETS:
            self.target = None
        else:
            self._spawn(now)
        return True
