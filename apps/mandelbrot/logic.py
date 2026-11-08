"""Escape-time math, views, progressive sample order and palettes. No pygame.

Pure Python is slow per pixel, so the app never computes a frame in one go:
:func:`progressive_samples` yields coarse 8×8 blocks first, then 4×4, 2×2 and
finally single pixels (skipping ones already computed), and the app works
through it for a few milliseconds each frame. A blocky preview appears almost
at once and sharpens while you look. Points inside the main cardioid and the
period-2 bulb are recognised without iterating, and a periodicity check stops
early on other interior points, which are otherwise the slowest to compute.
"""

from __future__ import annotations

import math
from collections.abc import Iterator
from dataclasses import dataclass

RGB = tuple[int, int, int]
INSIDE = -1.0
BAILOUT = 256.0  # a large escape radius makes the smooth colouring smooth
PASSES = (8, 4, 2, 1)
#: Smallest step between pixels before doubles run out of precision.
MIN_SCALE = 2e-14
_LOG2 = math.log(2)


def escape_time(cr: float, ci: float, max_iter: int) -> float:
    """Smoothed iteration count at which ``c`` escapes, or :data:`INSIDE`.

    The fractional part comes from the "normalised iteration count", so the
    colours blend smoothly instead of forming bands.
    """
    # Main cardioid and period-2 bulb: inside, no iteration needed.
    x = cr - 0.25
    q = x * x + ci * ci
    if q * (q + x) <= 0.25 * ci * ci or (cr + 1) * (cr + 1) + ci * ci <= 0.0625:
        return INSIDE
    zr = zi = 0.0
    check_r = check_i = 0.0
    period = 0
    for n in range(max_iter):
        zr2, zi2 = zr * zr, zi * zi
        if zr2 + zi2 > BAILOUT:
            log_zn = math.log(zr2 + zi2) / 2
            return n + 1 - math.log(log_zn / _LOG2) / _LOG2
        zi = 2 * zr * zi + ci
        zr = zr2 - zi2 + cr
        # Periodicity: if z comes back to a saved value, it's on a cycle: inside.
        if abs(zr - check_r) < 1e-13 and abs(zi - check_i) < 1e-13:
            return INSIDE
        period += 1
        if period > 20:
            period = 0
            check_r, check_i = zr, zi
    return INSIDE


@dataclass(frozen=True)
class View:
    """What part of the plane is shown: centre and complex units per pixel."""

    cx: float = -0.6
    cy: float = 0.0
    scale: float = 3.2 / 880

    def to_complex(self, x: float, y: float, width: int, height: int) -> tuple[float, float]:
        """The point under pixel ``(x, y)`` (pixel centres at ``+0.5``)."""
        return (
            self.cx + (x + 0.5 - width / 2) * self.scale,
            self.cy - (y + 0.5 - height / 2) * self.scale,
        )

    def zoom(self, factor: float, x: float, y: float, width: int, height: int) -> View:
        """Zoom by ``factor`` (>1 zooms in) keeping the point under ``(x, y)`` still."""
        scale = max(MIN_SCALE, min(0.05, self.scale / factor))
        pr, pi = self.to_complex(x, y, width, height)
        ratio = scale / self.scale
        return View(pr + (self.cx - pr) * ratio, pi + (self.cy - pi) * ratio, scale)

    def pan(self, dx: float, dy: float) -> View:
        """Move the picture by ``(dx, dy)`` pixels (as when dragging it)."""
        return View(self.cx - dx * self.scale, self.cy + dy * self.scale, self.scale)

    def magnification(self, default: View | None = None) -> float:
        return (default or View()).scale / self.scale

    @property
    def at_limit(self) -> bool:
        return self.scale <= MIN_SCALE * 1.0001


def suggested_iterations(view: View, base: int = 120) -> int:
    """Deeper zooms need more iterations to show detail: about +60 per tenfold zoom."""
    zoom = max(1.0, view.magnification())
    return int(base + 60 * math.log10(zoom))


def progressive_samples(width: int, height: int) -> Iterator[tuple[int, int, int]]:
    """Every pixel exactly once as ``(x, y, block)``, coarse passes first.

    ``block`` is the size of the square the sample should paint for now; later,
    finer passes overwrite the parts of it that differ.
    """
    for i, block in enumerate(PASSES):
        coarser = PASSES[i - 1] if i else 0
        for y in range(0, height, block):
            for x in range(0, width, block):
                if coarser and x % coarser == 0 and y % coarser == 0:
                    continue  # computed in an earlier pass
                yield x, y, block


@dataclass(frozen=True)
class Palette:
    name: str
    stops: tuple[RGB, ...]
    inside: RGB = (0, 0, 0)
    period: float = 48.0  # iterations per full cycle through the stops


PALETTES: tuple[Palette, ...] = (
    Palette(
        "Twilight",
        (
            (12, 7, 50),
            (68, 33, 140),
            (196, 74, 140),
            (250, 170, 90),
            (255, 245, 210),
            (40, 90, 170),
        ),
    ),
    Palette(
        "Fire",
        ((10, 0, 0), (120, 10, 0), (230, 80, 0), (255, 200, 40), (255, 255, 220), (90, 20, 0)),
    ),
    Palette("Ocean", ((2, 12, 40), (0, 70, 120), (0, 160, 180), (170, 240, 230), (10, 60, 110))),
    Palette("Mono", ((0, 0, 0), (255, 255, 255)), inside=(0, 0, 0), period=64.0),
)


def colour(value: float, palette: Palette) -> RGB:
    """The colour for an :func:`escape_time` result."""
    if value < 0:
        return palette.inside
    stops = palette.stops
    t = (math.sqrt(value) * 6 / math.sqrt(palette.period)) % 1 * len(stops)
    i = int(t)
    f = t - i
    a, b = stops[i % len(stops)], stops[(i + 1) % len(stops)]
    return (
        round(a[0] + (b[0] - a[0]) * f),
        round(a[1] + (b[1] - a[1]) * f),
        round(a[2] + (b[2] - a[2]) * f),
    )


@dataclass(frozen=True)
class Place:
    name: str
    view: View


PLACES: tuple[Place, ...] = (
    Place("Whole set", View()),
    Place("Seahorse Valley", View(-0.7453, 0.1127, 0.012 / 880)),
    Place("Elephant Valley", View(0.2925, 0.0164, 0.02 / 880)),
    Place("Spiral", View(-0.743643887037151, 0.131825904205330, 0.00012 / 880)),
    Place("Mini Mandelbrot", View(-1.7686, 0.0017, 0.009 / 880)),
)
