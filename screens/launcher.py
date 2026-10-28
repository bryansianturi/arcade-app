"""Home screen: favorites, recently played, and a searchable, filterable grid of apps."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

import pygame

from core import draw
from core.app_host import AppHost
from core.base_app import BaseApp, format_score
from core.canvas import Canvas, mouse_pos
from core.input import ACTIONDOWN, DIRECTION_STEPS
from core.scene_manager import Scene
from core.stats import format_ago
from core.widgets import Button, Card, Grid, SegmentedControl, TextInput, approach
from screens.common import HEADER_Y, MARGIN_X

if TYPE_CHECKING:
    from core.services import Services

CATEGORIES: tuple[tuple[str, str | None], ...] = (
    ("All", None),
    ("Games", "game"),
    ("Tools", "tool"),
)
CARD_MIN_WIDTH = 260
CARD_HEIGHT = 208
COMPACT_HEIGHT = 84
GRID_TOP = 196
SECTION_TITLE = 32  # height of a section heading
SECTION_GAP = 28


def matches(app: type[BaseApp], query: str, category: str | None) -> bool:
    """Return whether ``app`` passes the category filter and search ``query``."""
    meta = app.meta
    if category is not None and meta.category != category:
        return False
    q = query.strip().lower()
    return not q or q in meta.name.lower() or q in meta.description.lower()


@dataclass
class Section:
    """A titled block of cards. ``grid.rect.y`` is in content coordinates (0 = top)."""

    title: str | None
    apps: list[type[BaseApp]]
    grid: Grid
    compact: bool
    first_card: int  # index of this section's first card in ``LauncherScreen.cards``


def neighbor(rects: list[pygame.Rect], index: int, dx: int, dy: int) -> int:
    """The card reached by moving from ``rects[index]`` in direction ``(dx, dy)``.

    Left/right stay within the same row; up/down jump to the nearest row above or
    below (across sections) and pick the card closest horizontally.
    """
    if not rects:
        return 0
    here = rects[index]
    if dx:
        same_row = [i for i, r in enumerate(rects) if r.y == here.y]
        pos = same_row.index(index) + dx
        return same_row[pos] if 0 <= pos < len(same_row) else index
    rows = sorted({r.y for r in rects if (r.y - here.y) * dy > 0}, key=lambda y: abs(y - here.y))
    if not rows:
        return index
    in_row = [i for i, r in enumerate(rects) if r.y == rows[0]]
    return min(in_row, key=lambda i: abs(rects[i].centerx - here.centerx))


class LauncherScreen(Scene):
    """App cards in sections, with category tabs, search and keyboard/gamepad navigation."""

    def __init__(self, services: Services) -> None:
        super().__init__(services)
        t = services.theme
        w, h = services.scenes.size
        self.viewport = pygame.Rect(MARGIN_X, GRID_TOP, w - MARGIN_X * 2, h - GRID_TOP - t.space.lg)
        self.columns = Grid.fit(self.viewport, CARD_MIN_WIDTH, CARD_HEIGHT, gap=t.space.lg).columns
        # Header buttons, laid out right to left.
        x = w - MARGIN_X
        self.header_buttons: list[Button] = []
        for label, width, action, icon in (
            ("Settings", 120, self._open_settings, draw.gear_icon),
            ("High Scores", 150, self._open_scores, draw.star_icon),
            ("Achievements", 166, self._open_achievements, draw.trophy_icon),
            ("Stats", 100, self._open_stats, draw.chart_icon),
        ):
            x -= width
            self.header_buttons.insert(
                0, Button(t, (x, HEADER_Y + 4, width, 40), label, action, icon=icon)
            )
            x -= 12
        self.tabs = SegmentedControl(
            t,
            (MARGIN_X, 128, 330, 40),
            [c[0] for c in CATEGORIES],
            on_change=lambda _i: self._refilter(),
        )
        self.search = TextInput(
            t,
            (w - MARGIN_X - 300, 128, 300, 40),
            "Search apps",
            on_change=lambda _s: self._refilter(),
            icon=draw.search_icon,
        )
        self.visible: list[type[BaseApp]] = []
        self.sections: list[Section] = []
        self.cards: list[Card] = []
        self.card_apps: list[type[BaseApp]] = []
        self.selected = 0
        self.keyboard_nav = False
        self.scroll = 0.0
        self.scroll_target = 0.0
        self._refilter()

    # ------------------------------------------------------------------ data
    def _badge_for(self, app: type[BaseApp]) -> str | None:
        meta = app.meta
        if not meta.tracks_scores:
            return None
        scores = self.services.storage.scores_for(meta.id)
        # Prefer the hardest variant that has a score (variants are listed easy → hard).
        for variant in reversed(meta.score_variants()):
            entry = scores.get(variant)
            if entry is not None:
                label = "" if variant == "default" else f" · {variant.title()}"
                return f"Best {format_score(entry.score, meta.score_format)}{label}"
        return "No score yet"

    @property
    def browsing(self) -> bool:
        """Showing everything (no search, "All" tab): the personal rows are visible."""
        return self.tabs.index == 0 and not self.search.text.strip()

    def _build_sections(self) -> list[tuple[str | None, list[type[BaseApp]], bool]]:
        sections: list[tuple[str | None, list[type[BaseApp]], bool]] = []
        if self.browsing:
            by_id = {a.meta.id: a for a in self.services.apps}
            favorites = [by_id[i] for i in self.services.favorites.ids if i in by_id]
            recent_ids = self.services.stats.recent(self.columns, known=set(by_id))
            recent = [by_id[i] for i in recent_ids]
            if favorites:
                sections.append(("Favorites", favorites, True))
            if recent:
                sections.append(("Recently played", recent, True))
        title = "All apps" if sections else None
        sections.append((title, self.visible, False))
        return sections

    def _refilter(self) -> None:
        category = CATEGORIES[self.tabs.index][1]
        self.visible = [a for a in self.services.apps if matches(a, self.search.text, category)]
        t = self.services.theme
        now = datetime.now()
        self.sections, self.cards, self.card_apps = [], [], []
        y = 0
        for title, apps, compact in self._build_sections():
            if title is not None:
                y += SECTION_TITLE
            height = COMPACT_HEIGHT if compact else CARD_HEIGHT
            rect = pygame.Rect(self.viewport.x, y, self.viewport.width, 0)
            grid = Grid(rect, self.columns, height, gap=t.space.md if compact else t.space.lg)
            section = Section(title, apps, grid, compact, len(self.cards))
            self.sections.append(section)
            for i, app in enumerate(apps):
                if compact and title == "Recently played":
                    when = self.services.stats.get(app.meta.id).last_played
                    badge: str | None = f"Played {format_ago(when, now)}"
                else:
                    badge = self._badge_for(app)
                self.cards.append(
                    Card(
                        t,
                        grid.cell(i),
                        app.meta.name,
                        app.meta.description,
                        app.meta.accent,
                        on_click=lambda app=app: self._launch(app),  # type: ignore[misc]
                        badge=badge,
                        tag=app.meta.category,
                        icon=app.draw_icon,
                        favorite=app.meta.id in self.services.favorites,
                        on_favorite=lambda app=app: self._toggle_favorite(app),  # type: ignore[misc]
                        compact=compact,
                    )
                )
                self.card_apps.append(app)
            y += grid.content_height(len(apps)) + SECTION_GAP
        self.content_height = max(0, y - SECTION_GAP)
        self.selected = min(self.selected, max(0, len(self.cards) - 1))
        self.scroll_target = 0.0
        self._sync_focus()

    def on_reveal(self) -> None:
        # Coming back from an app or settings: scores, stats and favorites may have changed.
        self._refilter_preserving_selection()

    def _refilter_preserving_selection(self) -> None:
        selected, scroll = self.selected, self.scroll_target
        self._refilter()
        self.selected = min(selected, max(0, len(self.cards) - 1))
        self.scroll_target = self.scroll = min(scroll, self._max_scroll())
        self._sync_focus()

    # ------------------------------------------------------------------ actions
    def _launch(self, app: type[BaseApp]) -> None:
        self.search.focused = False
        self.manager.push(AppHost(self.services, app))

    def _toggle_favorite(self, app: type[BaseApp]) -> None:
        self.services.favorites.toggle(app.meta.id)
        current = self.card_apps[self.selected] if self.cards else None
        self._refilter_preserving_selection()
        # Keep the same app selected in the main grid (rows above may have changed).
        if current is not None and self.sections:
            main = self.sections[-1]
            if current in main.apps:
                self.selected = main.first_card + main.apps.index(current)
                self._ensure_visible(self.selected)
                self._sync_focus()

    def _open_settings(self) -> None:
        from screens.settings_screen import SettingsScreen

        self.manager.push(SettingsScreen(self.services))

    def _open_scores(self) -> None:
        from screens.high_scores import HighScoresScreen

        self.manager.push(HighScoresScreen(self.services))

    def _open_stats(self) -> None:
        from screens.stats import StatsScreen

        self.manager.push(StatsScreen(self.services))

    def _open_achievements(self) -> None:
        from screens.achievements import AchievementsScreen

        self.manager.push(AchievementsScreen(self.services))

    def _sync_focus(self) -> None:
        for i, card in enumerate(self.cards):
            card.focused = self.keyboard_nav and i == self.selected

    # ------------------------------------------------------------------ layout
    def _content_rects(self) -> list[pygame.Rect]:
        """Card rects in content coordinates (before scrolling)."""
        rects = []
        for section in self.sections:
            rects += [section.grid.cell(i) for i in range(len(section.apps))]
        return rects

    def _max_scroll(self) -> float:
        return float(max(0, self.content_height - self.viewport.height))

    def _ensure_visible(self, index: int) -> None:
        if not self.cards:
            return
        cell = self._content_rects()[index]
        section = next(s for s in reversed(self.sections) if s.first_card <= index)
        top = cell.y - (SECTION_TITLE if section.title and index == section.first_card else 0)
        if top < self.scroll_target:
            self.scroll_target = top
        elif cell.bottom > self.scroll_target + self.viewport.height:
            self.scroll_target = cell.bottom - self.viewport.height
        self.scroll_target = max(0.0, min(self._max_scroll(), self.scroll_target))

    # ------------------------------------------------------------------ events
    def handle_event(self, event: pygame.event.Event) -> None:
        for widget in (self.search, self.tabs, *self.header_buttons):
            if widget.handle_event(event):
                return
        if event.type == pygame.MOUSEMOTION:
            self.keyboard_nav = False
            self._sync_focus()
        elif event.type == pygame.MOUSEWHEEL:
            self.scroll_target = max(
                0.0, min(self._max_scroll(), self.scroll_target - event.y * 60)
            )
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.viewport.collidepoint(event.pos):
                for card in self.cards:
                    if card.handle_event(event):
                        return
        elif event.type == pygame.TEXTINPUT and not self.search.focused:
            # Start typing anywhere to search.
            self.search.focus()
            self.search.set_text(self.search.text + event.text)
        elif event.type == ACTIONDOWN:
            self._handle_action(event)
        elif event.type == pygame.KEYDOWN and event.key == pygame.K_TAB:
            step = -1 if event.mod & pygame.KMOD_SHIFT else 1
            self.tabs.select((self.tabs.index + step) % len(CATEGORIES))
        elif (
            event.type == pygame.KEYDOWN
            and event.key == pygame.K_d
            and event.mod & (pygame.KMOD_CTRL | pygame.KMOD_META)
            and self.cards
        ):
            self._toggle_favorite(self.card_apps[self.selected])

    def _handle_action(self, event: pygame.event.Event) -> None:
        if event.action in DIRECTION_STEPS:
            if self.keyboard_nav:
                dx, dy = DIRECTION_STEPS[event.action]
                self.selected = neighbor(self._content_rects(), self.selected, dx, dy)
            self.keyboard_nav = True
            self._ensure_visible(self.selected)
            self._sync_focus()
        elif event.action == "action" and self.cards and not event.repeat:
            self.cards[self.selected].activate()
        elif event.action == "pause" and self.search.text:
            self.search.set_text("")

    def wants_text(self) -> bool:
        return True  # typing anywhere searches

    # ------------------------------------------------------------------ frame
    def update(self, dt: float) -> None:
        self.scroll = approach(self.scroll, self.scroll_target, dt, 16)
        offset = self.viewport.y - round(self.scroll)
        inside = self.viewport.collidepoint(mouse_pos())
        for card, rect in zip(self.cards, self._content_rects(), strict=True):
            card.rect = rect.move(0, offset)
            card.update(dt)
            # Don't show hover effects for cards scrolled out of the visible area.
            if not inside:
                card.hovered = False
        for widget in (self.search, self.tabs, *self.header_buttons):
            widget.update(dt)

    def draw(self, surface: Canvas) -> None:
        t = self.services.theme
        p = t.palette
        surface.fill(p.bg)

        draw.text(
            surface, "Arcade", t.font(t.size.display, "bold"), p.text, (MARGIN_X, HEADER_Y - 4)
        )
        count = len(self.services.apps)
        subtitle = f"{count} app{'s' if count != 1 else ''} · pick one to play"
        draw.text(surface, subtitle, t.font(t.size.label), p.text_muted, (MARGIN_X, HEADER_Y + 50))
        for button in self.header_buttons:
            button.draw(surface)
        self.tabs.draw(surface)
        self.search.draw(surface)

        # Cards are clipped to the viewport (with room for hover lift and shadows).
        clip_area = self.viewport.inflate(32, 24)
        old_clip = surface.get_clip()
        surface.set_clip(clip_area)
        offset = self.viewport.y - round(self.scroll)
        heading = t.font(t.size.caption, "semibold")
        for section in self.sections:
            if section.title:
                draw.text(
                    surface,
                    section.title.upper(),
                    heading,
                    p.text_muted,
                    (self.viewport.x, section.grid.rect.y + offset - 10),
                    "bottomleft",
                )
        for card in self.cards:
            if card.rect.colliderect(clip_area):
                card.draw(surface)
        surface.set_clip(old_clip)

        if not self.visible:
            msg = (
                f'No apps match "{self.search.text}"'
                if self.search.text
                else "No apps in this category yet"
            )
            draw.text(
                surface,
                msg,
                t.font(t.size.title, "medium"),
                p.text_muted,
                self.viewport.center,
                "center",
            )

        failures = self.services.load_failures
        if failures:
            note = f"⚠ {len(failures)} app(s) failed to load: see arcade.log in the data folder"
            draw.text(
                surface,
                note,
                t.font(t.size.caption),
                p.warning,
                (MARGIN_X, surface.get_height() - 10),
                "bottomleft",
            )
