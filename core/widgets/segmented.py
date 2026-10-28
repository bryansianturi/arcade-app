"""Segmented control (a row of mutually exclusive options), used for tabs and choices."""

from __future__ import annotations

from collections.abc import Callable, Sequence

import pygame

from core import draw
from core.theme import Color, Theme, lerp_color, readable_on
from core.widgets.base import Widget, approach


class SegmentedControl(Widget):
    """A pill-shaped selector. Left/Right arrows change the choice when focused."""

    def __init__(
        self,
        theme: Theme,
        rect: pygame.Rect | tuple[int, int, int, int],
        options: Sequence[str],
        index: int = 0,
        on_change: Callable[[int], None] | None = None,
        accent: Color | None = None,
    ) -> None:
        super().__init__(theme, rect)
        self.options = list(options)
        self.index = index
        self.on_change = on_change
        self.accent = accent
        self._pill_x = float(self._segment(index).x)
        self._hover_index = -1

    def _segment(self, i: int) -> pygame.Rect:
        w = self.rect.width / len(self.options)
        return pygame.Rect(round(self.rect.x + i * w), self.rect.y, round(w), self.rect.height)

    def select(self, index: int) -> None:
        index = max(0, min(len(self.options) - 1, index))
        if index != self.index:
            self.index = index
            if self.on_change is not None:
                self.on_change(index)

    def handle_event(self, event: pygame.event.Event) -> bool:
        if self._is_click(event):
            for i in range(len(self.options)):
                if self._segment(i).collidepoint(event.pos):
                    self.select(i)
            return True
        if self.focused and event.type == pygame.KEYDOWN:
            if event.key == pygame.K_LEFT:
                self.select(self.index - 1)
                return True
            if event.key == pygame.K_RIGHT:
                self.select(self.index + 1)
                return True
        return False

    def update(self, dt: float) -> None:
        super().update(dt)
        self._pill_x = approach(self._pill_x, self._segment(self.index).x, dt, 18)
        mouse = pygame.mouse.get_pos()
        self._hover_index = next(
            (
                i
                for i in range(len(self.options))
                if self.hovered and self._segment(i).collidepoint(mouse)
            ),
            -1,
        )

    def draw(self, surface: pygame.Surface) -> None:
        t = self.theme
        p = t.palette
        accent = self.accent or p.primary
        radius = self.rect.height // 2
        draw.rounded_rect(surface, self.rect, p.surface_alt, radius)
        if self.focused:
            draw.rounded_rect(surface, self.rect.inflate(6, 6), accent, radius + 3, 2)
        pill = self._segment(self.index).inflate(-6, -6)
        pill.x = round(self._pill_x) + 3
        draw.rounded_rect(surface, pill, accent, pill.height // 2)
        font = t.font(t.size.label, "semibold")
        for i, option in enumerate(self.options):
            seg = self._segment(i)
            if i == self.index:
                color = readable_on(accent)
            elif i == self._hover_index:
                color = p.text
            else:
                color = lerp_color(p.text_muted, p.text, 0.2)
            draw.text(
                surface,
                draw.fit_text(option, font, seg.width - 8),
                font,
                color,
                seg.center,
                "center",
            )
