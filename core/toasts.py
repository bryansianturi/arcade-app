"""Toasts: small notifications drawn above every screen (achievements, screenshots...).

Any code with access to the services can call
``toasts.show("Screenshot saved", "arcade-20260101-120000.png")``. Toasts stack in
the top-right corner, slide in, wait a few seconds and fade out. They never take
input, so they can't interrupt a game.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import pygame

from core import draw
from core.canvas import Canvas
from core.draw import IconPainter
from core.theme import Color, Theme, lerp_color

TOAST_SECONDS = 3.2
SLIDE_SECONDS = 0.25
MAX_VISIBLE = 4
WIDTH = 340
HEIGHT = 64
MARGIN = 20
GAP = 10


@dataclass
class Toast:
    title: str
    message: str = ""
    accent: Color | None = None
    icon: IconPainter | None = None
    duration: float = TOAST_SECONDS
    age: float = 0.0

    @property
    def done(self) -> bool:
        return self.age >= self.duration

    def visibility(self) -> float:
        """0..1: slides in at the start, out at the end."""
        fade_in = min(1.0, self.age / SLIDE_SECONDS)
        fade_out = min(1.0, max(0.0, (self.duration - self.age) / SLIDE_SECONDS))
        return min(fade_in, fade_out)


class ToastService:
    """Queue of visible toasts. Updated and drawn by the main loop."""

    def __init__(self) -> None:
        self.toasts: list[Toast] = []
        self.listeners: list[Callable[[Toast], None]] = []

    def show(
        self,
        title: str,
        message: str = "",
        accent: Color | None = None,
        icon: IconPainter | None = None,
        duration: float = TOAST_SECONDS,
    ) -> Toast:
        toast = Toast(title, message, accent, icon, duration)
        self.toasts.append(toast)
        # Too many at once: the oldest ones leave early.
        for old in self.toasts[:-MAX_VISIBLE]:
            old.age = max(old.age, old.duration - SLIDE_SECONDS)
        for listener in self.listeners:
            listener(toast)
        return toast

    def update(self, dt: float) -> None:
        for toast in self.toasts:
            toast.age += dt
        self.toasts = [t for t in self.toasts if not t.done]

    def draw(self, surface: Canvas, theme: Theme) -> None:
        y = float(MARGIN)
        for toast in self.toasts:
            v = toast.visibility()
            ease = 1 - (1 - v) ** 3
            rect = pygame.Rect(0, 0, WIDTH, HEIGHT)
            rect.topright = (
                round(surface.get_width() - MARGIN + (WIDTH + MARGIN) * (1 - ease)),
                round(y),
            )
            _draw_toast(surface, theme, toast, rect)
            y += (HEIGHT + GAP) * ease


def _draw_toast(surface: Canvas, theme: Theme, toast: Toast, rect: pygame.Rect) -> None:
    p = theme.palette
    accent = toast.accent or p.primary
    draw.shadow(surface, rect, theme.radius.md, p.shadow, (0, 6), 14)
    draw.rounded_rect(surface, rect, p.surface, theme.radius.md)
    draw.rounded_rect(surface, rect, p.border, theme.radius.md, 1)
    badge = pygame.Rect(0, 0, 36, 36)
    badge.midleft = (rect.x + 14, rect.centery)
    draw.rounded_rect(surface, badge, lerp_color(p.surface, accent, 0.22), theme.radius.sm)
    painter = toast.icon or draw.star_icon
    painter(surface, badge.center, accent, 20)
    left = badge.right + 12
    width = rect.right - 14 - left
    title_font = theme.font(theme.size.label, "semibold")
    if toast.message:
        draw.text(
            surface,
            draw.fit_text(toast.title, title_font, width),
            title_font,
            p.text,
            (left, rect.centery - 1),
            "bottomleft",
        )
        caption = theme.font(theme.size.caption)
        draw.text(
            surface,
            draw.fit_text(toast.message, caption, width),
            caption,
            p.text_muted,
            (left, rect.centery + 2),
            "topleft",
        )
    else:
        draw.text(
            surface,
            draw.fit_text(toast.title, title_font, width),
            title_font,
            p.text,
            (left, rect.centery),
            "midleft",
        )
