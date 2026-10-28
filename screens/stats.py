"""Stats screen: total play time, sessions, most played app and a per-app table."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

import pygame

from core import draw, gfx
from core.base_app import BaseApp
from core.canvas import Canvas
from core.input import is_action
from core.scene_manager import Scene
from core.stats import AppStats, format_ago, format_duration
from core.theme import lerp_color
from core.widgets import approach, draw_panel
from screens.common import MARGIN_X, SubpageHeader, is_back

if TYPE_CHECKING:
    from core.services import Services

TILES_TOP = 112
TILE_HEIGHT = 104
LIST_TOP = TILES_TOP + TILE_HEIGHT + 56
ROW_HEIGHT = 60


@dataclass(frozen=True)
class StatsRow:
    app: type[BaseApp]
    stats: AppStats


def build_rows(services: Services) -> list[StatsRow]:
    """Apps that have been opened at least once, most played first."""
    rows = [StatsRow(app, services.stats.get(app.meta.id)) for app in services.apps]
    rows = [r for r in rows if r.stats.sessions]
    rows.sort(key=lambda r: (r.stats.seconds, r.stats.sessions), reverse=True)
    return rows


class StatsScreen(Scene):
    """Summary tiles plus a scrollable table of every app played."""

    def __init__(self, services: Services) -> None:
        super().__init__(services)
        self.header = SubpageHeader(services.theme, "Stats", self.manager.pop)
        self.rows = build_rows(services)
        self.scroll = 0.0
        self.scroll_target = 0.0

    def _max_scroll(self) -> float:
        visible = self.manager.size[1] - LIST_TOP - 24
        return float(max(0, len(self.rows) * ROW_HEIGHT - visible))

    def handle_event(self, event: pygame.event.Event) -> None:
        if self.header.handle_event(event):
            return
        if is_back(event):
            self.manager.pop()
        elif event.type == pygame.MOUSEWHEEL:
            self.scroll_target -= event.y * 60
        elif is_action(event, "up") or is_action(event, "down"):
            self.scroll_target += ROW_HEIGHT * (1 if event.action == "down" else -1)
        self.scroll_target = max(0.0, min(self._max_scroll(), self.scroll_target))

    def update(self, dt: float) -> None:
        self.header.update(dt)
        self.scroll = approach(self.scroll, self.scroll_target, dt, 16)

    # ------------------------------------------------------------------ drawing
    def draw(self, surface: Canvas) -> None:
        t = self.services.theme
        p = t.palette
        surface.fill(p.bg)
        self.header.draw(surface)
        self._draw_tiles(surface)
        width = surface.get_width() - MARGIN_X * 2
        if not self.rows:
            draw.text(
                surface,
                "Play something and your stats will show up here",
                t.font(t.size.title, "medium"),
                p.text_muted,
                (surface.get_width() // 2, LIST_TOP + 80),
                "center",
            )
            return
        self._draw_columns(surface, width)
        panel = pygame.Rect(MARGIN_X, LIST_TOP, width, surface.get_height() - LIST_TOP - 24)
        draw_panel(surface, panel, t)
        old_clip = surface.get_clip()
        surface.set_clip(panel.inflate(0, -8))
        top_seconds = max(self.rows[0].stats.seconds, 1.0)
        now = datetime.now()
        y = panel.y + 4 - round(self.scroll)
        for i, row in enumerate(self.rows):
            rect = pygame.Rect(panel.x, y + i * ROW_HEIGHT, panel.width, ROW_HEIGHT)
            if rect.bottom > panel.top and rect.top < panel.bottom:
                self._draw_row(surface, rect, row, top_seconds, now, divider=i > 0)
        surface.set_clip(old_clip)

    def _draw_tiles(self, surface: Canvas) -> None:
        t = self.services.theme
        p = t.palette
        stats = self.services.stats
        known = {a.meta.id for a in self.services.apps}
        most = stats.most_played(known)
        most_app = self.services.app(most) if most else None
        played = sum(1 for a in self.services.apps if stats.get(a.meta.id).sessions)
        tiles = [
            ("Play time", format_duration(stats.total_seconds), None),
            ("Sessions", f"{stats.total_sessions:,}", None),
            ("Apps tried", f"{played} / {len(self.services.apps)}", None),
            ("Most played", most_app.meta.name if most_app else "—", most_app),
        ]
        gap = t.space.md
        width = (surface.get_width() - MARGIN_X * 2 - gap * (len(tiles) - 1)) // len(tiles)
        for i, (label, value, app) in enumerate(tiles):
            rect = pygame.Rect(MARGIN_X + i * (width + gap), TILES_TOP, width, TILE_HEIGHT)
            draw_panel(surface, rect, t)
            x = rect.x + t.space.lg
            if app is not None:
                icon = pygame.Rect(x, 0, 40, 40)
                icon.centery = rect.centery + 12
                app.draw_icon(surface, icon, t)
                x = icon.right + t.space.sm + 4
            draw.text(
                surface,
                label.upper(),
                t.font(t.size.caption, "semibold"),
                p.text_muted,
                (rect.x + t.space.lg, rect.y + 20),
            )
            value_font = t.font(t.size.heading, "bold")
            draw.text(
                surface,
                draw.fit_text(value, value_font, rect.right - t.space.md - x),
                value_font,
                app.meta.accent if app is not None else p.text,
                (x, rect.centery + 12),
                "midleft",
            )

    def _draw_columns(self, surface: Canvas, width: int) -> None:
        t = self.services.theme
        font = t.font(t.size.caption, "semibold")
        y = LIST_TOP - 14
        right = MARGIN_X + width - t.space.lg
        columns: tuple[tuple[str, int, draw.Anchor], ...] = (
            ("APP", MARGIN_X + t.space.lg, "bottomleft"),
            ("PLAY TIME", MARGIN_X + 520, "bottomleft"),
            ("SESSIONS", right - 200, "bottomright"),
            ("LAST PLAYED", right, "bottomright"),
        )
        for label, x, anchor in columns:
            draw.text(surface, label, font, t.palette.text_muted, (x, y), anchor)

    def _draw_row(
        self,
        surface: Canvas,
        rect: pygame.Rect,
        row: StatsRow,
        top_seconds: float,
        now: datetime,
        divider: bool,
    ) -> None:
        t = self.services.theme
        p = t.palette
        meta = row.app.meta
        if divider:
            gfx.line(
                surface, p.border, (rect.x + t.space.lg, rect.y), (rect.right - t.space.lg, rect.y)
            )
        icon = pygame.Rect(rect.x + t.space.lg, 0, 34, 34)
        icon.centery = rect.centery
        row.app.draw_icon(surface, icon, t)
        draw.text(
            surface,
            meta.name,
            t.font(t.size.body, "semibold"),
            p.text,
            (icon.right + t.space.md, rect.centery),
            "midleft",
        )
        # Play-time bar, relative to the most played app.
        bar_x = MARGIN_X + 520
        bar = pygame.Rect(bar_x, 0, 220, 8)
        bar.centery = rect.centery
        gfx.rect(surface, p.surface_alt, bar, border_radius=4)
        fill = bar.copy()
        fill.width = max(8, round(bar.width * row.stats.seconds / top_seconds))
        gfx.rect(surface, meta.accent, fill, border_radius=4)
        draw.text(
            surface,
            format_duration(row.stats.seconds),
            t.font(t.size.label, "semibold"),
            lerp_color(p.text, meta.accent, 0.3),
            (bar.right + t.space.md, rect.centery),
            "midleft",
        )
        right = rect.right - t.space.lg
        draw.text(
            surface,
            f"{row.stats.sessions:,}",
            t.font(t.size.label, "medium"),
            p.text,
            (right - 200, rect.centery),
            "midright",
        )
        draw.text(
            surface,
            format_ago(row.stats.last_played, now),
            t.font(t.size.label),
            p.text_muted,
            (right, rect.centery),
            "midright",
        )
