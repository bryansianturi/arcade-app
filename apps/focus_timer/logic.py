"""Focus Timer logic: a Pomodoro cycle and a lap stopwatch. No pygame.

Both use absolute clock readings (``now``, in seconds) rather than summing
frame times, so they stay accurate if frames are dropped and can be saved
and resumed: the timer keeps going while you're in another app.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

Phase = Literal["focus", "short", "long"]
PHASES: tuple[Phase, ...] = ("focus", "short", "long")
PHASE_LABELS: dict[Phase, str] = {"focus": "Focus", "short": "Short break", "long": "Long break"}
MIN_MINUTES, MAX_MINUTES = 1, 90


@dataclass
class Clock:
    """Accumulated running time that can be started and stopped."""

    accumulated: float = 0.0
    started_at: float | None = None

    @property
    def running(self) -> bool:
        return self.started_at is not None

    def elapsed(self, now: float) -> float:
        extra = now - self.started_at if self.started_at is not None else 0.0
        return self.accumulated + max(0.0, extra)

    def start(self, now: float) -> None:
        if self.started_at is None:
            self.started_at = now

    def stop(self, now: float) -> None:
        if self.started_at is not None:
            self.accumulated = self.elapsed(now)
            self.started_at = None

    def reset(self) -> None:
        self.accumulated = 0.0
        self.started_at = None


@dataclass
class Stopwatch:
    clock: Clock = field(default_factory=Clock)
    laps: list[float] = field(default_factory=list)  # cumulative split times

    def toggle(self, now: float) -> None:
        if self.clock.running:
            self.clock.stop(now)
        else:
            self.clock.start(now)

    def lap(self, now: float) -> None:
        if self.clock.running:
            self.laps.append(self.clock.elapsed(now))

    def reset(self) -> None:
        self.clock.reset()
        self.laps.clear()

    def lap_times(self) -> list[float]:
        """Duration of each lap (not cumulative)."""
        out, previous = [], 0.0
        for split in self.laps:
            out.append(split - previous)
            previous = split
        return out


@dataclass
class Pomodoro:
    minutes: dict[Phase, int] = field(default_factory=lambda: {"focus": 25, "short": 5, "long": 15})
    long_every: int = 4
    phase: Phase = "focus"
    completed: int = 0  # focus sessions finished
    clock: Clock = field(default_factory=Clock)
    just_finished: Phase | None = None  # set when a phase ends; cleared when the next starts

    def duration(self, phase: Phase | None = None) -> float:
        return self.minutes[phase or self.phase] * 60.0

    def remaining(self, now: float) -> float:
        return max(0.0, self.duration() - self.clock.elapsed(now))

    def progress(self, now: float) -> float:
        return 1 - self.remaining(now) / self.duration()

    def next_phase(self) -> Phase:
        if self.phase != "focus":
            return "focus"
        # ``completed`` already includes the session that just ended when this is called.
        return "long" if self.completed % self.long_every == 0 else "short"

    def toggle(self, now: float) -> None:
        if self.clock.running:
            self.clock.stop(now)
        else:
            self.just_finished = None
            self.clock.start(now)

    def update(self, now: float) -> bool:
        """Advance phases if time ran out. Returns ``True`` when a phase just ended."""
        if not self.clock.running or self.remaining(now) > 0:
            return False
        ended = self.phase
        if ended == "focus":
            self.completed += 1
        self.phase = self.next_phase()
        self.clock.reset()
        self.just_finished = ended
        return True

    def reset(self) -> None:
        """Restart the current phase."""
        self.clock.reset()

    def skip(self) -> None:
        """Jump to the next phase without counting the current one."""
        if self.phase == "focus":
            self.phase = "long" if (self.completed + 1) % self.long_every == 0 else "short"
        else:
            self.phase = "focus"
        self.clock.reset()
        self.just_finished = None

    def adjust(self, phase: Phase, delta: int) -> None:
        """Change a phase length in minutes (only while that phase isn't running)."""
        if self.clock.running and phase == self.phase:
            return
        self.minutes[phase] = max(MIN_MINUTES, min(MAX_MINUTES, self.minutes[phase] + delta))

    # ------------------------------------------------------------------ persistence
    def to_dict(self) -> dict[str, Any]:
        return {
            "minutes": dict(self.minutes),
            "phase": self.phase,
            "completed": self.completed,
            "accumulated": self.clock.accumulated,
            "started_at": self.clock.started_at,
        }

    @classmethod
    def from_dict(cls, data: Any) -> Pomodoro:
        p = cls()
        if not isinstance(data, dict):
            return p
        minutes = data.get("minutes")
        if isinstance(minutes, dict):
            for phase in PHASES:
                value = minutes.get(phase)
                if isinstance(value, int) and MIN_MINUTES <= value <= MAX_MINUTES:
                    p.minutes[phase] = value
        if data.get("phase") in PHASES:
            p.phase = data["phase"]
        if isinstance(data.get("completed"), int):
            p.completed = max(0, data["completed"])
        if isinstance(data.get("accumulated"), int | float):
            p.clock.accumulated = float(data["accumulated"])
        if isinstance(data.get("started_at"), int | float):
            p.clock.started_at = float(data["started_at"])
        return p
