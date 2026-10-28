"""Launcher-style cards: an icon, a title, a description, an optional badge and a
favorite star. ``compact`` cards (icon, title and one line) are used for the
launcher's Favorites and Recently played rows."""

from __future__ import annotations

from collections.abc import Callable

import pygame

from core import draw
from core.canvas import Canvas
from core.theme import Color, Theme, lerp_color
from core.widgets.base import Widget

IconPainter = Callable[[Canvas, pygame.Rect, Theme], None]


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
        favorite: bool | None = None,
        on_favorite: Callable[[], None] | None = None,
        compact: bool = False,
    ) -> None:
        super().__init__(theme, rect)
        self.title = title
        self.description = description
        self.accent = accent
        self.on_click = on_click
        self.badge = badge  # e.g. "Best 1,240"
        self.tag = tag  # e.g. "Game"
        self.icon = icon
        self.favorite = favorite  # None: no star shown
        self.on_favorite = on_favorite
        self.compact = compact

    def star_rect(self) -> pygame.Rect:
        """Hit area of the favorite star (top-right corner)."""
        size = 32
        pad = self.theme.space.md if self.compact else self.theme.space.lg - 6
        return pygame.Rect(self.rect.right - pad - size + 6, self.rect.y + pad - 6, size, size)

    def activate(self) -> None:
        if self.on_click is not None:
            self.on_click()

    def handle_event(self, event: pygame.event.Event) -> bool:
        if self._is_click(event):
            if self.favorite is not None and self.star_rect().collidepoint(event.pos):
                if self.on_favorite is not None:
                    self.on_favorite()
            else:
                self.activate()
            return True
        return False

    def draw(self, surface: Canvas) -> None:
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

        self._draw_star(surface, rect)
        if self.compact:
            self._draw_compact(surface, rect)
            return

        pad = t.space.lg
        icon_rect = pygame.Rect(rect.x + pad, rect.y + pad, 44, 44)
        if self.icon is not None:
            self.icon(surface, icon_rect, t)
        else:
            draw.rounded_rect(surface, icon_rect, self.accent, t.radius.md)

        if self.tag:
            tag_font = t.font(t.size.caption, "medium")
            right = rect.right - pad - (30 if self.favorite is not None else 0)
            draw.text(
                surface,
                self.tag.upper(),
                tag_font,
                p.text_muted,
                (right, rect.y + pad),
                "topright",
            )

        width = rect.width - pad * 2
        title_font = t.font(t.size.title, "semibold")
        title_y = icon_rect.bottom + 12
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

    def _draw_star(self, surface: Canvas, rect: pygame.Rect) -> None:
        if self.favorite is None:
            return
        p = self.theme.palette
        star = self.star_rect().move(0, rect.y - self.rect.y)
        if self.favorite:
            draw.star_icon(surface, star.center, p.warning, 20)
        elif self._hover_t > 0.01 or self.focused:
            color = lerp_color(
                p.surface, p.text_muted, max(self._hover_t, 1.0 if self.focused else 0)
            )
            draw.star_outline_icon(surface, star.center, color, 20)

    def _draw_compact(self, surface: Canvas, rect: pygame.Rect) -> None:
        t = self.theme
        p = t.palette
        pad = t.space.md
        icon_rect = pygame.Rect(rect.x + pad, 0, 40, 40)
        icon_rect.centery = rect.centery + 2
        if self.icon is not None:
            self.icon(surface, icon_rect, t)
        else:
            draw.rounded_rect(surface, icon_rect, self.accent, t.radius.md)
        x = icon_rect.right + t.space.md
        width = rect.right - pad - x - (24 if self.favorite is not None else 0)
        title_font = t.font(t.size.body, "semibold")
        draw.text(
            surface,
            draw.fit_text(self.title, title_font, width),
            title_font,
            p.text,
            (x, icon_rect.centery - 1),
            "bottomleft",
        )
        caption = t.font(t.size.caption)
        draw.text(
            surface,
            draw.fit_text(self.badge or self.description, caption, width),
            caption,
            lerp_color(p.text_muted, self.accent, 0.35) if self.badge else p.text_muted,
            (x, icon_rect.centery + 2),
            "topleft",
        )
