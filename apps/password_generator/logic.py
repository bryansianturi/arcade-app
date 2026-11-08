"""Password generation and strength estimation. No pygame.

Passwords come from :class:`secrets.SystemRandom` (the OS's cryptographic
random source) unless a test passes its own ``random.Random``. Strength is the
entropy of the *generator*, ``length × log2(pool size)``, which is exact for a
random password, unlike pattern-guessing meters meant for human-made ones.
"""

from __future__ import annotations

import math
import random
import secrets
import string
from dataclasses import dataclass
from typing import Any

MIN_LENGTH, MAX_LENGTH = 4, 64
SYMBOLS = "!#$%&*+-=?@^_~"
#: Characters that are easy to confuse when reading or typing a password.
AMBIGUOUS = frozenset("Il1|O0o")

#: Guesses per second for an offline attack on a fast hash, for the time-to-crack line.
GUESSES_PER_SECOND = 1e10

STRENGTH_LABELS = ("Very weak", "Weak", "Fair", "Strong", "Very strong")
#: Lower bounds in bits for each label after the first.
STRENGTH_BITS = (28, 36, 60, 100)


@dataclass
class Options:
    """What the next password should contain."""

    length: int = 16
    lower: bool = True
    upper: bool = True
    digits: bool = True
    symbols: bool = True
    avoid_ambiguous: bool = False

    def sets(self) -> list[str]:
        """The enabled character sets, with ambiguous characters removed if asked."""
        chosen = [
            chars
            for chars, on in (
                (string.ascii_lowercase, self.lower),
                (string.ascii_uppercase, self.upper),
                (string.digits, self.digits),
                (SYMBOLS, self.symbols),
            )
            if on
        ]
        if self.avoid_ambiguous:
            chosen = ["".join(c for c in chars if c not in AMBIGUOUS) for chars in chosen]
        return chosen

    def pool(self) -> str:
        return "".join(self.sets())

    def set_length(self, length: int) -> None:
        self.length = max(MIN_LENGTH, min(MAX_LENGTH, length))

    def to_dict(self) -> dict[str, Any]:
        return dict(vars(self))

    @classmethod
    def from_dict(cls, data: object) -> Options:
        opts = cls()
        if isinstance(data, dict):
            length = data.get("length")
            if isinstance(length, int):
                opts.set_length(length)
            for name in ("lower", "upper", "digits", "symbols", "avoid_ambiguous"):
                if isinstance(data.get(name), bool):
                    setattr(opts, name, data[name])
        if not opts.sets():
            opts.lower = True
        return opts


def generate(options: Options, rng: random.Random | None = None) -> str:
    """A random password using every enabled set at least once.

    Raises ``ValueError`` if no character set is enabled.
    """
    rng = rng or secrets.SystemRandom()
    sets = options.sets()
    if not sets:
        raise ValueError("choose at least one character set")
    pool = "".join(sets)
    # One from each set (when it fits), the rest from the whole pool, then shuffle.
    chars = [rng.choice(s) for s in sets[: options.length]]
    chars += [rng.choice(pool) for _ in range(options.length - len(chars))]
    rng.shuffle(chars)
    return "".join(chars)


def entropy_bits(options: Options) -> float:
    """Bits of entropy of a password from these options (``0`` with no sets)."""
    size = len(options.pool())
    return options.length * math.log2(size) if size > 1 else 0.0


def strength(bits: float) -> int:
    """0 (very weak) to 4 (very strong); see :data:`STRENGTH_LABELS`."""
    return sum(bits >= b for b in STRENGTH_BITS)


def crack_time(bits: float, guesses_per_second: float = GUESSES_PER_SECOND) -> str:
    """Rough time to try half the possibilities, e.g. ``"3 hours"`` or ``"millions of years"``."""
    seconds = 2 ** (bits - 1) / guesses_per_second
    for unit, size in (
        ("year", 365.25 * 86400),
        ("day", 86400),
        ("hour", 3600),
        ("minute", 60),
        ("second", 1),
    ):
        if seconds >= size:
            count = seconds / size
            if unit == "year" and count >= 1000:
                scale = "billions" if count >= 1e9 else "millions" if count >= 1e6 else "thousands"
                return f"{scale} of years"
            n = round(count)
            return f"{n} {unit}{'s' if n != 1 else ''}"
    return "instantly"


def char_kind(ch: str) -> str:
    """``"letter"``, ``"digit"`` or ``"symbol"``, for colour-coding the display."""
    if ch.isdigit():
        return "digit"
    return "letter" if ch.isalpha() else "symbol"
