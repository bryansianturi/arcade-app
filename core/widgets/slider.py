"""Horizontal slider for picking a number in a range."""

from __future__ import annotations

from collections.abc import Callable

import pygame

from core import draw, gfx
from core.canvas import Canvas
from core.input import is_action
from core.theme import Color, Theme
from core.widgets.base import Widget


class Slider(Widget):
    """Drag the knob, click the track, or use Left/Right when focused.

    ``value`` is always a multiple of ``step`` (counted from ``minimum``) inside
    ``[minimum, maximum]``. ``on_change`` runs whenever it changes.
    """

    KNOB_R = 10

    def __init__(
        self,
        theme: Theme,
        rect: pygame.Rect | tuple[int, int, int, int],
        minimum: float,
        maximum: float,
        value: float,
        on_change: Callable[[float], None] | None = None,
        step: float = 1,
        accent: Color | None = None,
    ) -> None:
        super().__init__(theme, rect)
        self.minimum = minimum
        self.maximum = maximum
        self.step = step
        self.on_change = on_change
        self.accent = accent
        self.dragging = False
        self.value = self._snap(value)

    def _snap(self, value: float) -> float:
        steps = round((value - self.minimum) / self.step)
        snapped = self.minimum + steps * self.step
        snapped = max(self.minimum, min(self.maximum, snapped))
        return int(snapped) if float(self.step).is_integer() else round(snapped, 10)

    def set_value(self, value: float) -> None:
        """Change the value (snapped and clamped), calling ``on_change`` if it moved."""
        value = self._snap(value)
        if value != self.value:
            self.value = value
            if self.on_change is not None:
                self.on_change(value)

    def fraction(self) -> float:
        span = self.maximum - self.minimum
        return (self.value - self.minimum) / span if span else 0.0

    def _track(self) -> tuple[float, float]:
        return self.rect.x + self.KNOB_R, self.rect.right - self.KNOB_R

    def _value_at(self, x: float) -> float:
        left, right = self._track()
        f = (x - left) / (right - left) if right > left else 0.0
        return self.minimum + max(0.0, min(1.0, f)) * (self.maximum - self.minimum)

    def handle_event(self, event: pygame.event.Event) -> bool:
        if not (self.visible and self.enabled):
            return False
        if self._is_click(event):
            self.dragging = True
            self.set_value(self._value_at(event.pos[0]))
            return True
        if event.type == pygame.MOUSEMOTION and self.dragging:
            self.set_value(self._value_at(event.pos[0]))
            return True
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1 and self.dragging:
            self.dragging = False
            return True
        if self.focused:
            if is_action(event, "left"):
                self.set_value(self.value - self.step)
                return True
            if is_action(event, "right"):
                self.set_value(self.value + self.step)
                return True
        return False

    def update(self, dt: float) -> None:
        super().update(dt)
        if self.dragging and not pygame.mouse.get_pressed()[0]:
            self.dragging = False

    def draw(self, surface: Canvas) -> None:
        if not self.visible:
            return
        p = self.theme.palette
        accent = self.accent or p.primary
        left, right = self._track()
        cy = self.rect.centery
        knob_x = left + (right - left) * self.fraction()
        bar = pygame.Rect(round(left), cy - 3, round(right - left), 6)
        draw.rounded_rect(surface, bar, p.surface_hover, 3)
        filled = pygame.Rect(bar.x, bar.y, round(knob_x - left), 6)
        if filled.width > 0:
            draw.rounded_rect(surface, filled, accent, 3)
        r = self.KNOB_R + (2 if self.dragging else round(self._hover_t * 1.5))
        if self.focused:
            gfx.circle(surface, accent, (knob_x, cy), r + 4, 2)
        draw.shadow(
            surface,
            pygame.Rect(round(knob_x - r), cy - r, 2 * r, 2 * r),
            r,
            p.shadow,
            (0, 1),
            4,
        )
        gfx.circle(surface, (255, 255, 255), (knob_x, cy), r)
        gfx.circle(surface, accent, (knob_x, cy), r, 2)
