"""``pygame.draw`` for :class:`~core.canvas.Canvas`: same names and arguments, logical units.

Circles are anti-aliased; everything else matches ``pygame.draw`` exactly but is
rasterised at the canvas's native resolution.
"""

from __future__ import annotations

from collections.abc import Iterable

import pygame

from core.canvas import Canvas, ColorLike, Point, RectLike


def rect(
    canvas: Canvas, color: ColorLike, rect: RectLike, width: float = 0, border_radius: float = 0
) -> None:
    radius = canvas.px(border_radius) if border_radius > 0 else -1
    pygame.draw.rect(
        canvas.surface, color, canvas.px_rect(rect), canvas.px_width(width), border_radius=radius
    )


def circle(
    canvas: Canvas, color: ColorLike, center: Point, radius: float, width: float = 0
) -> None:
    r = radius * canvas.scale
    if r < 0.5:
        return
    pygame.draw.aacircle(canvas.surface, color, canvas.px_point(center), r, canvas.px_width(width))


def ellipse(canvas: Canvas, color: ColorLike, rect: RectLike, width: float = 0) -> None:
    pygame.draw.ellipse(canvas.surface, color, canvas.px_rect(rect), canvas.px_width(width))


def arc(
    canvas: Canvas,
    color: ColorLike,
    rect: RectLike,
    start_angle: float,
    stop_angle: float,
    width: float = 1,
) -> None:
    pygame.draw.arc(
        canvas.surface,
        color,
        canvas.px_rect(rect),
        start_angle,
        stop_angle,
        canvas.px_width(width),
    )


def line(canvas: Canvas, color: ColorLike, start: Point, end: Point, width: float = 1) -> None:
    pygame.draw.line(
        canvas.surface,
        color,
        canvas.px_point(start),
        canvas.px_point(end),
        canvas.px_width(width),
    )


def lines(
    canvas: Canvas, color: ColorLike, closed: bool, points: Iterable[Point], width: float = 1
) -> None:
    pygame.draw.lines(
        canvas.surface,
        color,
        closed,
        [canvas.px_point(p) for p in points],
        canvas.px_width(width),
    )


def polygon(canvas: Canvas, color: ColorLike, points: Iterable[Point], width: float = 0) -> None:
    pygame.draw.polygon(
        canvas.surface, color, [canvas.px_point(p) for p in points], canvas.px_width(width)
    )
