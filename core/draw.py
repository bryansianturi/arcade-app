"""Low-level drawing helpers: rounded rectangles, soft shadows and anchored text."""

from __future__ import annotations

import math
from collections.abc import Callable
from functools import lru_cache
from typing import Literal

import pygame

from core import gfx
from core.canvas import Canvas, Font

Anchor = Literal[
    "topleft",
    "midtop",
    "topright",
    "midleft",
    "center",
    "midright",
    "bottomleft",
    "midbottom",
    "bottomright",
]
RGB = tuple[int, int, int]
RGBA = tuple[int, int, int, int]
#: A vector icon: ``painter(surface, center, color, size)``.
IconPainter = Callable[[Canvas, tuple[int, int], RGB, int], None]
#: Widgets accept either a text glyph (must exist in the font) or a vector painter.
Icon = str | IconPainter


def rounded_rect(
    surface: Canvas,
    rect: pygame.Rect,
    color: RGB | RGBA,
    radius: int,
    width: int = 0,
) -> None:
    """Draw a (filled or outlined) rectangle with rounded corners.

    RGBA colors are alpha-blended onto ``surface``.
    """
    radius = min(radius, rect.width // 2, rect.height // 2)
    if len(color) == 4 and color[3] < 255:
        layer = Canvas.new(rect.size, alpha=True)
        gfx.rect(layer, color, layer.get_rect(), width, border_radius=radius)
        surface.blit(layer, rect.topleft)
    else:
        gfx.rect(surface, color, rect, width, border_radius=radius)


@lru_cache(maxsize=128)
def _shadow_surface(
    size: tuple[int, int], radius: int, blur: int, color: RGBA, scale: float
) -> Canvas:
    """Build (and cache) a blurred rounded-rect shadow."""
    w, h = size
    pad = blur * 2
    base = Canvas.new((w + pad * 2, h + pad * 2), alpha=True, scale=scale)
    gfx.rect(base, color, (pad, pad, w, h), border_radius=radius)
    # Cheap blur: shrink then grow with smoothscale, twice.
    full = base.surface.get_size()
    blurred = base.surface
    for factor in (4, 2):
        small = (max(1, full[0] // factor), max(1, full[1] // factor))
        blurred = pygame.transform.smoothscale(blurred, small)
        blurred = pygame.transform.smoothscale(blurred, full)
    return Canvas(blurred, scale, (base.width, base.height))


@lru_cache(maxsize=16)
def _corner_mask(size: tuple[int, int], radius: int, scale: float) -> Canvas:
    mask = Canvas.new(size, alpha=True, scale=scale)
    gfx.rect(mask, (255, 255, 255, 255), mask.get_rect(), border_radius=radius)
    return mask


def round_corners(layer: Canvas, radius: int) -> Canvas:
    """Return ``layer`` with transparent rounded corners (for playfields drawn offscreen).

    ``layer`` must have been created with ``alpha=True``.
    """
    layer.blit(
        _corner_mask(layer.get_size(), radius, layer.scale),
        (0, 0),
        special_flags=pygame.BLEND_RGBA_MIN,
    )
    return layer


@lru_cache(maxsize=8)
def vertical_gradient(size: tuple[int, int], top: RGB, bottom: RGB, scale: float) -> Canvas:
    """A cached top-to-bottom color gradient. Copy it before drawing on it."""
    strip = pygame.Surface((1, max(1, round(size[1] * scale))), pygame.SRCALPHA)
    rows = strip.get_height()
    for y in range(rows):
        t = y / rows
        strip.set_at(
            (0, y), tuple(round(a + (b - a) * t) for a, b in zip(top, bottom, strict=True))
        )
    full = pygame.transform.scale(strip, (max(1, round(size[0] * scale)), rows))
    return Canvas(full, scale, size)


def shadow(
    surface: Canvas,
    rect: pygame.Rect,
    radius: int,
    color: RGBA,
    offset: tuple[int, int] = (0, 6),
    blur: int = 12,
) -> None:
    """Draw a soft drop shadow under ``rect``."""
    if color[3] <= 0:
        return
    shadow_img = _shadow_surface(rect.size, radius, blur, color, surface.scale)
    pad = blur * 2
    surface.blit(shadow_img, (rect.x - pad + offset[0], rect.y - pad + offset[1]))


def text(
    surface: Canvas,
    content: str,
    font: Font,
    color: RGB | RGBA,
    pos: tuple[float, float],
    anchor: Anchor = "topleft",
) -> pygame.Rect:
    """Render ``content`` and blit it anchored at ``pos``. Returns the drawn rect.

    Anchoring uses the exact (fractional) text size, so centred text stays centred
    at any render scale.
    """
    image = font.render(content, True, color)
    if len(color) == 4:
        image.set_alpha(color[3])
    frect = pygame.FRect(0, 0, image.width, image.height)
    setattr(frect, anchor, pos)
    surface.blit(image, frect.topleft)
    return pygame.Rect(round(frect.x), round(frect.y), round(frect.width), round(frect.height))


def fit_text(content: str, font: Font, max_width: int) -> str:
    """Truncate ``content`` with an ellipsis so it renders within ``max_width``."""
    if font.size(content)[0] <= max_width:
        return content
    ellipsis = "…"
    while content and font.size(content + ellipsis)[0] > max_width:
        content = content[:-1]
    return content.rstrip() + ellipsis


def wrap_text(content: str, font: Font, max_width: int) -> list[str]:
    """Greedy word-wrap ``content`` into lines no wider than ``max_width``."""
    lines: list[str] = []
    for paragraph in content.split("\n"):
        line = ""
        for word in paragraph.split(" "):
            candidate = f"{line} {word}".strip()
            if font.size(candidate)[0] <= max_width or not line:
                line = candidate
            else:
                lines.append(line)
                line = word
        lines.append(line)
    return lines


def overlay(surface: Canvas, color: RGBA) -> None:
    """Fill the whole surface with a translucent color (e.g. to dim behind a modal)."""
    layer = Canvas.new(surface.get_size(), alpha=True)
    layer.fill(color)
    surface.blit(layer, (0, 0))


def search_icon(surface: Canvas, center: tuple[int, int], color: RGB, size: int = 16) -> None:
    """A magnifying glass drawn with shapes (fonts rarely include a nice one)."""
    r = size * 0.33
    cx, cy = center[0] - size * 0.12, center[1] - size * 0.12
    gfx.circle(surface, color, (round(cx), round(cy)), round(r), 2)
    start = (round(cx + r * 0.72), round(cy + r * 0.72))
    end = (round(center[0] + size * 0.42), round(center[1] + size * 0.42))
    gfx.line(surface, color, start, end, 3)


def gear_icon(surface: Canvas, center: tuple[int, int], color: RGB, size: int = 16) -> None:
    """A simple cog: a ring with eight teeth."""
    cx, cy = center
    outer, inner = size * 0.5, size * 0.34
    for i in range(8):
        a = i * math.pi / 4
        gfx.line(
            surface,
            color,
            (round(cx + math.cos(a) * inner), round(cy + math.sin(a) * inner)),
            (round(cx + math.cos(a) * outer), round(cy + math.sin(a) * outer)),
            3,
        )
    gfx.circle(surface, color, center, round(inner), 3)


def star_icon(surface: Canvas, center: tuple[int, int], color: RGB, size: int = 16) -> None:
    """A filled five-pointed star."""
    outer, inner = size * 0.5, size * 0.21
    c = pygame.Vector2(center)
    points = [
        c + pygame.Vector2(0, -(outer if i % 2 == 0 else inner)).rotate(i * 36) for i in range(10)
    ]
    gfx.polygon(surface, color, points)


def star_outline_icon(surface: Canvas, center: tuple[int, int], color: RGB, size: int = 16) -> None:
    """An outlined five-pointed star (e.g. "not a favorite")."""
    outer, inner = size * 0.5, size * 0.21
    c = pygame.Vector2(center)
    points = [
        c + pygame.Vector2(0, -(outer if i % 2 == 0 else inner)).rotate(i * 36) for i in range(10)
    ]
    gfx.polygon(surface, color, points, 1.5)


def camera_icon(surface: Canvas, center: tuple[int, int], color: RGB, size: int = 16) -> None:
    """A simple camera: body, lens and viewfinder bump."""
    cx, cy = center
    body = pygame.FRect(0, 0, size * 0.9, size * 0.62)
    body.center = (cx, cy + size * 0.06)
    bump = pygame.FRect(0, 0, size * 0.32, size * 0.16)
    bump.midbottom = (cx - size * 0.12, body.top + 1)
    gfx.rect(surface, color, bump, border_radius=size * 0.05)
    gfx.rect(surface, color, body, 2, border_radius=size * 0.12)
    gfx.circle(surface, color, body.center, size * 0.17, 2)


def lock_icon(surface: Canvas, center: tuple[int, int], color: RGB, size: int = 16) -> None:
    """A padlock."""
    cx, cy = center
    body = pygame.FRect(0, 0, size * 0.7, size * 0.5)
    body.midtop = (cx, cy - size * 0.05)
    shackle = pygame.FRect(0, 0, size * 0.44, size * 0.6)
    shackle.midbottom = (cx, body.top + size * 0.18)
    gfx.rect(surface, color, shackle, max(1.5, size * 0.1), border_radius=size * 0.22)
    gfx.rect(surface, color, body, border_radius=size * 0.1)


def trophy_icon(surface: Canvas, center: tuple[int, int], color: RGB, size: int = 16) -> None:
    """A trophy cup on a base."""
    cx, cy = center
    cup = pygame.FRect(0, 0, size * 0.56, size * 0.5)
    cup.midtop = (cx, cy - size * 0.45)
    gfx.rect(surface, color, cup, border_radius=size * 0.2)
    for side in (-1, 1):  # handles
        handle = pygame.FRect(0, 0, size * 0.26, size * 0.26)
        handle.center = (cx + side * size * 0.3, cup.top + size * 0.15)
        gfx.rect(surface, color, handle, max(1.5, size * 0.08), border_radius=size * 0.13)
    gfx.rect(surface, color, (cx - size * 0.05, cup.bottom - 1, size * 0.1, size * 0.18))
    gfx.rect(
        surface,
        color,
        (cx - size * 0.24, cup.bottom + size * 0.16, size * 0.48, size * 0.12),
        border_radius=size * 0.04,
    )


def chart_icon(surface: Canvas, center: tuple[int, int], color: RGB, size: int = 16) -> None:
    """Three bars of a bar chart."""
    cx, cy = center
    w = size * 0.2
    for i, h in enumerate((0.45, 0.85, 0.65)):
        x = cx - size * 0.4 + i * size * 0.3
        gfx.rect(
            surface, color, (x, cy + size * 0.42 - size * h, w, size * h), border_radius=w * 0.3
        )


def icon_width(icon: Icon, font: Font) -> int:
    """Horizontal space an icon occupies when drawn next to text in ``font``."""
    return font.size(icon)[0] if isinstance(icon, str) else font.get_height()


def draw_icon(
    surface: Canvas,
    icon: Icon,
    font: Font,
    color: RGB,
    midleft: tuple[int, int],
) -> int:
    """Draw ``icon`` with its left edge at ``midleft``. Returns the x just past it."""
    if isinstance(icon, str):
        return text(surface, icon, font, color, midleft, "midleft").right
    size = font.get_height()
    icon(surface, (midleft[0] + size // 2, midleft[1]), color, round(size * 0.8))
    return midleft[0] + size


def thick_line(
    surface: Canvas,
    color: RGB,
    start: tuple[float, float] | pygame.Vector2,
    end: tuple[float, float] | pygame.Vector2,
    width: float,
) -> None:
    """A line of constant ``width`` at any angle, with round caps.

    ``gfx.line`` makes diagonal thick lines thinner than straight ones;
    this draws the body as a polygon instead.
    """
    a = pygame.Vector2(start)
    b = pygame.Vector2(end)
    radius = width / 2
    if (b - a).length_squared() > 0:
        normal = (b - a).normalize().rotate(90) * radius
        gfx.polygon(surface, color, [a + normal, b + normal, b - normal, a - normal])
    gfx.circle(surface, color, a, radius)
    gfx.circle(surface, color, b, radius)


def ring_arc(
    surface: Canvas,
    color: RGB,
    center: tuple[float, float],
    radius: float,
    width: float,
    fraction: float,
    start_deg: float = -90,
) -> None:
    """A thick, round-capped arc covering ``fraction`` (0..1) of a circle, clockwise.

    Used for progress rings. ``start_deg`` -90 starts at 12 o'clock.
    """
    fraction = max(0.0, min(1.0, fraction))
    if fraction <= 0:
        return
    c = pygame.Vector2(center)
    mid = radius - width / 2
    steps = max(2, int(120 * fraction))
    outer, inner = [], []
    for i in range(steps + 1):
        angle = start_deg + 360 * fraction * i / steps
        direction = pygame.Vector2(1, 0).rotate(angle)
        outer.append(c + direction * radius)
        inner.append(c + direction * (radius - width))
    gfx.polygon(surface, color, outer + inner[::-1])
    for angle in (start_deg, start_deg + 360 * fraction):  # round caps
        gfx.circle(surface, color, c + pygame.Vector2(mid, 0).rotate(angle), width / 2)
