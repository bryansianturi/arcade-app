"""Switchboard UI: a panel of glowing lights, par, hints and three board sizes."""

from __future__ import annotations

import math
import random

import pygame

from apps.switchboard.logic import Cell, Switchboard, neighbourhood, solve
from core import draw, gfx
from core.base_app import BaseApp
from core.canvas import Canvas
from core.input import DIRECTION_STEPS, action_of
from core.registry import register_app
from core.theme import Color, Theme, lerp_color
from core.widgets import Button, ButtonMenu, SegmentedControl, draw_panel

ACCENT: Color = (240, 171, 252)
ON: Color = (253, 224, 71)
OFF: Color = (44, 48, 66)
SIZES = (4, 5, 6)
BOARD = pygame.Rect(120, 80, 560, 560)
SIDE_X = 760
FLASH_SECONDS = 0.25


@register_app
class SwitchboardApp(BaseApp):
    """Press a light to flip it and its neighbours. Switch them all off."""

    @classmethod
    def draw_icon(cls, surface: Canvas, rect: pygame.Rect, theme: Theme) -> None:
        draw.rounded_rect(surface, rect, (30, 27, 46), theme.radius.md)
        cell = rect.width / 3.6
        for r in range(3):
            for c in range(3):
                on = (r, c) in {(0, 1), (1, 0), (1, 1), (1, 2), (2, 1)}
                box = pygame.FRect(0, 0, cell * 0.8, cell * 0.8)
                box.center = (rect.x + cell * (c + 0.8), rect.y + cell * (r + 0.8))
                gfx.rect(surface, ON if on else OFF, box, border_radius=cell * 0.2)

    # ------------------------------------------------------------------ lifecycle
    def on_enter(self) -> None:
        size = self.data.get("size", 5)
        self.size = size if size in SIZES else 5
        solved = self.data.get("solved", 0)
        self.total_solved = solved if isinstance(solved, int) else 0
        t = self.theme
        self.size_picker = SegmentedControl(
            t,
            (SIDE_X, 196, 300, 40),
            [f"{s} × {s}" for s in SIZES],
            SIZES.index(self.size),
            self._set_size,
        )
        self.buttons = [
            Button(t, (SIDE_X, 430, 144, 44), "Undo", self._undo),
            Button(t, (SIDE_X + 156, 430, 144, 44), "Hint", self._hint),
            Button(t, (SIDE_X, 486, 144, 44), "Restart", self._restart_puzzle),
            Button(
                t,
                (SIDE_X + 156, 486, 144, 44),
                "New puzzle",
                self._new_puzzle,
                "primary",
                accent=ACCENT,
            ),
        ]
        self.time = 0.0
        self.cursor: Cell = (0, 0)
        self.keyboard = False
        self._new_puzzle()

    def on_exit(self) -> None:
        self.data["size"], self.data["solved"] = self.size, self.total_solved
        self.data.save()

    def restart(self) -> None:
        self._restart_puzzle()

    def _set_size(self, index: int) -> None:
        self.size = SIZES[index]
        self._new_puzzle()

    def _new_puzzle(self) -> None:
        self.board = Switchboard.random(self.size, random.Random())
        self.start = set(self.board.lights)
        self.par = len(solve(self.size, self.start) or [])
        self.flashes: dict[Cell, float] = {}
        self.hint: Cell | None = None
        self.menu: ButtonMenu | None = None
        self.cursor = (min(self.cursor[0], self.size - 1), min(self.cursor[1], self.size - 1))

    def _restart_puzzle(self) -> None:
        self.board = Switchboard(self.size, set(self.start))
        self.hint = None
        self.menu = None

    def _undo(self) -> None:
        if self.menu is None:
            self.board.undo()
            self.hint = None

    def _hint(self) -> None:
        if self.menu is not None:
            return
        presses = solve(self.size, self.board.lights) or []
        self.hint = presses[0] if presses else None

    def _press(self, cell: Cell) -> None:
        if self.menu is not None:
            return
        self.board.press(cell)
        for n in neighbourhood(self.size, cell):
            self.flashes[n] = FLASH_SECONDS
        if self.hint is not None:
            self.hint = None
        if self.board.solved:
            self._on_solved()

    def _on_solved(self) -> None:
        self.total_solved += 1
        self.unlock("solve_1")
        if self.board.presses <= self.par:
            self.unlock("par")
        if self.size == 6:
            self.unlock("big")
        self.menu = ButtonMenu(
            self.theme,
            (BOARD.centerx, BOARD.centery + 40),
            [("Next puzzle", self._new_puzzle)],
            accent=ACCENT,
        )

    # ------------------------------------------------------------------ geometry
    def cell_rect(self, cell: Cell) -> pygame.Rect:
        step = BOARD.width // self.size
        return pygame.Rect(BOARD.x + cell[1] * step, BOARD.y + cell[0] * step, step, step).inflate(
            -12, -12
        )

    # ------------------------------------------------------------------ events
    def handle_event(self, event: pygame.event.Event) -> None:
        if self.menu is not None:
            self.menu.handle_event(event)
            return
        for widget in (self.size_picker, *self.buttons):
            if widget.handle_event(event):
                return
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self.keyboard = False
            for r in range(self.size):
                for c in range(self.size):
                    if self.cell_rect((r, c)).collidepoint(event.pos):
                        self._press((r, c))
                        return
        elif event.type == pygame.KEYDOWN and event.key in (pygame.K_u, pygame.K_h, pygame.K_n):
            {pygame.K_u: self._undo, pygame.K_h: self._hint, pygame.K_n: self._new_puzzle}[
                event.key
            ]()
        else:
            action = action_of(event)
            if action in DIRECTION_STEPS:
                if self.keyboard:
                    dc, dr = DIRECTION_STEPS[action]
                    self.cursor = (
                        (self.cursor[0] + dr) % self.size,
                        (self.cursor[1] + dc) % self.size,
                    )
                self.keyboard = True
            elif action == "action" and not event.repeat:
                self.keyboard = True
                self._press(self.cursor)

    def update(self, dt: float) -> None:
        self.time += dt
        self.flashes = {k: v - dt for k, v in self.flashes.items() if v - dt > 0}
        for widget in (self.size_picker, *self.buttons):
            widget.update(dt)
        self.buttons[0].enabled = bool(self.board._undo) and self.menu is None
        if self.menu is not None:
            self.menu.update(dt)

    # ------------------------------------------------------------------ drawing
    def draw(self, surface: Canvas) -> None:
        t = self.theme
        p = t.palette
        surface.fill(p.bg)
        panel = BOARD.inflate(36, 36)
        draw.shadow(surface, panel, t.radius.lg, p.shadow, (0, 8), 16)
        draw.rounded_rect(surface, panel, (24, 22, 36), t.radius.lg)
        for r in range(self.size):
            for c in range(self.size):
                self._draw_light(surface, (r, c))
        self._draw_side(surface, t)
        if self.menu is not None:
            draw.overlay(surface, p.overlay)
            box = pygame.Rect(0, 0, 380, 130 + self.menu.rect.height)
            box.midbottom = (self.menu.rect.centerx, self.menu.rect.bottom + 28)
            draw_panel(surface, box, t)
            draw.text(
                surface,
                "Lights out!",
                t.font(t.size.heading, "bold"),
                p.text,
                (box.centerx, box.y + 26),
                "midtop",
            )
            sub = f"{self.board.presses} presses · par {self.par}"
            good = self.board.presses <= self.par
            draw.text(
                surface,
                sub + (" · perfect!" if good else ""),
                t.font(t.size.label, "semibold"),
                p.success if good else p.text_muted,
                (box.centerx, box.y + 72),
                "midtop",
            )
            self.menu.draw(surface)

    def _draw_light(self, surface: Canvas, cell: Cell) -> None:
        rect = self.cell_rect(cell)
        on = cell in self.board.lights
        flash = self.flashes.get(cell, 0.0) / FLASH_SECONDS
        grow = round(6 * math.sin(flash * math.pi))
        rect = rect.inflate(grow, grow)
        if on:
            glow = 0.85 + 0.15 * math.sin(self.time * 3 + cell[0] + cell[1])
            draw.rounded_rect(
                surface, rect.inflate(14, 14), lerp_color((24, 22, 36), ON, 0.18 * glow), 20
            )
            draw.rounded_rect(surface, rect, ON, 14)
            draw.rounded_rect(
                surface, rect.inflate(-rect.width * 0.4, -rect.height * 0.4), (255, 251, 222), 10
            )
        else:
            draw.rounded_rect(surface, rect, OFF, 14)
            draw.rounded_rect(surface, rect, (58, 63, 84), 14, 2)
        if cell == self.hint:
            draw.rounded_rect(surface, rect.inflate(10, 10), ACCENT, 18, 4)
        if self.keyboard and cell == self.cursor:
            draw.rounded_rect(surface, rect.inflate(10, 10), (96, 165, 250), 18, 3)

    def _draw_side(self, surface: Canvas, t: Theme) -> None:
        p = t.palette
        x = SIDE_X
        draw.text(surface, "Switchboard", t.font(t.size.heading, "bold"), p.text, (x, 80))
        draw.text(surface, "Turn every light off.", t.font(t.size.label), p.text_muted, (x, 126))
        draw.text(
            surface,
            "Each press flips a light and its neighbours.",
            t.font(t.size.label),
            p.text_muted,
            (x, 150),
        )
        self.size_picker.draw(surface)
        stats = (
            ("Presses", str(self.board.presses)),
            ("Par", str(self.par)),
            ("Lights on", str(len(self.board.lights))),
        )
        for i, (label, value) in enumerate(stats):
            sx = x + i * 104
            draw.text(
                surface, label.upper(), t.font(t.size.caption, "semibold"), p.text_muted, (sx, 272)
            )
            draw.text(surface, value, t.font(t.size.heading, "bold"), p.text, (sx, 294))
        draw.text(
            surface,
            f"{self.total_solved} solved so far",
            t.font(t.size.label),
            p.text_muted,
            (x, 370),
        )
        for button in self.buttons:
            button.draw(surface)
        draw.text(
            surface,
            "Click or arrows + Space · H hint · U undo · N new",
            t.font(t.size.caption),
            p.text_muted,
            (x, 556),
        )
