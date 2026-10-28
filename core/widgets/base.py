"""Shared widget plumbing: the :class:`Widget` base class and animation helpers."""

from __future__ import annotations

import pygame

from core.theme import Theme

#: How quickly hover/press animations settle (higher is snappier).
ANIM_SPEED = 14.0


def approach(current: float, target: float, dt: float, speed: float = ANIM_SPEED) -> float:
    """Move ``current`` towards ``target`` with frame-rate independent easing."""
    return current + (target - current) * min(1.0, dt * speed)


class Widget:
    """Base class for UI elements with a rectangle, hover tracking and focus.

    Subclasses override :meth:`handle_event` (return ``True`` to consume the
    event), :meth:`update` and :meth:`draw`.
    """

    def __init__(self, theme: Theme, rect: pygame.Rect | tuple[int, int, int, int]) -> None:
        self.theme = theme
        self.rect = pygame.Rect(rect)
        self.visible = True
        self.enabled = True
        self.focused = False  # keyboard focus (drawn as a ring)
        self.hovered = False
        self._hover_t = 0.0  # 0..1, animated

    def handle_event(self, event: pygame.event.Event) -> bool:
        return False

    def update(self, dt: float) -> None:
        self.hovered = (
            self.visible and self.enabled and self.rect.collidepoint(pygame.mouse.get_pos())
        )
        self._hover_t = approach(self._hover_t, 1.0 if self.hovered or self.focused else 0.0, dt)

    def draw(self, surface: pygame.Surface) -> None:
        raise NotImplementedError

    def _is_click(self, event: pygame.event.Event) -> bool:
        return (
            event.type == pygame.MOUSEBUTTONDOWN
            and event.button == 1
            and self.visible
            and self.enabled
            and self.rect.collidepoint(event.pos)
        )
