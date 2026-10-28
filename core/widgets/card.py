"""Launcher-style cards: an icon, a title, a description and an optional badge."""

from __future__ import annotations

from collections.abc import Callable

import pygame

from core import draw
from core.theme import Color, Theme, lerp_color
from core.widgets.base import Widget

IconPainter = Callable[[pygame.Surface, pygame.Rect, Theme], None]


class Card(Widget):
    """A clickable panel that lifts on hover. Used for the app grid in the launcher."""

    def __init__(
        self,
        theme: Theme,
        rect: pygame.Rect | tuple[int, int, int, int],
        title: str,
        description: str,
        accent: Color,
        on_click: Callable[[], None] | None = None,
        badge: str | None = None,
        tag: str | None = None,
        icon: IconPainter | None = None,
    ) -> None:
        super().__init__(theme, rect)
        self.title = title
        self.description = description
        self.accent = accent
        self.on_click = on_click
        self.badge = badge  # e.g. "Best 1,240"
        self.tag = tag  # e.g. "Game"
        self.icon = icon

    def activate(self) -> None:
        if self.on_click is not None:
            self.on_click()

    def handle_event(self, event: pygame.event.Event) -> bool:
        if self._is_click(event):
            self.activate()
            return True
        return False

    def draw(self, surface: pygame.Surface) -> None:
        if not self.visible:
            return
        t = self.theme
        p = t.palette
        lift = round(4 * self._hover_t)
        rect = self.rect.move(0, -lift)

        draw.shadow(surface, rect, t.radius.lg, p.shadow, (0, 4 + lift * 2), 10 + lift * 2)
        draw.rounded_rect(
            surface, rect, lerp_color(p.surface, p.surface_hover, self._hover_t * 0.5), t.radius.lg
        )
        # Accent strip along the top edge.
        strip = pygame.Rect(rect.x, rect.y, rect.width, t.radius.lg * 2)
        clip = surface.get_clip()
        surface.set_clip(pygame.Rect(rect.x, rect.y, rect.width, 4).clip(clip))
        draw.rounded_rect(surface, strip, self.accent, t.radius.lg)
        surface.set_clip(clip)

        if self.focused or self._hover_t > 0.01:
            ring = lerp_color(p.surface, self.accent, 1.0 if self.focused else self._hover_t)
            draw.rounded_rect(surface, rect, ring, t.radius.lg, 2)

        pad = t.space.lg
        icon_rect = pygame.Rect(rect.x + pad, rect.y + pad, 48, 48)
        if self.icon is not None:
            self.icon(surface, icon_rect, t)
        else:
            draw.rounded_rect(surface, icon_rect, self.accent, t.radius.md)

        if self.tag:
            tag_font = t.font(t.size.caption, "medium")
            draw.text(
                surface,
                self.tag.upper(),
                tag_font,
                p.text_muted,
                (rect.right - pad, rect.y + pad),
                "topright",
            )

        width = rect.width - pad * 2
        title_font = t.font(t.size.title, "semibold")
        title_y = icon_rect.bottom + t.space.md
        draw.text(
            surface,
            draw.fit_text(self.title, title_font, width),
            title_font,
            p.text,
            (rect.x + pad, title_y),
        )
        body_font = t.font(t.size.label)
        y = title_y + title_font.get_height() + t.space.xs
        for line in draw.wrap_text(self.description, body_font, width)[:2]:
            draw.text(surface, line, body_font, p.text_muted, (rect.x + pad, y))
            y += body_font.get_linesize()

        if self.badge:
            badge_font = t.font(t.size.caption, "semibold")
            bw = badge_font.size(self.badge)[0] + t.space.md
            badge = pygame.Rect(0, 0, bw, 24)
            badge.bottomleft = (rect.x + pad, rect.bottom - pad + 4)
            draw.rounded_rect(
                surface, badge, lerp_color(p.surface, self.accent, 0.22), t.radius.pill
            )
            draw.text(
                surface,
                self.badge,
                badge_font,
                lerp_color(p.text, self.accent, 0.35),
                badge.center,
                "center",
            )
