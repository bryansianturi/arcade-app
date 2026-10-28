"""Home screen: a searchable, filterable grid of every registered app."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pygame

from core import draw
from core.app_host import AppHost
from core.base_app import BaseApp, format_score
from core.canvas import Canvas, mouse_pos
from core.input import ACTIONDOWN
from core.scene_manager import Scene
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
GRID_TOP = 196


def matches(app: type[BaseApp], query: str, category: str | None) -> bool:
    """Return whether ``app`` passes the category filter and search ``query``."""
    meta = app.meta
    if category is not None and meta.category != category:
        return False
    q = query.strip().lower()
    return not q or q in meta.name.lower() or q in meta.description.lower()


class LauncherScreen(Scene):
    """Grid of app cards with category tabs, search and keyboard navigation."""

    def __init__(self, services: Services) -> None:
        super().__init__(services)
        t = services.theme
        w, h = services.scenes.size
        self.grid = Grid.fit(
            pygame.Rect(MARGIN_X, GRID_TOP, w - MARGIN_X * 2, h - GRID_TOP - t.space.lg),
            CARD_MIN_WIDTH,
            CARD_HEIGHT,
            gap=t.space.lg,
        )
        # Header buttons, laid out right to left.
        x = w - MARGIN_X
        self.header_buttons: list[Button] = []
        for label, width, action, icon in (
            ("Settings", 120, self._open_settings, draw.gear_icon),
            ("High Scores", 150, self._open_scores, draw.star_icon),
            ("Achievements", 166, self._open_achievements, draw.trophy_icon),
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
        self.cards: list[Card] = []
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

    def _refilter(self) -> None:
        category = CATEGORIES[self.tabs.index][1]
        self.visible = [a for a in self.services.apps if matches(a, self.search.text, category)]
        self.cards = [
            Card(
                self.services.theme,
                self.grid.cell(i),
                app.meta.name,
                app.meta.description,
                app.meta.accent,
                on_click=lambda app=app: self._launch(app),  # type: ignore[misc]
                badge=self._badge_for(app),
                tag=app.meta.category,
                icon=app.draw_icon,
            )
            for i, app in enumerate(self.visible)
        ]
        self.selected = min(self.selected, max(0, len(self.cards) - 1))
        self.scroll_target = 0.0
        self._sync_focus()

    def on_reveal(self) -> None:
        # Coming back from an app or settings: scores may have changed.
        self._refilter_preserving_selection()

    def _refilter_preserving_selection(self) -> None:
        selected, scroll = self.selected, self.scroll_target
        self._refilter()
        self.selected = min(selected, max(0, len(self.cards) - 1))
        self.scroll_target = self.scroll = scroll
        self._sync_focus()

    # ------------------------------------------------------------------ actions
    def _launch(self, app: type[BaseApp]) -> None:
        self.search.focused = False
        self.manager.push(AppHost(self.services, app))

    def _open_settings(self) -> None:
        from screens.settings_screen import SettingsScreen

        self.manager.push(SettingsScreen(self.services))

    def _open_scores(self) -> None:
        from screens.high_scores import HighScoresScreen

        self.manager.push(HighScoresScreen(self.services))

    def _open_achievements(self) -> None:
        from screens.achievements import AchievementsScreen

        self.manager.push(AchievementsScreen(self.services))

    def _sync_focus(self) -> None:
        for i, card in enumerate(self.cards):
            card.focused = self.keyboard_nav and i == self.selected

    def _max_scroll(self) -> float:
        return float(max(0, self.grid.content_height(len(self.cards)) - self.grid.rect.height))

    def _ensure_visible(self, index: int) -> None:
        cell = self.grid.cell(index)
        top = cell.y - self.grid.rect.y
        if top < self.scroll_target:
            self.scroll_target = top
        elif cell.bottom - self.grid.rect.y > self.scroll_target + self.grid.rect.height:
            self.scroll_target = cell.bottom - self.grid.rect.y - self.grid.rect.height
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
            if self.grid.rect.collidepoint(event.pos):
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

    def _handle_action(self, event: pygame.event.Event) -> None:
        moves = {"left": (-1, 0), "right": (1, 0), "up": (0, -1), "down": (0, 1)}
        if event.action in moves:
            if self.keyboard_nav:
                dx, dy = moves[event.action]
                self.selected = self.grid.move(self.selected, dx, dy, len(self.cards))
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
        for widget in (self.search, self.tabs, *self.header_buttons):
            widget.update(dt)
        for i, card in enumerate(self.cards):
            card.rect = self.grid.cell(i, round(self.scroll))
            card.update(dt)
            # Don't show hover effects for cards scrolled out of the visible area.
            if not self.grid.rect.collidepoint(mouse_pos()):
                card.hovered = False

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

        # Cards are clipped to the grid area (with room for hover lift and shadows).
        clip_area = self.grid.rect.inflate(32, 24)
        old_clip = surface.get_clip()
        surface.set_clip(clip_area)
        for card in self.cards:
            if card.rect.colliderect(clip_area):
                card.draw(surface)
        surface.set_clip(old_clip)

        if not self.cards:
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
                self.grid.rect.center,
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
