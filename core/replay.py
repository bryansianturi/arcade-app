"""Replays for real-time games: record the seed and inputs, play them back exactly.

A game is replayable when its simulation is deterministic: all randomness comes
from one seeded ``random.Random`` and it advances in fixed steps. Then a run is
fully described by the seed plus *which commands arrived before which step*:

    stepper = FixedStep()
    recorder = Recorder(seed)

    # input handler: apply a command now and record it
    game.turn(LEFT); recorder.command("turn", "left")

    # update(dt):
    for _ in range(stepper.steps(dt)):
        game.update(STEP); recorder.advance()

    # game over:
    replays.offer(recorder.finish(app_id, score, variant), order="higher")

Playback creates the game from ``replay.seed`` and, before every step, applies
``player.commands_for(tick)`` through the same code path the live input uses.

:class:`ReplayStore` keeps the best run per app and variant in
``replays/<app_id>.json``. Commands are small JSON lists, so a several-minute
run is a few kilobytes.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal

from core.storage import Storage

log = logging.getLogger(__name__)

STEP = 1 / 120  # seconds per simulation step
MAX_STEPS_PER_FRAME = 24  # don't spiral after a long hitch (dt is clamped anyway)
FORMAT = 1

Arg = str | int | float | bool


@dataclass(frozen=True)
class Command:
    tick: int  # applied before simulation step number ``tick`` (0-based)
    name: str
    args: tuple[Arg, ...] = ()

    def to_json(self) -> list[Arg]:
        return [self.tick, self.name, *self.args]

    @classmethod
    def from_json(cls, data: Any) -> Command:
        if not (isinstance(data, list) and len(data) >= 2):
            raise ValueError(f"bad command {data!r}")
        tick, name, *args = data
        if not isinstance(tick, int) or tick < 0 or not isinstance(name, str):
            raise ValueError(f"bad command {data!r}")
        if not all(isinstance(a, str | int | float | bool) for a in args):
            raise ValueError(f"bad command arguments {data!r}")
        return cls(tick, name, tuple(args))


@dataclass
class Replay:
    """One recorded run."""

    app_id: str
    seed: int
    ticks: int  # number of simulation steps in the run
    score: float
    variant: str = "default"
    step: float = STEP
    commands: list[Command] = field(default_factory=list)
    app_version: str = ""
    date: str = ""

    @property
    def seconds(self) -> float:
        return self.ticks * self.step

    def to_dict(self) -> dict[str, Any]:
        return {
            "format": FORMAT,
            "app_id": self.app_id,
            "variant": self.variant,
            "seed": self.seed,
            "ticks": self.ticks,
            "score": self.score,
            "step": self.step,
            "app_version": self.app_version,
            "date": self.date,
            "commands": [c.to_json() for c in self.commands],
        }

    @classmethod
    def from_dict(cls, data: Any) -> Replay:
        """Parse a stored replay. Raises ``ValueError`` (or ``KeyError``/``TypeError``)."""
        if not isinstance(data, dict) or data.get("format") != FORMAT:
            raise ValueError("unsupported replay format")
        commands = [Command.from_json(c) for c in data["commands"]]
        ticks = int(data["ticks"])
        if any(c.tick > ticks for c in commands):
            raise ValueError("command after the end of the run")
        return cls(
            app_id=str(data["app_id"]),
            seed=int(data["seed"]),
            ticks=ticks,
            score=float(data["score"]),
            variant=str(data.get("variant", "default")),
            step=float(data["step"]),
            commands=commands,
            app_version=str(data.get("app_version", "")),
            date=str(data.get("date", "")),
        )


class FixedStep:
    """Turns variable frame times into a whole number of fixed simulation steps."""

    def __init__(self, step: float = STEP) -> None:
        self.step = step
        self.accumulator = 0.0

    def steps(self, dt: float) -> int:
        self.accumulator += dt
        n = int(self.accumulator / self.step)
        self.accumulator -= n * self.step
        return min(n, MAX_STEPS_PER_FRAME)

    @property
    def alpha(self) -> float:
        """How far (0..1) the current frame is into the next step, for interpolation."""
        return self.accumulator / self.step


class Recorder:
    """Collects commands, stamped with the number of steps simulated so far."""

    def __init__(self, seed: int, step: float = STEP) -> None:
        self.seed = seed
        self.step = step
        self.tick = 0
        self.commands: list[Command] = []

    def command(self, name: str, *args: Arg) -> None:
        self.commands.append(Command(self.tick, name, args))

    def advance(self) -> None:
        self.tick += 1

    def finish(
        self, app_id: str, score: float, variant: str = "default", app_version: str = ""
    ) -> Replay:
        return Replay(
            app_id=app_id,
            seed=self.seed,
            ticks=self.tick,
            score=score,
            variant=variant,
            step=self.step,
            commands=list(self.commands),
            app_version=app_version,
            date=date.today().isoformat(),
        )


class Player:
    """Feeds a replay's commands back, step by step."""

    def __init__(self, replay: Replay) -> None:
        self.replay = replay
        self.tick = 0
        self._index = 0

    def commands_for(self, tick: int) -> Iterator[Command]:
        """Commands to apply before step ``tick`` (call with increasing ticks)."""
        commands = self.replay.commands
        while self._index < len(commands) and commands[self._index].tick <= tick:
            yield commands[self._index]
            self._index += 1

    def advance(self) -> None:
        self.tick += 1

    @property
    def done(self) -> bool:
        return self.tick >= self.replay.ticks

    @property
    def progress(self) -> float:
        return min(1.0, self.tick / max(1, self.replay.ticks))


class ReplayStore:
    """The best replay per app and variant, in ``replays/<app_id>.json``."""

    def __init__(self, storage: Storage) -> None:
        self.storage = storage

    @staticmethod
    def _file(app_id: str) -> str:
        return f"replays/{app_id}.json"

    def best(self, app_id: str, variant: str = "default") -> Replay | None:
        raw = self.storage.load_json(self._file(app_id)).get(variant)
        if raw is None:
            return None
        try:
            return Replay.from_dict(raw)
        except (ValueError, KeyError, TypeError) as exc:
            log.warning("Ignoring unreadable replay for %s/%s: %s", app_id, variant, exc)
            return None

    def offer(self, replay: Replay, order: Literal["higher", "lower"] = "higher") -> bool:
        """Keep ``replay`` if it beats the stored one for its variant. Returns whether kept."""
        old = self.best(replay.app_id, replay.variant)
        if old is not None:
            better = replay.score < old.score if order == "lower" else replay.score > old.score
            if not better:
                return False
        data = self.storage.load_json(self._file(replay.app_id))
        data[replay.variant] = replay.to_dict()
        self.storage.save_json(self._file(replay.app_id), data)
        return True
