"""Echo Pads rules: watch a sequence of pads light up, then repeat it. Pure Python, no pygame.

Pads are numbered clockwise from the top: 0 up, 1 right, 2 down, 3 left. Each
round the sequence grows by one. In **classic** mode one step is appended; in
**shuffle** mode a whole new sequence is drawn, so nothing carries over.
Playback speeds up as the sequence gets longer.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Literal

PADS = 4
#: Pause before playback starts, and after a correctly repeated round.
LEAD = 0.6
SUCCESS_PAUSE = 0.7

Mode = Literal["classic", "shuffle"]
MODES: tuple[Mode, ...] = ("classic", "shuffle")
State = Literal["ready", "showing", "input", "success", "over"]


def step_times(length: int) -> tuple[float, float]:
    """(lit, gap) seconds per playback step for a sequence of ``length``."""
    lit = max(0.22, 0.6 - 0.025 * (length - 1))
    return lit, lit * 0.45


@dataclass
class EchoGame:
    mode: Mode = "classic"
    rng: random.Random = field(default_factory=random.Random)
    sequence: list[int] = field(default_factory=list)
    state: State = "ready"
    #: While showing: the step being played. While repeating: the next step expected.
    pos: int = 0
    timer: float = 0.0
    #: The pad lit by playback right now, if any.
    lit: int | None = None
    #: Length of the longest sequence repeated correctly.
    score: int = 0
    #: After a mistake: (pad pressed, pad expected).
    wrong: tuple[int, int] | None = None

    def start(self) -> None:
        if self.state != "ready":
            return
        self.sequence = [self.rng.randrange(PADS)]
        self._show()

    def _show(self) -> None:
        self.state = "showing"
        self.pos = 0
        self.timer = -LEAD
        self.lit = None

    def _extend(self) -> None:
        length = len(self.sequence) + 1
        if self.mode == "shuffle":
            self.sequence = [self.rng.randrange(PADS) for _ in range(length)]
        else:
            self.sequence.append(self.rng.randrange(PADS))

    def update(self, dt: float) -> None:
        if self.state == "showing":
            self.timer += dt
            lit_for, gap = step_times(len(self.sequence))
            if self.timer < 0:
                return
            step, into = divmod(self.timer, lit_for + gap)
            self.pos = int(step)
            if self.pos >= len(self.sequence):
                self.state, self.pos, self.lit = "input", 0, None
            else:
                self.lit = self.sequence[self.pos] if into < lit_for else None
        elif self.state == "success":
            self.timer += dt
            if self.timer >= SUCCESS_PAUSE:
                self._extend()
                self._show()

    def press(self, pad: int) -> bool | None:
        """Press ``pad`` while repeating. ``True`` right, ``False`` wrong, ``None`` ignored."""
        if self.state != "input":
            return None
        expected = self.sequence[self.pos]
        if pad != expected:
            self.state = "over"
            self.wrong = (pad, expected)
            return False
        self.pos += 1
        if self.pos == len(self.sequence):
            self.score = len(self.sequence)
            self.state = "success"
            self.timer = 0.0
        return True
