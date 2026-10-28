"""Controls screen: rebind the shared actions and see connected gamepads."""

from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING

import pygame

from core import draw, gfx
from core.canvas import Canvas
from core.input import ACTION_LABELS, ACTIONDOWN, ACTIONS, SLOTS, Action, key_label
from core.scene_manager import Scene
from core.widgets import Button, draw_panel
from screens.common import MARGIN_X, SubpageHeader, is_back

if TYPE_CHECKING:
    from core.services import Services

ROW_HEIGHT = 64
PANEL_WIDTH = 820
SLOT_WIDTH = 170
CANCEL_KEYS = (pygame.K_ESCAPE,)
CLEAR_KEYS = (pygame.K_BACKSPACE, pygame.K_DELETE)


class ControlsScreen(Scene):
    """A grid of key slots: pick one, then press the key to bind."""

    def __init__(self, services: Services) -> None:
        super().__init__(services)
        t = services.theme
        self.header = SubpageHeader(t, "Controls", self.manager.pop)
        w, _ = self.manager.size
        self.panel = pygame.Rect((w - PANEL_WIDTH) // 2, 116, PANEL_WIDTH, 0)
        self.panel.height = len(ACTIONS) * ROW_HEIGHT + t.space.md * 2
        self.slots: list[list[Button]] = []
        for i, action in enumerate(ACTIONS):
            row = []
            for slot in range(SLOTS):
                x = self.panel.right - t.space.lg - (SLOTS - slot) * (SLOT_WIDTH + t.space.sm)
                rect = pygame.Rect(x + t.space.sm, 0, SLOT_WIDTH, 40)
                rect.centery = self._row_rect(i).centery
                row.append(Button(t, rect, "", partial(self._capture, action, slot)))
            self.slots.append(row)
        self.reset_btn = Button(
            t,
            (self.panel.right - 200, self.panel.bottom + 20, 200, 40),
            "Reset to defaults",
            self._reset,
            "ghost",
        )
        self.cursor = (-1, 0)  # (row, slot); -1 = no keyboard focus yet
        self.capturing: tuple[Action, int] | None = None
        self.message = ""
        self._swallow: int | None = None  # key just bound: ignore its own action event
        self._refresh()

    def _row_rect(self, i: int) -> pygame.Rect:
        return pygame.Rect(
            self.panel.x,
            self.panel.y + self.services.theme.space.md + i * ROW_HEIGHT,
            self.panel.width,
            ROW_HEIGHT,
        )

    # ------------------------------------------------------------------ binding
    def _refresh(self) -> None:
        inp = self.services.input
        for action, row in zip(ACTIONS, self.slots, strict=True):
            keys = inp.keys_for(action)
            for slot, button in enumerate(row):
                capturing = self.capturing == (action, slot)
                button.text = (
                    "Press a key…"
                    if capturing
                    else key_label(keys[slot])
                    if slot < len(keys)
                    else "—"
                )
                button.variant = "primary" if capturing else "secondary"
        r, s = self.cursor
        for i, row in enumerate(self.slots):
            for j, button in enumerate(row):
                button.focused = (i, j) == (r, s)

    def _capture(self, action: Action, slot: int) -> None:
        self.capturing = (action, slot)
        self.cursor = (ACTIONS.index(action), slot) if self.cursor[0] >= 0 else self.cursor
        self.message = "Press a key · Esc cancel · Backspace clear"
        self._refresh()

    def _finish(self, key: int) -> None:
        assert self.capturing is not None
        action, slot = self.capturing
        self.capturing = None
        inp = self.services.input
        self._swallow = key
        try:
            if key in CLEAR_KEYS:
                inp.clear(action, slot)
                self.message = f"Cleared a key for {ACTION_LABELS[action]}"
            elif key not in CANCEL_KEYS:
                inp.bind(action, slot, key)
                self.message = f"{key_label(key)} → {ACTION_LABELS[action]}"
            else:
                self.message = ""
        except ValueError as exc:
            self.message = str(exc)
        self.services.save_input()
        self._refresh()

    def _reset(self) -> None:
        self.services.input.reset()
        self.services.save_input()
        self.message = "Default controls restored"
        self._refresh()

    # ------------------------------------------------------------------ loop
    def handle_event(self, event: pygame.event.Event) -> None:
        if self.capturing is not None:
            if event.type == pygame.KEYDOWN:
                self._finish(event.key)
            elif event.type == pygame.MOUSEBUTTONDOWN:
                self.capturing = None
                self.message = ""
                self._refresh()
            return
        if event.type == ACTIONDOWN and event.key is not None and event.key == self._swallow:
            return
        if event.type == pygame.KEYUP and event.key == self._swallow:
            self._swallow = None
        if self.header.handle_event(event) or self.reset_btn.handle_event(event):
            return
        if is_back(event):
            self.manager.pop()
            return
        if event.type == ACTIONDOWN and event.action in ("up", "down", "left", "right"):
            r, s = self.cursor
            if r < 0:
                r, s = 0, 0
            elif event.action in ("up", "down"):
                r = (r + (1 if event.action == "down" else -1)) % len(ACTIONS)
            else:
                s = (s + (1 if event.action == "right" else -1)) % SLOTS
            self.cursor = (r, s)
            self._refresh()
            return
        if event.type == pygame.MOUSEBUTTONDOWN:
            self.cursor = (-1, 0)
            self._refresh()
        for row in self.slots:
            for button in row:
                if button.handle_event(event):
                    return

    def update(self, dt: float) -> None:
        self.header.update(dt)
        self.reset_btn.update(dt)
        for row in self.slots:
            for button in row:
                button.update(dt)

    def draw(self, surface: Canvas) -> None:
        t = self.services.theme
        p = t.palette
        surface.fill(p.bg)
        self.header.draw(surface)
        draw_panel(surface, self.panel, t)
        caption = t.font(t.size.caption, "semibold")
        for slot in range(SLOTS):
            x = self.slots[0][slot].rect.centerx
            label = "Primary" if slot == 0 else "Alternative"
            draw.text(
                surface, label.upper(), caption, p.text_muted, (x, self.panel.y - 10), "midbottom"
            )
        for i, action in enumerate(ACTIONS):
            rect = self._row_rect(i)
            if i:
                gfx.line(
                    surface,
                    p.border,
                    (rect.x + t.space.lg, rect.y),
                    (rect.right - t.space.lg, rect.y),
                )
            draw.text(
                surface,
                ACTION_LABELS[action],
                t.font(t.size.body, "semibold"),
                p.text,
                (rect.x + t.space.lg, rect.centery),
                "midleft",
            )
            for button in self.slots[i]:
                button.draw(surface)
        self.reset_btn.draw(surface)

        pads = self.services.input.gamepads.connected
        lines = [
            "Gamepad: "
            + (", ".join(pads) if pads else "none connected")
            + " · D-pad / left stick move · A confirm · B / Start pause",
        ]
        if self.message:
            lines.insert(0, self.message)
        for j, line in enumerate(lines):
            draw.text(
                surface,
                draw.fit_text(line, t.font(t.size.caption), PANEL_WIDTH - 220),
                t.font(t.size.caption, "semibold" if j == 0 and self.message else "regular"),
                p.text if j == 0 and self.message else p.text_muted,
                (self.panel.x, self.panel.bottom + 30 + j * 22),
                "midleft",
            )
        draw.text(
            surface,
            "Arrows move · Enter rebind · Esc back · F5, F11 and F12 are reserved",
            t.font(t.size.caption),
            p.text_muted,
            (surface.get_width() - MARGIN_X, surface.get_height() - t.space.lg),
            "bottomright",
        )
