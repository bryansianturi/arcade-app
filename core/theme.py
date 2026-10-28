"""Design tokens shared by every screen and app: colors, fonts, spacing and radii.

Apps should take colors from ``theme.palette`` instead of hard-coding them so
that switching between dark and light mode just works. The :class:`Theme`
object is shared and mutated in place when the mode changes, so holding a
reference to it is always safe.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import partial
from typing import Literal

import pygame

from core.canvas import Font
from core.paths import FONTS_DIR

log = logging.getLogger(__name__)

Color = tuple[int, int, int]
Weight = Literal["regular", "medium", "semibold", "bold"]

FONT_FILES: dict[Weight, str] = {
    "regular": "Inter-Regular.ttf",
    "medium": "Inter-Medium.ttf",
    "semibold": "Inter-SemiBold.ttf",
    "bold": "Inter-Bold.ttf",
}
#: Tried in order by ``pygame.font.SysFont`` when the bundled font is missing.
FALLBACK_FONTS = "inter,segoeui,helveticaneue,helvetica,arial,dejavusans,sans"


@dataclass(frozen=True)
class Palette:
    """Semantic color roles. Name colors by purpose, not by hue."""

    bg: Color  # window background
    surface: Color  # cards, panels
    surface_alt: Color  # inputs, secondary buttons, hovered rows
    surface_hover: Color
    border: Color
    text: Color
    text_muted: Color
    text_on_accent: Color
    primary: Color  # default accent for buttons and focus rings
    success: Color
    warning: Color
    danger: Color
    shadow: tuple[int, int, int, int]  # RGBA; alpha controls shadow strength
    overlay: tuple[int, int, int, int]  # dim layer behind modals


DARK = Palette(
    bg=(15, 17, 23),
    surface=(26, 29, 38),
    surface_alt=(36, 40, 52),
    surface_hover=(44, 49, 63),
    border=(52, 57, 72),
    text=(236, 238, 243),
    text_muted=(145, 152, 170),
    text_on_accent=(255, 255, 255),
    primary=(99, 132, 255),
    success=(52, 199, 123),
    warning=(255, 184, 76),
    danger=(255, 92, 102),
    shadow=(0, 0, 0, 120),
    overlay=(8, 9, 13, 170),
)

LIGHT = Palette(
    bg=(243, 244, 248),
    surface=(255, 255, 255),
    surface_alt=(234, 236, 242),
    surface_hover=(224, 227, 236),
    border=(214, 218, 228),
    text=(22, 25, 34),
    text_muted=(98, 106, 124),
    text_on_accent=(255, 255, 255),
    primary=(70, 104, 240),
    success=(30, 160, 95),
    warning=(214, 140, 20),
    danger=(222, 60, 72),
    shadow=(30, 40, 70, 55),
    overlay=(20, 24, 36, 110),
)


@dataclass(frozen=True)
class Spacing:
    """A 4px-based spacing scale."""

    xs: int = 4
    sm: int = 8
    md: int = 16
    lg: int = 24
    xl: int = 32
    xxl: int = 48


@dataclass(frozen=True)
class Radius:
    sm: int = 6
    md: int = 10
    lg: int = 16
    pill: int = 999


@dataclass(frozen=True)
class TypeScale:
    """Font sizes in logical pixels."""

    caption: int = 13
    body: int = 16
    label: int = 15
    title: int = 22
    heading: int = 30
    display: int = 44


class Theme:
    """Holds the active palette plus spacing, radius and font helpers."""

    def __init__(self, mode: Literal["dark", "light"] = "dark") -> None:
        self.mode: Literal["dark", "light"] = mode
        self.palette: Palette = DARK if mode == "dark" else LIGHT
        self.space = Spacing()
        self.radius = Radius()
        self.size = TypeScale()
        self._fonts: dict[tuple[int, Weight], Font] = {}
        self._warned_fallback = False

    def set_mode(self, mode: Literal["dark", "light"]) -> None:
        """Switch between the dark and light palettes."""
        self.mode = mode
        self.palette = DARK if mode == "dark" else LIGHT

    def font(self, size: int, weight: Weight = "regular") -> Font:
        """Return a cached font of the given logical pixel size and weight."""
        key = (size, weight)
        font = self._fonts.get(key)
        if font is None:
            font = Font(partial(self._load_font, weight=weight), size)
            self._fonts[key] = font
        return font

    def _load_font(self, size: int, weight: Weight) -> pygame.font.Font:
        """Load the real font at ``size`` physical pixels."""
        path = FONTS_DIR / FONT_FILES[weight]
        if path.is_file():
            return pygame.font.Font(path, size)
        if not self._warned_fallback:
            log.info("Bundled font not found in %s; using a system font", FONTS_DIR)
            self._warned_fallback = True
        return pygame.font.SysFont(FALLBACK_FONTS, size, bold=weight in ("semibold", "bold"))


def lerp_color(a: Color, b: Color, t: float) -> Color:
    """Linearly blend two colors; ``t`` is clamped to ``[0, 1]``."""
    t = max(0.0, min(1.0, t))
    return (
        round(a[0] + (b[0] - a[0]) * t),
        round(a[1] + (b[1] - a[1]) * t),
        round(a[2] + (b[2] - a[2]) * t),
    )


def with_alpha(color: Color, alpha: int) -> tuple[int, int, int, int]:
    """Return ``color`` as RGBA."""
    return (color[0], color[1], color[2], alpha)


def readable_on(color: Color) -> Color:
    """Return black or white, whichever reads better on ``color``."""
    r, g, b = color
    luminance = 0.299 * r + 0.587 * g + 0.114 * b
    return (20, 22, 28) if luminance > 170 else (255, 255, 255)
