"""Clickable buttons with hover, press and focus states."""

from __future__ import annotations

from collections.abc import Callable
from typing import Literal

import pygame

from core import draw
from core.theme import Color, Theme, lerp_color, readable_on
from core.widgets.base import Widget, approach

Variant = Literal["primary", "secondary", "ghost", "danger"]


class Button(Widget):
    """A rounded button. ``on_click`` runs on mouse release or Enter/Space when focused."""

    def __init__(
        self,
        theme: Theme,
        rect: pygame.Rect | tuple[int, int, int, int],
        text: str,
        on_click: Callable[[], None] | None = None,
        variant: Variant = "secondary",
        accent: Color | None = None,
        font_size: int | None = None,
        icon: draw.Icon | None = None,
    ) -> None:
        super().__init__(theme, rect)
        self.text = text
        self.on_click = on_click
        self.variant: Variant = variant
        self.accent = accent
        self.font_size = font_size
        self.icon = icon  # optional glyph ("★") or vector painter (draw.gear_icon)
        self._pressed = False
        self._press_t = 0.0

    def flash(self) -> None:
        """Play the press animation (e.g. when the matching keyboard key is used)."""
        self._press_t = 1.0
        self._hover_t = 1.0

    def activate(self) -> None:
        """Trigger the button as if it were clicked."""
        if self.enabled and self.on_click is not None:
            self.on_click()

    def handle_event(self, event: pygame.event.Event) -> bool:
        if not (self.visible and self.enabled):
            return False
        if self._is_click(event):
            self._pressed = True
            return True
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1 and self._pressed:
            self._pressed = False
            if self.rect.collidepoint(event.pos):
                self.activate()
            return True
        if (
            self.focused
            and event.type == pygame.KEYDOWN
            and event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE)
        ):
            self._press_t = 1.0
            self.activate()
            return True
        return False

    def update(self, dt: float) -> None:
        super().update(dt)
        if self._pressed and not pygame.mouse.get_pressed()[0]:
            self._pressed = False
        self._press_t = approach(self._press_t, 1.0 if self._pressed else 0.0, dt, 24)

    def _colors(self) -> tuple[Color, Color]:
        p = self.theme.palette
        h = self._hover_t
        if self.variant in ("primary", "danger"):
            base = self.accent or (p.primary if self.variant == "primary" else p.danger)
            hover = lerp_color(base, (255, 255, 255), 0.12)
            return lerp_color(base, hover, h), readable_on(base)
        if self.variant == "ghost":
            return lerp_color(p.bg, p.surface_hover, h), p.text
        return lerp_color(p.surface_alt, p.surface_hover, h), p.text

    def draw(self, surface: pygame.Surface) -> None:
        if not self.visible:
            return
        theme = self.theme
        fill, fg = self._colors()
        if not self.enabled:
            fill = lerp_color(fill, theme.palette.bg, 0.5)
            fg = theme.palette.text_muted
        # Pressing shrinks the button slightly for tactile feedback.
        shrink = round(2 * self._press_t)
        rect = self.rect.inflate(-shrink * 2, -shrink * 2)
        if self.variant != "ghost" and self.enabled:
            draw.shadow(surface, rect, theme.radius.md, theme.palette.shadow, (0, 2), 6)
        draw.rounded_rect(surface, rect, fill, theme.radius.md)
        if self.focused:
            ring = self.accent or theme.palette.primary
            draw.rounded_rect(surface, rect.inflate(6, 6), ring, theme.radius.md + 3, 2)
        font = theme.font(self.font_size or theme.size.label, "semibold")
        if self.icon is None:
            label = draw.fit_text(self.text, font, rect.width - theme.space.md)
            draw.text(surface, label, font, fg, rect.center, "center")
            return
        gap = theme.space.sm
        icon_w = draw.icon_width(self.icon, font)
        label = draw.fit_text(self.text, font, rect.width - theme.space.md - icon_w - gap)
        x = rect.centerx - (icon_w + gap + font.size(label)[0]) // 2
        x = draw.draw_icon(surface, self.icon, font, fg, (x, rect.centery)) + gap
        draw.text(surface, label, font, fg, (x, rect.centery), "midleft")
