"""On/off switch."""

from __future__ import annotations

from collections.abc import Callable

import pygame

from core import draw
from core.theme import Theme, lerp_color
from core.widgets.base import Widget, approach


class Toggle(Widget):
    """An iOS-style switch. Click it (or press Enter/Space when focused) to flip."""

    WIDTH = 48
    HEIGHT = 28

    def __init__(
        self,
        theme: Theme,
        pos: tuple[int, int],
        value: bool = False,
        on_change: Callable[[bool], None] | None = None,
    ) -> None:
        super().__init__(theme, (pos[0], pos[1], self.WIDTH, self.HEIGHT))
        self.value = value
        self.on_change = on_change
        self._knob_t = 1.0 if value else 0.0

    def toggle(self) -> None:
        self.value = not self.value
        if self.on_change is not None:
            self.on_change(self.value)

    def handle_event(self, event: pygame.event.Event) -> bool:
        if self._is_click(event):
            self.toggle()
            return True
        if (
            self.focused
            and event.type == pygame.KEYDOWN
            and event.key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_LEFT, pygame.K_RIGHT)
        ):
            self.toggle()
            return True
        return False

    def update(self, dt: float) -> None:
        super().update(dt)
        self._knob_t = approach(self._knob_t, 1.0 if self.value else 0.0, dt, 18)

    def draw(self, surface: pygame.Surface) -> None:
        p = self.theme.palette
        track = lerp_color(p.surface_hover, p.primary, self._knob_t)
        draw.rounded_rect(surface, self.rect, track, self.HEIGHT // 2)
        if self.focused:
            draw.rounded_rect(surface, self.rect.inflate(6, 6), p.primary, self.HEIGHT // 2 + 3, 2)
        r = self.HEIGHT // 2 - 3
        travel = self.WIDTH - 2 * (r + 3)
        cx = self.rect.x + 3 + r + round(travel * self._knob_t)
        pygame.draw.circle(surface, (255, 255, 255), (cx, self.rect.centery), r)
