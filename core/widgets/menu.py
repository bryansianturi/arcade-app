"""A vertical stack of buttons with keyboard navigation, plus a panel helper.

Used for the pause menu, crash dialog and app start screens (e.g. choose difficulty).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

import pygame

from core import draw
from core.canvas import Canvas
from core.input import is_action
from core.theme import Color, Theme
from core.widgets.button import Button, Variant

MenuItem = tuple[str, Callable[[], None]]


def draw_panel(surface: Canvas, rect: pygame.Rect, theme: Theme) -> None:
    """Draw a raised rounded panel (shadow + surface color)."""
    draw.shadow(surface, rect, theme.radius.lg, theme.palette.shadow, (0, 10), 18)
    draw.rounded_rect(surface, rect, theme.palette.surface, theme.radius.lg)


class ButtonMenu:
    """Buttons laid out vertically and centred on ``center``.

    Up/Down (or W/S, Tab) move focus, Enter/Space activates, and hovering with
    the mouse moves focus too. The first item uses ``primary_variant``.
    """

    def __init__(
        self,
        theme: Theme,
        center: tuple[int, int],
        items: Sequence[MenuItem],
        width: int = 260,
        height: int = 48,
        gap: int = 12,
        accent: Color | None = None,
        primary_variant: Variant = "primary",
    ) -> None:
        self.theme = theme
        total = len(items) * height + (len(items) - 1) * gap
        top = center[1] - total // 2
        self.buttons = [
            Button(
                theme,
                (center[0] - width // 2, top + i * (height + gap), width, height),
                label,
                action,
                variant=primary_variant if i == 0 else "secondary",
                accent=accent,
            )
            for i, (label, action) in enumerate(items)
        ]
        self.index = 0
        self._sync_focus()

    @property
    def rect(self) -> pygame.Rect:
        return self.buttons[0].rect.unionall([b.rect for b in self.buttons[1:]])

    def _sync_focus(self) -> None:
        for i, button in enumerate(self.buttons):
            button.focused = i == self.index

    def handle_event(self, event: pygame.event.Event) -> bool:
        if is_action(event, "up"):
            self.index = (self.index - 1) % len(self.buttons)
            self._sync_focus()
            return True
        if is_action(event, "down") or (event.type == pygame.KEYDOWN and event.key == pygame.K_TAB):
            self.index = (self.index + 1) % len(self.buttons)
            self._sync_focus()
            return True
        if event.type == pygame.MOUSEMOTION:
            for i, button in enumerate(self.buttons):
                if button.rect.collidepoint(event.pos) and i != self.index:
                    self.index = i
                    self._sync_focus()
        return any(button.handle_event(event) for button in self.buttons)

    def update(self, dt: float) -> None:
        for button in self.buttons:
            button.update(dt)

    def draw(self, surface: Canvas) -> None:
        for button in self.buttons:
            button.draw(surface)
