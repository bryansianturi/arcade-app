"""Global high scores, built automatically from every app with ``tracks_scores=True``."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import pygame

from core import draw, gfx
from core.base_app import BaseApp, format_score
from core.canvas import Canvas
from core.input import is_action
from core.scene_manager import Scene
from core.widgets import approach, draw_panel
from screens.common import MARGIN_X, SubpageHeader, is_back

if TYPE_CHECKING:
    from core.services import Services

ROW_HEIGHT = 92
ROW_GAP = 12
LIST_TOP = 112


@dataclass(frozen=True)
class ScoreCell:
    variant: str
    value: str  # formatted score, or "—"
    date: str


@dataclass(frozen=True)
class ScoreRow:
    app: type[BaseApp]
    cells: tuple[ScoreCell, ...]


def build_rows(services: Services) -> list[ScoreRow]:
    """Collect one row per score-tracking app, with a cell per variant."""
    rows: list[ScoreRow] = []
    for app in services.apps:
        meta = app.meta
        if not meta.tracks_scores:
            continue
        stored = services.storage.scores_for(meta.id)
        cells = []
        for variant in meta.score_variants():
            entry = stored.get(variant)
            label = "Best" if variant == "default" else variant.title()
            if entry is None:
                cells.append(ScoreCell(label, "—", ""))
            else:
                cells.append(
                    ScoreCell(label, format_score(entry.score, meta.score_format), entry.date)
                )
        rows.append(ScoreRow(app, tuple(cells)))
    return rows


class HighScoresScreen(Scene):
    """Lists the best score of every app (and every variant, e.g. difficulty)."""

    def __init__(self, services: Services) -> None:
        super().__init__(services)
        self.header = SubpageHeader(services.theme, "High Scores", self.manager.pop)
        self.rows = build_rows(services)
        self.scroll = 0.0
        self.scroll_target = 0.0

    def _max_scroll(self) -> float:
        h = self.manager.size[1]
        content = len(self.rows) * (ROW_HEIGHT + ROW_GAP)
        return float(max(0, content - (h - LIST_TOP - 24)))

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
        list_area = pygame.Rect(MARGIN_X - 24, LIST_TOP - 12, width + 48, surface.get_height())
        old_clip = surface.get_clip()
        surface.set_clip(list_area)
        y = LIST_TOP - round(self.scroll)
        for row in self.rows:
            rect = pygame.Rect(MARGIN_X, y, width, ROW_HEIGHT)
            if rect.bottom > 0 and rect.top < surface.get_height():
                self._draw_row(surface, rect, row)
            y += ROW_HEIGHT + ROW_GAP
        surface.set_clip(old_clip)

        # The header is drawn last so rows scroll underneath it.
        gfx.rect(surface, p.bg, (0, 0, surface.get_width(), LIST_TOP - 12))
        self.header.draw(surface)

        if not self.rows:
            draw.text(
                surface,
                "No apps track scores yet",
                t.font(t.size.title, "medium"),
                p.text_muted,
                surface.get_rect().center,
                "center",
            )

    def _draw_row(self, surface: Canvas, rect: pygame.Rect, row: ScoreRow) -> None:
        t = self.services.theme
        p = t.palette
        meta = row.app.meta
        draw_panel(surface, rect, t)
        icon = pygame.Rect(rect.x + t.space.lg, 0, 44, 44)
        icon.centery = rect.centery
        row.app.draw_icon(surface, icon, t)
        draw.text(
            surface,
            meta.name,
            t.font(t.size.title, "semibold"),
            p.text,
            (icon.right + t.space.md, rect.centery),
            "midleft",
        )

        # Variant columns are right-aligned, each 150px wide.
        col_w = 150
        x = rect.right - t.space.lg - col_w * len(row.cells)
        for cell in row.cells:
            empty = cell.value == "—"
            draw.text(
                surface,
                cell.variant.upper(),
                t.font(t.size.caption, "medium"),
                p.text_muted,
                (x, rect.y + 18),
            )
            draw.text(
                surface,
                cell.value,
                t.font(t.size.title, "bold"),
                p.text_muted if empty else meta.accent,
                (x, rect.y + 36),
            )
            if cell.date:
                draw.text(
                    surface, cell.date, t.font(t.size.caption), p.text_muted, (x, rect.y + 66)
                )
            x += col_w
