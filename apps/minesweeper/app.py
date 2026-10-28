"""Minesweeper UI: board rendering, mouse/keyboard input and result banner."""

from __future__ import annotations

import math
import random

import pygame

from apps.minesweeper.logic import DIFFICULTIES, Cell, Difficulty, Minefield
from core import draw, gfx
from core.base_app import BaseApp, format_score
from core.canvas import Canvas, mouse_pos
from core.input import direction, is_action
from core.registry import register_app
from core.theme import Color, Theme, lerp_color
from core.widgets import Button, SegmentedControl

ACCENT: Color = (202, 138, 4)
NUMBER_COLORS: tuple[Color, ...] = (
    (96, 165, 250),
    (74, 222, 128),
    (248, 113, 113),
    (167, 139, 250),
    (251, 191, 36),
    (45, 212, 191),
    (244, 114, 182),
    (148, 163, 184),
)
BOARD_AREA = pygame.Rect(48, 96, 1184, 584)
MAX_CELL = 56
HINT = "Left click reveal · Right click flag · Click a number to chord · Arrows, Space and F keys"


@register_app
class MinesweeperApp(BaseApp):
    """Clear the field without hitting a mine. The first click is always safe."""

    @classmethod
    def draw_icon(cls, surface: Canvas, rect: pygame.Rect, theme: Theme) -> None:
        draw.rounded_rect(surface, rect, ACCENT, theme.radius.md)
        _draw_mine(surface, rect.center, rect.width * 0.24, (30, 30, 36))

    # ------------------------------------------------------------------ lifecycle
    def on_enter(self) -> None:
        saved = self.data.get("difficulty")
        self.difficulty: Difficulty = saved if saved in DIFFICULTIES else "easy"
        t = self.theme
        self.picker = SegmentedControl(
            t,
            (1232 - 130 - 12 - 330, 28, 330, 40),
            [d.title() for d in DIFFICULTIES],
            DIFFICULTIES.index(self.difficulty),
            self._set_difficulty,
            accent=ACCENT,
        )
        self.new_btn = Button(
            t, (1232 - 130, 28, 130, 40), "New game", self._new_game, "primary", accent=ACCENT
        )
        self.cursor: Cell = (0, 0)
        self.keyboard_nav = False
        self.pressed: Cell | None = None
        self.new_best = False
        self.time = 0.0
        self._new_game()

    def restart(self) -> None:
        self._new_game()

    def _set_difficulty(self, index: int) -> None:
        self.picker.index = index
        self.difficulty = DIFFICULTIES[index]
        self.data["difficulty"] = self.difficulty
        self.data.save()
        self._new_game()

    def _new_game(self) -> None:
        self.field = Minefield.for_difficulty(self.difficulty, random.Random())
        f = self.field
        self.cell = min(MAX_CELL, BOARD_AREA.width // f.width, BOARD_AREA.height // f.height)
        self.board = pygame.Rect(0, 0, self.cell * f.width, self.cell * f.height)
        self.board.center = BOARD_AREA.center
        self.cursor = (f.width // 2, f.height // 2)
        self.new_best = False

    # ------------------------------------------------------------------ helpers
    def _cell_at(self, pos: tuple[int, int]) -> Cell | None:
        if not self.board.collidepoint(pos):
            return None
        return ((pos[0] - self.board.x) // self.cell, (pos[1] - self.board.y) // self.cell)

    def _cell_rect(self, cell: Cell) -> pygame.Rect:
        return pygame.Rect(
            self.board.x + cell[0] * self.cell,
            self.board.y + cell[1] * self.cell,
            self.cell,
            self.cell,
        )

    def _open(self, cell: Cell) -> None:
        """Reveal a hidden cell, or chord on a revealed number."""
        if cell in self.field.revealed:
            self.field.chord(cell)
        else:
            self.field.reveal(cell)
        self._after_move()

    def _after_move(self) -> None:
        if self.field.status == "won":
            seconds = max(1, round(self.field.elapsed))
            self.new_best = self.submit_score(seconds, self.difficulty)

    # ------------------------------------------------------------------ events
    def handle_event(self, event: pygame.event.Event) -> None:
        if self.picker.handle_event(event) or self.new_btn.handle_event(event):
            return
        if event.type == pygame.MOUSEMOTION:
            self.keyboard_nav = False
        elif event.type == pygame.MOUSEBUTTONDOWN:
            cell = self._cell_at(event.pos)
            if cell is None:
                return
            self.cursor = cell
            if event.button == 1:
                self.pressed = cell
            elif event.button == 3:
                self.field.toggle_flag(cell)
        elif event.type == pygame.MOUSEBUTTONUP:
            cell = self._cell_at(event.pos)
            if event.button == 1 and cell is not None and cell == self.pressed:
                self._open(cell)
            elif event.button == 2 and cell is not None:
                self.field.chord(cell)
                self._after_move()
            if event.button == 1:
                self.pressed = None
        else:
            self._handle_key(event)

    def _handle_key(self, event: pygame.event.Event) -> None:
        f = self.field
        if (step := direction(event)) is not None:
            dx, dy = step
            if self.keyboard_nav:
                x, y = self.cursor
                self.cursor = (max(0, min(f.width - 1, x + dx)), max(0, min(f.height - 1, y + dy)))
            self.keyboard_nav = True
        elif is_action(event, "action", repeat=False):
            self.keyboard_nav = True
            self._open(self.cursor)
        elif event.type != pygame.KEYDOWN:
            return
        elif event.key == pygame.K_f:
            self.keyboard_nav = True
            f.toggle_flag(self.cursor)
        elif event.key == pygame.K_n:
            self._new_game()

    def update(self, dt: float) -> None:
        self.time += dt
        self.field.tick(dt)
        self.picker.update(dt)
        self.new_btn.update(dt)

    # ------------------------------------------------------------------ drawing
    def draw(self, surface: Canvas) -> None:
        t = self.theme
        p = t.palette
        surface.fill(p.bg)
        draw.text(
            surface, "Minesweeper", t.font(t.size.heading, "bold"), p.text, (48, 48), "midleft"
        )
        self._draw_stats(surface, t)
        self.picker.draw(surface)
        self.new_btn.draw(surface)

        frame = self.board.inflate(16, 16)
        draw.shadow(surface, frame, t.radius.lg, p.shadow, (0, 8), 16)
        draw.rounded_rect(surface, frame, p.surface, t.radius.lg)
        hover = None if self.keyboard_nav else self._cell_at(mouse_pos())
        for y in range(self.field.height):
            for x in range(self.field.width):
                self._draw_cell(surface, t, (x, y), hover)
        if self.keyboard_nav and not self.field.finished:
            ring = self._cell_rect(self.cursor).inflate(2, 2)
            draw.rounded_rect(surface, ring, ACCENT, 6, 3)
        self._draw_banner(surface, t)

    def _draw_stats(self, surface: Canvas, t: Theme) -> None:
        p = t.palette
        font = t.font(t.size.title, "bold")
        f = self.field
        pill = pygame.Rect(0, 0, 110, 40)
        pill.midright = (self.picker.rect.x - 24, 48)
        timer = pill.copy()
        mines = pill.move(-pill.width - 12, 0)
        for rect in (mines, timer):
            draw.rounded_rect(surface, rect, p.surface_alt, t.radius.pill)
        _draw_mine(surface, (mines.x + 24, mines.centery), 8, p.text_muted)
        draw.text(
            surface, str(f.mines_left), font, p.text, (mines.right - 18, mines.centery), "midright"
        )
        # A simple clock: circle and two hands.
        c = (timer.x + 24, timer.centery)
        gfx.circle(surface, p.text_muted, c, 9, 2)
        gfx.line(surface, p.text_muted, c, (c[0], c[1] - 5), 2)
        gfx.line(surface, p.text_muted, c, (c[0] + 4, c[1]), 2)
        draw.text(
            surface,
            format_score(f.elapsed, "time"),
            font,
            p.text,
            (timer.right - 18, timer.centery),
            "midright",
        )

    def _draw_cell(self, surface: Canvas, t: Theme, cell: Cell, hover: Cell | None) -> None:
        p = t.palette
        f = self.field
        rect = self._cell_rect(cell)
        tile = rect.inflate(-2, -2)
        radius = max(3, self.cell // 8)
        lost = f.status == "lost"

        if cell in f.revealed or (lost and cell in f.mines and cell not in f.flags):
            bg = lerp_color(p.surface, p.bg, 0.55)
            if cell == f.exploded:
                bg = p.danger
            gfx.rect(surface, bg, tile, border_radius=radius)
            if cell in f.mines:
                color = (255, 255, 255) if cell == f.exploded else p.text_muted
                _draw_mine(surface, rect.center, self.cell * 0.22, color)
                return
            n = f.adjacent_mines(cell)
            if n:
                color = NUMBER_COLORS[n - 1]
                if t.mode == "light":
                    color = lerp_color(color, (0, 0, 0), 0.3)
                font = t.font(max(12, round(self.cell * 0.55)), "bold")
                draw.text(surface, str(n), font, color, rect.center, "center")
            return

        pressed = cell == self.pressed and cell == hover and not f.finished
        base = lerp_color(p.surface_hover, ACCENT, 0.08)
        if pressed:
            base = lerp_color(p.surface, p.bg, 0.4)
        elif cell == hover and not f.finished:
            base = lerp_color(base, ACCENT, 0.18)
        gfx.rect(surface, base, tile, border_radius=radius)
        if not pressed:
            # Light top edge for a subtle raised look.
            top = pygame.Rect(tile.x + 2, tile.y + 1, tile.width - 4, 2)
            gfx.rect(surface, lerp_color(base, (255, 255, 255), 0.12), top, border_radius=1)
        if cell in f.flags:
            _draw_flag(surface, rect, self.cell, p.danger, p.text)
            if lost and cell not in f.mines:  # wrong flag
                k = self.cell * 0.28
                cx, cy = rect.center
                gfx.line(surface, p.text, (cx - k, cy - k), (cx + k, cy + k), 3)
                gfx.line(surface, p.text, (cx - k, cy + k), (cx + k, cy - k), 3)

    def _draw_banner(self, surface: Canvas, t: Theme) -> None:
        p = t.palette
        f = self.field
        font = t.font(t.size.label, "semibold")
        if f.status == "lost":
            text, color = "Boom! Press N or click New game to try again.", p.danger
        elif f.status == "won":
            time_text = format_score(max(1, round(f.elapsed)), "time")
            best = " · New best time!" if self.new_best else ""
            text, color = f"Cleared in {time_text}{best}", p.success
        else:
            text = HINT
            color, font = p.text_muted, t.font(t.size.caption)
        draw.text(surface, text, font, color, (640, 704), "center")


def _draw_mine(surface: Canvas, center: tuple[float, float], r: float, color: Color) -> None:
    cx, cy = center
    for i in range(8):
        a = i * math.pi / 4
        gfx.line(
            surface,
            color,
            (cx + math.cos(a) * r * 0.6, cy + math.sin(a) * r * 0.6),
            (cx + math.cos(a) * r * 1.35, cy + math.sin(a) * r * 1.35),
            max(2, round(r / 4)),
        )
    gfx.circle(surface, color, (cx, cy), r)
    gfx.circle(surface, (255, 255, 255), (cx - r * 0.35, cy - r * 0.35), max(1.0, r * 0.22))


def _draw_flag(surface: Canvas, rect: pygame.Rect, size: int, flag: Color, pole: Color) -> None:
    u = size / 10
    x = rect.x + rect.width * 0.42
    top = rect.y + 2.4 * u
    bottom = rect.bottom - 2.4 * u
    gfx.line(surface, pole, (x, top), (x, bottom), max(2, round(u * 0.5)))
    gfx.polygon(surface, flag, [(x, top), (x + 3.6 * u, top + 1.6 * u), (x, top + 3.2 * u)])
    gfx.line(surface, pole, (x - 1.8 * u, bottom), (x + 1.8 * u, bottom), max(2, round(u * 0.5)))
