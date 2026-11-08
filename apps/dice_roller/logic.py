"""Dice pools, dice notation, rolls and coin flips. No pygame."""

from __future__ import annotations

import random
import re
from dataclasses import dataclass, field
from typing import Any, Literal

#: The dice with buttons in the app. Typed notation also accepts other sizes.
DIE_SIDES = (4, 6, 8, 10, 12, 20)
MIN_SIDES, MAX_SIDES = 2, 100
MAX_DICE = 12
MAX_MODIFIER = 99

_TERM = re.compile(r"([+-]?)\s*(?:(\d*)\s*[dD]\s*(\d+)|(\d+))")


@dataclass
class Pool:
    """How many of each die to roll, plus a flat modifier."""

    counts: dict[int, int] = field(default_factory=dict)
    modifier: int = 0

    @property
    def size(self) -> int:
        return sum(self.counts.values())

    def add(self, sides: int, n: int = 1) -> bool:
        """Add ``n`` dice if they fit within :data:`MAX_DICE`."""
        if not MIN_SIDES <= sides <= MAX_SIDES or n < 1 or self.size + n > MAX_DICE:
            return False
        self.counts[sides] = self.counts.get(sides, 0) + n
        return True

    def remove(self, sides: int) -> bool:
        if self.counts.get(sides, 0) <= 0:
            return False
        self.counts[sides] -= 1
        if not self.counts[sides]:
            del self.counts[sides]
        return True

    def set_modifier(self, value: int) -> None:
        self.modifier = max(-MAX_MODIFIER, min(MAX_MODIFIER, value))

    def clear(self) -> None:
        self.counts.clear()
        self.modifier = 0

    def dice(self) -> list[int]:
        """Each die's sides, smallest dice first: ``[6, 6, 20]``."""
        return [sides for sides in sorted(self.counts) for _ in range(self.counts[sides])]

    def notation(self) -> str:
        """``"2d6 + 1d20 - 1"``; ``""`` for an empty pool."""
        text = " + ".join(f"{self.counts[s]}d{s}" for s in sorted(self.counts))
        if text and self.modifier:
            text += f" {'-' if self.modifier < 0 else '+'} {abs(self.modifier)}"
        return text

    def bounds(self) -> tuple[int, int]:
        """Lowest and highest possible totals."""
        return self.size + self.modifier, sum(self.dice()) + self.modifier

    def average(self) -> float:
        return sum((s + 1) / 2 for s in self.dice()) + self.modifier

    def to_dict(self) -> dict[str, Any]:
        return {"counts": {str(s): n for s, n in self.counts.items()}, "modifier": self.modifier}

    @classmethod
    def from_dict(cls, data: object) -> Pool:
        pool = cls()
        if not isinstance(data, dict):
            return pool
        counts = data.get("counts")
        for key, n in counts.items() if isinstance(counts, dict) else []:
            if isinstance(key, str) and key.isdigit() and isinstance(n, int):
                pool.add(int(key), n)
        if isinstance(data.get("modifier"), int):
            pool.set_modifier(data["modifier"])
        return pool


def parse_notation(text: str) -> Pool | None:
    """Parse dice notation like ``"3d6+2"``, ``"d20 + d4 - 1"`` or ``"2d8+1d6"``.

    Dice can only be added; constants can be added or subtracted. Returns
    ``None`` for anything else, or if the pool would exceed the limits.
    """
    text = text.strip()
    if not text:
        return None
    pool, pos = Pool(), 0
    modifier = 0
    while pos < len(text):
        while pos < len(text) and text[pos].isspace():
            pos += 1
        match = _TERM.match(text, pos)
        if match is None or (pos > 0 and not match.group(1)):
            return None  # terms after the first need a sign
        sign, count, sides, constant = match.groups()
        if sides is not None:
            if sign == "-" or not pool.add(int(sides), int(count) if count else 1):
                return None
        else:
            modifier += -int(constant) if sign == "-" else int(constant)
        pos = match.end()
    if not pool.size or abs(modifier) > MAX_MODIFIER:
        return None
    pool.modifier = modifier
    return pool


@dataclass(frozen=True)
class Roll:
    """One roll: each die as ``(sides, value)``, the modifier and the notation rolled."""

    dice: tuple[tuple[int, int], ...]
    modifier: int
    notation: str

    @property
    def total(self) -> int:
        return sum(value for _, value in self.dice) + self.modifier

    def to_dict(self) -> dict[str, Any]:
        return {
            "dice": [list(d) for d in self.dice],
            "modifier": self.modifier,
            "notation": self.notation,
        }

    @classmethod
    def from_dict(cls, data: object) -> Roll | None:
        if not isinstance(data, dict):
            return None
        dice, modifier, notation = data.get("dice"), data.get("modifier"), data.get("notation")
        if not (isinstance(dice, list) and isinstance(modifier, int) and isinstance(notation, str)):
            return None
        parsed = []
        for d in dice:
            if not (isinstance(d, list) and len(d) == 2 and all(isinstance(x, int) for x in d)):
                return None
            if not 1 <= d[1] <= d[0]:
                return None
            parsed.append((d[0], d[1]))
        return cls(tuple(parsed), modifier, notation)


def roll(pool: Pool, rng: random.Random) -> Roll:
    """Roll every die in ``pool``."""
    dice = tuple((sides, rng.randint(1, sides)) for sides in pool.dice())
    return Roll(dice, pool.modifier, pool.notation())


Side = Literal["heads", "tails"]


def flip(rng: random.Random) -> Side:
    return "heads" if rng.random() < 0.5 else "tails"


@dataclass
class CoinStats:
    """Running tally of flips, with the current and longest streaks."""

    heads: int = 0
    tails: int = 0
    streak_side: Side | None = None
    streak: int = 0
    best_streak: int = 0
    recent: list[Side] = field(default_factory=list)

    RECENT = 24

    @property
    def total(self) -> int:
        return self.heads + self.tails

    def record(self, side: Side) -> None:
        if side == "heads":
            self.heads += 1
        else:
            self.tails += 1
        self.streak = self.streak + 1 if side == self.streak_side else 1
        self.streak_side = side
        self.best_streak = max(self.best_streak, self.streak)
        self.recent = [*self.recent, side][-self.RECENT :]

    def share(self, side: Side) -> float:
        """Fraction of flips that came up ``side`` (0 with no flips)."""
        if not self.total:
            return 0.0
        return (self.heads if side == "heads" else self.tails) / self.total
