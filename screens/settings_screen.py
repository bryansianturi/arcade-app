"""Settings screen: theme, window size, fullscreen, developer mode, animations, controls, data."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

import pygame

from core import draw, gfx
from core.canvas import Canvas
from core.input import is_action
from core.scene_manager import Scene
from core.settings import WINDOW_PRESETS
from core.web import IS_BROWSER
from core.widgets import Button, SegmentedControl, Toggle, Widget, draw_panel
from screens.common import MARGIN_X, SubpageHeader, is_back

if TYPE_CHECKING:
    from core.services import Services

ROW_HEIGHT = 72
PANEL_WIDTH = 820


@dataclass
class _Row:
    title: str
    hint: str
    control: Widget


class SettingsScreen(Scene):
    """Edits :class:`core.settings.Settings`; every change is saved immediately."""

    def __init__(self, services: Services) -> None:
        super().__init__(services)
        t = services.theme
        s = services.settings
        self.header = SubpageHeader(t, "Settings", self.manager.pop)
        w, _ = self.manager.size
        self.panel = pygame.Rect((w - PANEL_WIDTH) // 2, 116, PANEL_WIDTH, 0)
        right = self.panel.right - t.space.lg
        self._confirm_reset = False

        def seg(width: int, options: list[str], index: int, cb: Callable[[int], None]) -> Widget:
            return SegmentedControl(t, (right - width, 0, width, 40), options, index, cb)

        def toggle(value: bool, cb: Callable[[bool], None]) -> Toggle:
            return Toggle(t, (right - Toggle.WIDTH, 0), value, cb)

        size_index = WINDOW_PRESETS.index(s.window_size) if s.window_size in WINDOW_PRESETS else 1
        self.reset_btn = Button(
            t, (right - 190, 0, 190, 40), "Reset high scores", self._reset_scores, "danger"
        )
        self.fullscreen_toggle = toggle(s.fullscreen, self._set_fullscreen)
        window_rows = [
            _Row(
                "Window size",
                "Used when not in fullscreen",
                seg(420, [f"{a}×{b}" for a, b in WINDOW_PRESETS], size_index, self._set_size),
            ),
            _Row("Fullscreen", "Also toggled any time with F11", self.fullscreen_toggle),
        ]
        self.rows = [
            _Row(
                "Theme",
                "Dark or light colors everywhere",
                seg(220, ["Dark", "Light"], 0 if s.theme == "dark" else 1, self._set_theme),
            ),
            *([] if IS_BROWSER else window_rows),  # the browser owns the window
            _Row(
                "Developer mode",
                "FPS/debug overlay · F5 reloads the current app",
                toggle(s.developer_mode, self._set_developer),
            ),
            _Row("Animations", "Screen transitions", toggle(s.transitions, self._set_transitions)),
            _Row(
                "Controls",
                "Rebind keys · gamepads work automatically",
                Button(t, (right - 190, 0, 190, 40), "Customize", self._open_controls),
            ),
            _Row("High scores", "Permanently delete every saved score", self.reset_btn),
        ]
        self.panel.height = len(self.rows) * ROW_HEIGHT + t.space.md * 2
        for i, row in enumerate(self.rows):
            row.control.rect.centery = self._row_rect(i).centery
        self.focus = -1  # no keyboard focus until an arrow key is pressed

    def _row_rect(self, i: int) -> pygame.Rect:
        return pygame.Rect(
            self.panel.x,
            self.panel.y + self.services.theme.space.md + i * ROW_HEIGHT,
            self.panel.width,
            ROW_HEIGHT,
        )

    # ------------------------------------------------------------------ setters
    def _apply(self) -> None:
        self.services.save_settings()

    def _set_theme(self, index: int) -> None:
        self.services.settings.theme = "dark" if index == 0 else "light"
        self._apply()

    def _set_size(self, index: int) -> None:
        self.services.settings.window_size = WINDOW_PRESETS[index]
        self._apply()

    def _set_fullscreen(self, value: bool) -> None:
        self.services.settings.fullscreen = value
        self._apply()

    def _set_developer(self, value: bool) -> None:
        self.services.settings.developer_mode = value
        self._apply()

    def _set_transitions(self, value: bool) -> None:
        self.services.settings.transitions = value
        self._apply()

    def _open_controls(self) -> None:
        from screens.controls import ControlsScreen

        self.manager.push(ControlsScreen(self.services))

    def _reset_scores(self) -> None:
        if not self._confirm_reset:
            self._confirm_reset = True
            self.reset_btn.text = "Click again to confirm"
            return
        self.services.storage.clear_scores()
        self._confirm_reset = False
        self.reset_btn.text = "Scores cleared"
        self.reset_btn.enabled = False

    def on_reveal(self) -> None:
        # Fullscreen may have been toggled with F11 while we were underneath.
        self.fullscreen_toggle.value = self.services.settings.fullscreen

    # ------------------------------------------------------------------ loop
    def _set_focus(self, index: int) -> None:
        self.focus = index % len(self.rows)
        for i, row in enumerate(self.rows):
            row.control.focused = i == self.focus

    def handle_event(self, event: pygame.event.Event) -> None:
        if self.header.handle_event(event):
            return
        if is_back(event):
            self.manager.pop()
            return
        is_tab = event.type == pygame.KEYDOWN and event.key == pygame.K_TAB
        if is_action(event, "up") or is_action(event, "down") or is_tab:
            step = -1 if is_action(event, "up") else 1
            self._set_focus(0 if self.focus < 0 else self.focus + step)
            return
        if event.type == pygame.MOUSEBUTTONDOWN:
            # Using the mouse hides the keyboard focus ring.
            self.focus = -1
            for row in self.rows:
                row.control.focused = False
        for row in self.rows:
            if row.control.handle_event(event):
                return

    def update(self, dt: float) -> None:
        self.header.update(dt)
        # Keep the fullscreen toggle in sync when F11 is used on this screen.
        self.fullscreen_toggle.value = self.services.settings.fullscreen
        for row in self.rows:
            row.control.update(dt)

    def draw(self, surface: Canvas) -> None:
        t = self.services.theme
        p = t.palette
        surface.fill(p.bg)
        self.header.draw(surface)
        draw_panel(surface, self.panel, t)
        for i, row in enumerate(self.rows):
            rect = self._row_rect(i)
            if i:
                y = rect.y
                gfx.line(surface, p.border, (rect.x + t.space.lg, y), (rect.right - t.space.lg, y))
            x = rect.x + t.space.lg
            draw.text(
                surface,
                row.title,
                t.font(t.size.body, "semibold"),
                p.text,
                (x, rect.centery - 2),
                "bottomleft",
            )
            draw.text(
                surface,
                row.hint,
                t.font(t.size.caption),
                p.text_muted,
                (x, rect.centery + 3),
                "topleft",
            )
            row.control.draw(surface)

        caption = t.font(t.size.caption)
        where = (
            "Saved in this browser" if IS_BROWSER else f"Data folder: {self.services.storage.root}"
        )
        data_dir = draw.fit_text(where, caption, 800)
        draw.text(
            surface,
            data_dir,
            caption,
            p.text_muted,
            (MARGIN_X, surface.get_height() - t.space.lg),
            "bottomleft",
        )
        hint = "↑↓ move · ←→ / Enter change · Esc back"
        draw.text(
            surface,
            hint,
            t.font(t.size.caption),
            p.text_muted,
            (surface.get_width() - MARGIN_X, surface.get_height() - t.space.lg),
            "bottomright",
        )
