"""Pieces shared by the built-in screens."""

from __future__ import annotations

from collections.abc import Callable

import pygame

from core import draw
from core.canvas import Canvas
from core.theme import Theme
from core.widgets import Button

MARGIN_X = 48
HEADER_Y = 36


class SubpageHeader:
    """A "← Back" button plus a page title, used by Settings and High Scores."""

    def __init__(self, theme: Theme, title: str, on_back: Callable[[], None]) -> None:
        self.theme = theme
        self.title = title
        self.back = Button(theme, (MARGIN_X, HEADER_Y, 104, 40), "Back", on_back, "ghost", icon="←")

    def handle_event(self, event: pygame.event.Event) -> bool:
        return self.back.handle_event(event)

    def update(self, dt: float) -> None:
        self.back.update(dt)

    def draw(self, surface: Canvas) -> None:
        t = self.theme
        self.back.draw(surface)
        draw.text(
            surface,
            self.title,
            t.font(t.size.heading, "bold"),
            t.palette.text,
            (self.back.rect.right + t.space.lg, self.back.rect.centery),
            "midleft",
        )


def is_back_key(event: pygame.event.Event) -> bool:
    """Esc or Backspace returns to the previous screen."""
    return event.type == pygame.KEYDOWN and event.key in (pygame.K_ESCAPE, pygame.K_BACKSPACE)
