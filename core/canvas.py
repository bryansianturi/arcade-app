"""Resolution-independent drawing: logical coordinates, native-resolution pixels.

Apps and screens lay everything out on a fixed 1280×720 *logical* canvas, but
the window is drawn at the display's real pixel density (2× on a Retina Mac, or
any fractional factor once the window is resized). A :class:`Canvas` pairs a
pygame surface with that *scale*: positions, sizes and line widths given to it
are logical pixels and are converted only when something is rasterised, so text
and shapes stay crisp instead of being drawn small and stretched afterwards.

* :class:`Canvas` mirrors the parts of ``pygame.Surface`` the code base uses.
* ``core.gfx`` mirrors ``pygame.draw`` for canvases.
* :class:`Font` mirrors ``pygame.font.Font`` with metrics in logical pixels.

The current scale is process-wide (there is one window); :mod:`core.display`
updates it whenever the window changes size. Tests and headless runs use 1.0.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

import pygame

Point = tuple[float, float] | Sequence[float] | pygame.Vector2
RectLike = pygame.Rect | pygame.FRect | tuple[float, float, float, float] | Sequence[float]
ColorLike = tuple[int, int, int] | tuple[int, int, int, int] | Sequence[int] | pygame.Color

_EPS = 1e-6


@dataclass(frozen=True)
class Viewport:
    """Where the logical canvas sits inside the window, for mapping mouse input."""

    scale: float = 1.0  # physical pixels per logical pixel
    offset: tuple[int, int] = (0, 0)  # letterbox offset, physical pixels
    pixel_ratio: float = 1.0  # physical pixels per window coordinate (2 on Retina)


_viewport = Viewport()


def render_scale() -> float:
    """Physical pixels per logical pixel for everything drawn this frame."""
    return _viewport.scale


def set_viewport(viewport: Viewport) -> None:
    global _viewport
    _viewport = viewport


def viewport() -> Viewport:
    return _viewport


def to_logical(pos: tuple[float, float]) -> tuple[int, int]:
    """Convert a window (mouse) coordinate to a logical canvas coordinate."""
    v = _viewport
    x = (pos[0] * v.pixel_ratio - v.offset[0]) / v.scale
    y = (pos[1] * v.pixel_ratio - v.offset[1]) / v.scale
    return math.floor(x), math.floor(y)


def mouse_pos() -> tuple[int, int]:
    """``pygame.mouse.get_pos()`` in logical coordinates."""
    return to_logical(pygame.mouse.get_pos())


def _ceil(value: float) -> int:
    return math.ceil(value - _EPS)


class Canvas:
    """A drawing surface addressed in logical pixels."""

    __slots__ = ("_clip", "height", "scale", "surface", "width")

    def __init__(
        self,
        surface: pygame.Surface,
        scale: float = 1.0,
        size: tuple[float, float] | None = None,
    ) -> None:
        self.surface = surface
        self.scale = scale
        w, h = (
            size
            if size is not None
            else (surface.get_width() / scale, surface.get_height() / scale)
        )
        #: Logical size; may be fractional for rendered text.
        self.width: float = w
        self.height: float = h
        self._clip: pygame.Rect | None = None

    @classmethod
    def new(
        cls, size: tuple[float, float], *, alpha: bool = False, scale: float | None = None
    ) -> Canvas:
        """An offscreen canvas of logical ``size`` (like ``pygame.Surface(size)``)."""
        s = render_scale() if scale is None else scale
        px = (max(1, _ceil(size[0] * s)), max(1, _ceil(size[1] * s)))
        surface = pygame.Surface(px, pygame.SRCALPHA if alpha else 0)
        return cls(surface, s, (size[0], size[1]))

    # ------------------------------------------------------------------ conversion
    def px(self, value: float) -> int:
        """A logical length in physical pixels."""
        return round(value * self.scale)

    def px_width(self, width: float) -> int:
        """A line width in physical pixels; 0 (filled) stays 0, thin lines stay visible."""
        return 0 if width <= 0 else max(1, round(width * self.scale))

    def px_point(self, point: Point) -> tuple[int, int]:
        return round(point[0] * self.scale), round(point[1] * self.scale)

    def px_rect(self, rect: RectLike) -> pygame.Rect:
        """A logical rect in physical pixels. Edges are rounded, so neighbours stay flush."""
        r = pygame.FRect(rect)
        s = self.scale
        left, top = round(r.left * s), round(r.top * s)
        return pygame.Rect(left, top, round(r.right * s) - left, round(r.bottom * s) - top)

    # ------------------------------------------------------------------ Surface API
    def get_size(self) -> tuple[int, int]:
        return round(self.width), round(self.height)

    def get_width(self) -> int:
        return round(self.width)

    def get_height(self) -> int:
        return round(self.height)

    def get_rect(self, **kwargs: Any) -> pygame.Rect:
        rect = pygame.Rect((0, 0), self.get_size())
        for name, value in kwargs.items():
            setattr(rect, name, value)
        return rect

    def fill(self, color: ColorLike, rect: RectLike | None = None, special_flags: int = 0) -> None:
        area = None if rect is None else self.px_rect(rect)
        self.surface.fill(color, area, special_flags)

    def blit(
        self,
        source: Canvas,
        dest: Point | RectLike,
        area: RectLike | None = None,
        special_flags: int = 0,
    ) -> None:
        """Blit ``source`` with its top-left at logical ``dest`` (a point or a rect)."""
        image = source.surface
        src_area = None if area is None else source.px_rect(area)
        if abs(source.scale - self.scale) > _EPS:
            # Drawn at another scale (e.g. a snapshot taken before a resize).
            if src_area is not None:
                image = image.subsurface(src_area.clip(image.get_rect()))
                src_area = None
            factor = self.scale / source.scale
            image = pygame.transform.smoothscale_by(image, factor)
        self.surface.blit(image, self.px_point((dest[0], dest[1])), src_area, special_flags)

    def set_alpha(self, value: int | None) -> None:
        self.surface.set_alpha(value)

    def get_clip(self) -> pygame.Rect:
        """The logical clip rect (exactly what was last passed to :meth:`set_clip`)."""
        return self._clip.copy() if self._clip is not None else self.get_rect()

    def set_clip(self, rect: RectLike | None) -> None:
        if rect is None or pygame.Rect(rect) == self.get_rect():
            self._clip = None
            self.surface.set_clip(None)
        else:
            self._clip = pygame.Rect(rect)
            self.surface.set_clip(self.px_rect(self._clip))

    def scaled(self, factor: float) -> Canvas:
        """A smoothly resized copy (``pygame.transform.smoothscale_by``)."""
        image = pygame.transform.smoothscale_by(self.surface, factor)
        return Canvas(image, self.scale, (self.width * factor, self.height * factor))

    def copy(self) -> Canvas:
        return Canvas(self.surface.copy(), self.scale, (self.width, self.height))


class Font:
    """A font with logical-pixel metrics that renders at the current scale.

    The underlying ``pygame.font.Font`` is loaded at ``size × scale`` pixels, so
    text is rasterised natively rather than scaled. Safe to keep across resizes.
    """

    def __init__(self, loader: Callable[[int], pygame.font.Font], size: int) -> None:
        self._loader = loader
        self.point_size = size
        self._by_px: dict[int, pygame.font.Font] = {}

    def _native(self) -> tuple[pygame.font.Font, float]:
        scale = render_scale()
        px = max(1, round(self.point_size * scale))
        font = self._by_px.get(px)
        if font is None:
            font = self._by_px[px] = self._loader(px)
        return font, scale

    def size(self, text: str) -> tuple[int, int]:
        """Logical (width, height) of ``text``, rounded up so it always fits."""
        font, scale = self._native()
        w, h = font.size(text)
        return _ceil(w / scale), _ceil(h / scale)

    def get_height(self) -> int:
        font, scale = self._native()
        return _ceil(font.get_height() / scale)

    def get_linesize(self) -> int:
        font, scale = self._native()
        return _ceil(font.get_linesize() / scale)

    def render(
        self,
        text: str,
        antialias: bool,
        color: ColorLike,
        background: ColorLike | None = None,
    ) -> Canvas:
        font, scale = self._native()
        return Canvas(font.render(text, antialias, color, background), scale)
