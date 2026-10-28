"""Achievements screen: every app's achievements, locked and unlocked."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import pygame

from core import draw, gfx
from core.achievements import Achievement
from core.base_app import BaseApp
from core.canvas import Canvas
from core.input import is_action
from core.scene_manager import Scene
from core.theme import lerp_color
from core.widgets import approach, draw_panel
from screens.common import MARGIN_X, SubpageHeader, is_back

if TYPE_CHECKING:
    from core.services import Services

ROW_HEIGHT = 124
ROW_GAP = 12
LIST_TOP = 112
INFO_WIDTH = 250
MAX_TILES = 4


@dataclass(frozen=True)
class AchievementRow:
    app: type[BaseApp]
    items: tuple[tuple[Achievement, str | None], ...]  # (definition, unlocked-at or None)

    @property
    def unlocked(self) -> int:
        return sum(at is not None for _, at in self.items)


def build_rows(services: Services) -> list[AchievementRow]:
    """One row per app that declares achievements."""
    service = services.achievements
    rows = []
    for app in services.apps:
        defs = service.definitions(app.meta.id)
        if defs:
            items = tuple((a, service.unlocked_at(app.meta.id, a.id)) for a in defs)
            rows.append(AchievementRow(app, items))
    return rows


class AchievementsScreen(Scene):
    """Scrollable list of apps, each with its achievement tiles."""

    def __init__(self, services: Services) -> None:
        super().__init__(services)
        self.header = SubpageHeader(services.theme, "Achievements", self.manager.pop)
        self.rows = build_rows(services)
        self.scroll = 0.0
        self.scroll_target = 0.0

    def _max_scroll(self) -> float:
        content = len(self.rows) * (ROW_HEIGHT + ROW_GAP)
        return float(max(0, content - (self.manager.size[1] - LIST_TOP - 24)))

    def handle_event(self, event: pygame.event.Event) -> None:
        if self.header.handle_event(event):
            return
        if is_back(event):
            self.manager.pop()
        elif event.type == pygame.MOUSEWHEEL:
            self.scroll_target -= event.y * 60
        elif is_action(event, "up") or is_action(event, "down"):
            step = 1 if event.action == "down" else -1
            self.scroll_target += (ROW_HEIGHT + ROW_GAP) * step
        self.scroll_target = max(0.0, min(self._max_scroll(), self.scroll_target))

    def update(self, dt: float) -> None:
        self.header.update(dt)
        self.scroll = approach(self.scroll, self.scroll_target, dt, 16)

    def draw(self, surface: Canvas) -> None:
        t = self.services.theme
        p = t.palette
        surface.fill(p.bg)
        width = surface.get_width() - MARGIN_X * 2
        old_clip = surface.get_clip()
        surface.set_clip(pygame.Rect(0, LIST_TOP - 12, surface.get_width(), surface.get_height()))
        y = LIST_TOP - round(self.scroll)
        for row in self.rows:
            rect = pygame.Rect(MARGIN_X, y, width, ROW_HEIGHT)
            if rect.bottom > 0 and rect.top < surface.get_height():
                self._draw_row(surface, rect, row)
            y += ROW_HEIGHT + ROW_GAP
        surface.set_clip(old_clip)

        gfx.rect(surface, p.bg, (0, 0, surface.get_width(), LIST_TOP - 12))
        self.header.draw(surface)
        self._draw_summary(surface)
        if not self.rows:
            draw.text(
                surface,
                "No achievements yet",
                t.font(t.size.title, "medium"),
                p.text_muted,
                surface.get_rect().center,
                "center",
            )

    def _draw_summary(self, surface: Canvas) -> None:
        t = self.services.theme
        p = t.palette
        done, total = self.services.achievements.progress()
        right = surface.get_width() - MARGIN_X
        bar = pygame.Rect(0, 0, 220, 8)
        bar.midright = (right, 64)
        gfx.rect(surface, p.surface_alt, bar, border_radius=4)
        if total and done:
            fill = bar.copy()
            fill.width = max(8, round(bar.width * done / total))
            gfx.rect(surface, p.primary, fill, border_radius=4)
        draw.text(
            surface,
            f"{done} of {total} unlocked",
            t.font(t.size.label, "semibold"),
            p.text,
            (bar.right, bar.top - 8),
            "bottomright",
        )

    def _draw_row(self, surface: Canvas, rect: pygame.Rect, row: AchievementRow) -> None:
        t = self.services.theme
        p = t.palette
        meta = row.app.meta
        draw_panel(surface, rect, t)
        icon = pygame.Rect(rect.x + t.space.lg, 0, 44, 44)
        icon.centery = rect.centery
        row.app.draw_icon(surface, icon, t)
        x = icon.right + t.space.md
        title_font = t.font(t.size.title, "semibold")
        draw.text(
            surface,
            draw.fit_text(meta.name, title_font, rect.x + INFO_WIDTH - t.space.md - x),
            title_font,
            p.text,
            (x, rect.centery - 2),
            "bottomleft",
        )
        draw.text(
            surface,
            f"{row.unlocked} / {len(row.items)}",
            t.font(t.size.label, "medium"),
            meta.accent if row.unlocked else p.text_muted,
            (x, rect.centery + 4),
            "topleft",
        )

        left = rect.x + INFO_WIDTH
        tile_w = (rect.right - t.space.md - left - t.space.sm * (MAX_TILES - 1)) // MAX_TILES
        for i, (achievement, at) in enumerate(row.items[:MAX_TILES]):
            tile = pygame.Rect(
                left + i * (tile_w + t.space.sm), rect.y + 14, tile_w, rect.height - 28
            )
            self._draw_tile(surface, tile, achievement, at, meta.accent)

    def _draw_tile(
        self,
        surface: Canvas,
        rect: pygame.Rect,
        achievement: Achievement,
        unlocked_at: str | None,
        accent: tuple[int, int, int],
    ) -> None:
        t = self.services.theme
        p = t.palette
        unlocked = unlocked_at is not None
        draw.rounded_rect(
            surface,
            rect,
            lerp_color(p.surface, accent, 0.12) if unlocked else p.surface_alt,
            t.radius.md,
        )
        badge = pygame.Rect(rect.x + 12, rect.y + 12, 30, 30)
        if unlocked:
            draw.rounded_rect(surface, badge, accent, 15)
            draw.star_icon(surface, badge.center, (255, 255, 255), 18)
        else:
            draw.rounded_rect(surface, badge, p.surface_hover, 15)
            draw.lock_icon(surface, badge.center, p.text_muted, 15)
        text_x = badge.right + 10
        width = rect.right - 10 - text_x
        secret = achievement.hidden and not unlocked
        name = "Hidden achievement" if secret else achievement.name
        draw.text(
            surface,
            draw.fit_text(name, t.font(t.size.label, "semibold"), width),
            t.font(t.size.label, "semibold"),
            p.text if unlocked else p.text_muted,
            (text_x, badge.centery),
            "midleft",
        )
        caption = t.font(t.size.caption)
        description = "Keep playing to find out" if secret else achievement.description
        lines = draw.wrap_text(description, caption, rect.width - 24)[:2]
        for j, line in enumerate(lines):
            draw.text(
                surface,
                draw.fit_text(line, caption, rect.width - 24),
                caption,
                p.text_muted,
                (rect.x + 12, badge.bottom + 6 + j * 18),
            )
