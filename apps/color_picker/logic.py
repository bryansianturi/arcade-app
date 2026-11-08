"""Color conversions, color harmonies and contrast. No pygame.

Colors are ``(r, g, b)`` tuples of ints 0–255. The picker keeps its state as
HSV floats (:class:`HSV`) so the hue survives passing through grey, where RGB
alone would lose it.
"""

from __future__ import annotations

import colorsys
import random
import string
from dataclasses import dataclass
from typing import Literal

RGB = tuple[int, int, int]
HEX_DIGITS = frozenset(string.hexdigits)

Harmony = Literal["complementary", "analogous", "triadic", "split", "square", "shades"]
HARMONIES: tuple[Harmony, ...] = (
    "complementary",
    "analogous",
    "triadic",
    "split",
    "square",
    "shades",
)
HARMONY_NAMES: dict[Harmony, str] = {
    "complementary": "Complement",
    "analogous": "Analogous",
    "triadic": "Triadic",
    "split": "Split",
    "square": "Square",
    "shades": "Shades",
}

#: Each harmony as five (hue offset in degrees, saturation ×, value ×) recipes.
_RECIPES: dict[Harmony, tuple[tuple[float, float, float], ...]] = {
    "complementary": ((0, 1, 1), (0, 0.45, 1), (180, 1, 1), (180, 0.45, 1), (180, 1, 0.6)),
    "analogous": ((-40, 1, 1), (-20, 1, 1), (0, 1, 1), (20, 1, 1), (40, 1, 1)),
    "triadic": ((0, 1, 1), (120, 1, 1), (240, 1, 1), (0, 0.4, 1), (120, 1, 0.6)),
    "split": ((0, 1, 1), (150, 1, 1), (210, 1, 1), (0, 0.4, 1), (0, 1, 0.6)),
    "square": ((0, 1, 1), (90, 1, 1), (180, 1, 1), (270, 1, 1), (0, 0.4, 1)),
    "shades": ((0, 0.35, 1), (0, 0.7, 1), (0, 1, 1), (0, 1, 0.7), (0, 1, 0.4)),
}


@dataclass(frozen=True)
class HSV:
    """Hue in degrees [0, 360), saturation and value in [0, 1]."""

    h: float
    s: float
    v: float

    def clamped(self) -> HSV:
        return HSV(self.h % 360, min(1.0, max(0.0, self.s)), min(1.0, max(0.0, self.v)))

    def to_rgb(self) -> RGB:
        r, g, b = colorsys.hsv_to_rgb(self.h % 360 / 360, self.s, self.v)
        return round(r * 255), round(g * 255), round(b * 255)

    @classmethod
    def from_rgb(cls, rgb: RGB, keep_hue: float = 0.0) -> HSV:
        """Convert, keeping ``keep_hue`` for greys (which have no hue of their own)."""
        h, s, v = colorsys.rgb_to_hsv(*(c / 255 for c in rgb))
        return cls(h * 360 if s > 0 else keep_hue, s, v)


def to_hex(rgb: RGB) -> str:
    return "#{:02X}{:02X}{:02X}".format(*rgb)


def parse_hex(text: str) -> RGB | None:
    """``"#1e90ff"``, ``"1E90FF"`` or short ``"#19f"`` → RGB; anything else → ``None``."""
    text = text.strip().removeprefix("#")
    if len(text) == 3:
        text = "".join(c * 2 for c in text)
    if len(text) != 6 or not all(c in HEX_DIGITS for c in text):
        return None  # int(..., 16) alone would also accept "-1_234"
    value = int(text, 16)
    return (value >> 16) & 255, (value >> 8) & 255, value & 255


def rgb_text(rgb: RGB) -> str:
    return "rgb({}, {}, {})".format(*rgb)


def hsl_text(rgb: RGB) -> str:
    h, light, s = colorsys.rgb_to_hls(*(c / 255 for c in rgb))
    return f"hsl({round(h * 360) % 360}, {round(s * 100)}%, {round(light * 100)}%)"


def palette(base: HSV, harmony: Harmony) -> list[RGB]:
    """Five colors in ``harmony`` with ``base``, built on the HSV color wheel."""
    return [
        HSV(base.h + dh, base.s * s_mul, base.v * v_mul).clamped().to_rgb()
        for dh, s_mul, v_mul in _RECIPES[harmony]
    ]


def random_color(rng: random.Random) -> HSV:
    """A pleasant random color: any hue, fairly saturated, not too dark."""
    return HSV(rng.uniform(0, 360), rng.uniform(0.45, 0.95), rng.uniform(0.6, 1.0))


def luminance(rgb: RGB) -> float:
    """WCAG relative luminance, 0 (black) to 1 (white)."""

    def channel(c: int) -> float:
        x = c / 255
        return x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: RGB, b: RGB) -> float:
    """WCAG contrast ratio, 1 to 21."""
    hi, lo = sorted((luminance(a), luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def wcag_grade(ratio: float) -> str:
    """``"AAA"``, ``"AA"``, ``"AA large"`` or ``"Fail"`` for body text."""
    if ratio >= 7:
        return "AAA"
    if ratio >= 4.5:
        return "AA"
    return "AA large" if ratio >= 3 else "Fail"
