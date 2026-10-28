"""Low-level drawing helpers: rounded rectangles, soft shadows and anchored text."""

from __future__ import annotations

import math
from collections.abc import Callable
from functools import lru_cache
from typing import Literal

import pygame

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
IconPainter = Callable[[pygame.Surface, tuple[int, int], RGB, int], None]
#: Widgets accept either a text glyph (must exist in the font) or a vector painter.
Icon = str | IconPainter


def rounded_rect(
    surface: pygame.Surface,
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
        layer = pygame.Surface(rect.size, pygame.SRCALPHA)
        pygame.draw.rect(layer, color, layer.get_rect(), width, border_radius=radius)
        surface.blit(layer, rect.topleft)
    else:
        pygame.draw.rect(surface, color, rect, width, border_radius=radius)


@lru_cache(maxsize=128)
def _shadow_surface(size: tuple[int, int], radius: int, blur: int, color: RGBA) -> pygame.Surface:
    """Build (and cache) a blurred rounded-rect shadow."""
    w, h = size
    pad = blur * 2
    base = pygame.Surface((w + pad * 2, h + pad * 2), pygame.SRCALPHA)
    pygame.draw.rect(base, color, (pad, pad, w, h), border_radius=radius)
    # Cheap blur: shrink then grow with smoothscale, twice.
    blurred = base
    for factor in (4, 2):
        small = (max(1, blurred.get_width() // factor), max(1, blurred.get_height() // factor))
        blurred = pygame.transform.smoothscale(blurred, small)
        blurred = pygame.transform.smoothscale(blurred, base.get_size())
    return blurred


def shadow(
    surface: pygame.Surface,
    rect: pygame.Rect,
    radius: int,
    color: RGBA,
    offset: tuple[int, int] = (0, 6),
    blur: int = 12,
) -> None:
    """Draw a soft drop shadow under ``rect``."""
    if color[3] <= 0:
        return
    shadow_img = _shadow_surface(rect.size, radius, blur, color)
    pad = blur * 2
    surface.blit(shadow_img, (rect.x - pad + offset[0], rect.y - pad + offset[1]))


def text(
    surface: pygame.Surface,
    content: str,
    font: pygame.font.Font,
    color: RGB | RGBA,
    pos: tuple[int, int],
    anchor: Anchor = "topleft",
) -> pygame.Rect:
    """Render ``content`` and blit it anchored at ``pos``. Returns the drawn rect."""
    image = font.render(content, True, color)
    if len(color) == 4:
        image.set_alpha(color[3])
    rect = image.get_rect(**{anchor: pos})
    surface.blit(image, rect)
    return rect


def fit_text(content: str, font: pygame.font.Font, max_width: int) -> str:
    """Truncate ``content`` with an ellipsis so it renders within ``max_width``."""
    if font.size(content)[0] <= max_width:
        return content
    ellipsis = "…"
    while content and font.size(content + ellipsis)[0] > max_width:
        content = content[:-1]
    return content.rstrip() + ellipsis


def wrap_text(content: str, font: pygame.font.Font, max_width: int) -> list[str]:
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


def overlay(surface: pygame.Surface, color: RGBA) -> None:
    """Fill the whole surface with a translucent color (e.g. to dim behind a modal)."""
    layer = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
    layer.fill(color)
    surface.blit(layer, (0, 0))


def search_icon(
    surface: pygame.Surface, center: tuple[int, int], color: RGB, size: int = 16
) -> None:
    """A magnifying glass drawn with shapes (fonts rarely include a nice one)."""
    r = size * 0.33
    cx, cy = center[0] - size * 0.12, center[1] - size * 0.12
    pygame.draw.circle(surface, color, (round(cx), round(cy)), round(r), 2)
    start = (round(cx + r * 0.72), round(cy + r * 0.72))
    end = (round(center[0] + size * 0.42), round(center[1] + size * 0.42))
    pygame.draw.line(surface, color, start, end, 3)


def gear_icon(surface: pygame.Surface, center: tuple[int, int], color: RGB, size: int = 16) -> None:
    """A simple cog: a ring with eight teeth."""
    cx, cy = center
    outer, inner = size * 0.5, size * 0.34
    for i in range(8):
        a = i * math.pi / 4
        pygame.draw.line(
            surface,
            color,
            (round(cx + math.cos(a) * inner), round(cy + math.sin(a) * inner)),
            (round(cx + math.cos(a) * outer), round(cy + math.sin(a) * outer)),
            3,
        )
    pygame.draw.circle(surface, color, center, round(inner), 3)


def icon_width(icon: Icon, font: pygame.font.Font) -> int:
    """Horizontal space an icon occupies when drawn next to text in ``font``."""
    return font.size(icon)[0] if isinstance(icon, str) else font.get_height()


def draw_icon(
    surface: pygame.Surface,
    icon: Icon,
    font: pygame.font.Font,
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
    surface: pygame.Surface,
    color: RGB,
    start: tuple[float, float] | pygame.Vector2,
    end: tuple[float, float] | pygame.Vector2,
    width: float,
) -> None:
    """A line of constant ``width`` at any angle, with round caps.

    ``pygame.draw.line`` makes diagonal thick lines thinner than straight ones;
    this draws the body as a polygon instead.
    """
    a = pygame.Vector2(start)
    b = pygame.Vector2(end)
    radius = width / 2
    if (b - a).length_squared() > 0:
        normal = (b - a).normalize().rotate(90) * radius
        pygame.draw.polygon(surface, color, [a + normal, b + normal, b - normal, a - normal])
    pygame.draw.circle(surface, color, a, radius)
    pygame.draw.circle(surface, color, b, radius)
