"""Tic-tac-toe UI: animated marks, CPU turn delay, settings and a running tally."""

from __future__ import annotations

import math
import random

import pygame

from apps.tictactoe.logic import Level, Mark, TicTacToe, winning_line
from core import draw, gfx
from core.base_app import BaseApp
from core.canvas import Canvas, mouse_pos
from core.input import direction, is_action
from core.registry import register_app
from core.theme import Color, Theme, lerp_color
from core.widgets import Button, SegmentedControl

ACCENT: Color = (71, 85, 105)
X_COLOR: Color = (56, 189, 248)
O_COLOR: Color = (244, 114, 182)
CELL = 168
BOARD = pygame.Rect(140, 108, CELL * 3, CELL * 3)
SIDE_X = BOARD.right + 90
CPU_DELAY = 0.45
DRAW_SECONDS = 0.22
LEVELS: tuple[Level, ...] = ("easy", "unbeatable")

NUMBER_KEYS = {getattr(pygame, f"K_{n}"): n - 1 for n in range(1, 10)} | {
    getattr(pygame, f"K_KP{n}"): n - 1 for n in range(1, 10)
}


def cell_rect(index: int) -> pygame.Rect:
    return pygame.Rect(BOARD.x + (index % 3) * CELL, BOARD.y + (index // 3) * CELL, CELL, CELL)


def draw_x(surface: Canvas, rect: pygame.Rect, progress: float, width: int) -> None:
    """Draw an X whose two strokes appear one after the other as ``progress`` goes 0→1."""
    inset = rect.width * 0.26
    strokes = (
        ((rect.x + inset, rect.y + inset), (rect.right - inset, rect.bottom - inset)),
        ((rect.right - inset, rect.y + inset), (rect.x + inset, rect.bottom - inset)),
    )
    for i, (a, b) in enumerate(strokes):
        k = max(0.0, min(1.0, progress * 2 - i))
        if k <= 0:
            continue
        end = (a[0] + (b[0] - a[0]) * k, a[1] + (b[1] - a[1]) * k)
        draw.thick_line(surface, X_COLOR, a, end, width)


def draw_o(surface: Canvas, rect: pygame.Rect, progress: float, width: int) -> None:
    radius = rect.width * 0.27
    if progress >= 1:
        gfx.circle(surface, O_COLOR, rect.center, radius, width)
        return
    box = pygame.Rect(0, 0, radius * 2, radius * 2)
    box.center = rect.center
    start = math.pi / 2
    gfx.arc(surface, O_COLOR, box, start, start + math.tau * progress, width)


@register_app
class TicTacToeApp(BaseApp):
    """Three in a row against a computer that is either easy or unbeatable."""

    @classmethod
    def draw_icon(cls, surface: Canvas, rect: pygame.Rect, theme: Theme) -> None:
        draw.rounded_rect(surface, rect, (30, 41, 59), theme.radius.md)
        half = rect.inflate(-rect.width // 2, -rect.height // 2)
        draw_x(surface, half.move(-rect.width // 6, -rect.height // 6).inflate(8, 8), 1, 3)
        draw_o(surface, half.move(rect.width // 6, rect.height // 6).inflate(8, 8), 1, 3)

    # ------------------------------------------------------------------ lifecycle
    def on_enter(self) -> None:
        t = self.theme
        level = self.data.get("level", "unbeatable")
        self.level: Level = level if level in LEVELS else "unbeatable"
        self.human_first = bool(self.data.get("human_first", True))
        self.level_picker = SegmentedControl(
            t,
            (SIDE_X, 214, 340, 40),
            ["Easy", "Unbeatable"],
            LEVELS.index(self.level),
            self._set_level,
            accent=ACCENT,
        )
        self.first_picker = SegmentedControl(
            t,
            (SIDE_X, 300, 340, 40),
            ["You start", "CPU starts"],
            0 if self.human_first else 1,
            self._set_first,
            accent=ACCENT,
        )
        self.new_btn = Button(
            t, (SIDE_X, 540, 340, 52), "New round", self._new_round, "primary", accent=ACCENT
        )
        self.rng = random.Random()
        self.cursor = 4
        self.keyboard_nav = False
        self.time = 0.0
        self._new_round()

    def _set_level(self, index: int) -> None:
        self.level_picker.index = index
        self.level = LEVELS[index]
        self._save_prefs()
        self._new_round()

    def _set_first(self, index: int) -> None:
        self.first_picker.index = index
        self.human_first = index == 0
        self._save_prefs()
        self._new_round()

    def _save_prefs(self) -> None:
        self.data["level"] = self.level
        self.data["human_first"] = self.human_first
        self.data.save()

    def _new_round(self) -> None:
        human: Mark = "X" if self.human_first else "O"  # X always moves first
        self.game = TicTacToe(human=human, level=self.level, rng=self.rng)
        self.placed_at: dict[int, float] = {}
        self.cpu_timer = CPU_DELAY
        self.ended_at: float | None = None

    def restart(self) -> None:
        self._new_round()

    # ------------------------------------------------------------------ tally
    def tally(self) -> list[int]:
        """``[wins, draws, losses]`` for the current level."""
        raw = self.data.get("tally", {}).get(self.level, [0, 0, 0])
        return [int(v) for v in raw] if isinstance(raw, list) and len(raw) == 3 else [0, 0, 0]

    def _record_result(self) -> None:
        result = self.game.result
        if result is None:
            return
        self.ended_at = self.time
        tally = self.tally()
        tally[0 if result == self.game.human else 1 if result == "draw" else 2] += 1
        all_tallies = dict(self.data.get("tally", {}))
        all_tallies[self.level] = tally
        self.data["tally"] = all_tallies
        self.data.save()

    # ------------------------------------------------------------------ input
    def _play(self, index: int) -> None:
        if self.game.human_move(index):
            self.placed_at[index] = self.time
            self.cpu_timer = CPU_DELAY
            self._record_result()

    def handle_event(self, event: pygame.event.Event) -> None:
        for widget in (self.level_picker, self.first_picker, self.new_btn):
            if widget.handle_event(event):
                return
        if event.type == pygame.MOUSEMOTION:
            self.keyboard_nav = False
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.game.result is not None and BOARD.collidepoint(event.pos):
                self._new_round()  # click the finished board to play again
                return
            for i in range(9):
                if cell_rect(i).collidepoint(event.pos):
                    self._play(i)
        elif (step := direction(event)) is not None:
            if self.keyboard_nav:
                dx, dy = step
                x, y = self.cursor % 3, self.cursor // 3
                self.cursor = max(0, min(2, y + dy)) * 3 + max(0, min(2, x + dx))
            self.keyboard_nav = True
        elif is_action(event, "action", repeat=False):
            if self.game.result is not None:
                self._new_round()
            else:
                self.keyboard_nav = True
                self._play(self.cursor)
        elif event.type == pygame.KEYDOWN:
            if event.key in NUMBER_KEYS:
                self._play(NUMBER_KEYS[event.key])
            elif event.key == pygame.K_n:
                self._new_round()

    def update(self, dt: float) -> None:
        self.time += dt
        for widget in (self.level_picker, self.first_picker, self.new_btn):
            widget.update(dt)
        if self.game.cpu_to_move:
            self.cpu_timer -= dt
            if self.cpu_timer <= 0:
                index = self.game.cpu_move()
                if index is not None:
                    self.placed_at[index] = self.time
                self._record_result()

    # ------------------------------------------------------------------ drawing
    def _status(self) -> tuple[str, Color]:
        p = self.theme.palette
        result = self.game.result
        if result == "draw":
            return "It's a draw", p.text_muted
        if result == self.game.human:
            return "You win!", p.success
        if result is not None:
            return "The computer wins", p.danger
        if self.game.turn == self.game.human:
            return f"Your turn ({self.game.human})", p.text
        return "Thinking…", p.text_muted

    def draw(self, surface: Canvas) -> None:
        t = self.theme
        p = t.palette
        surface.fill(p.bg)
        frame = BOARD.inflate(40, 40)
        draw.shadow(surface, frame, t.radius.lg, p.shadow, (0, 8), 16)
        draw.rounded_rect(surface, frame, p.surface, t.radius.lg)

        hover = None
        mouse = mouse_pos()
        if self.game.result is None and self.game.turn == self.game.human:
            if self.keyboard_nav:
                hover = self.cursor
            else:
                hover = next((i for i in range(9) if cell_rect(i).collidepoint(mouse)), None)
        if hover is not None and not self.game.board[hover]:
            tint = cell_rect(hover).inflate(-16, -16)
            draw.rounded_rect(surface, tint, lerp_color(p.surface, ACCENT, 0.15), t.radius.md)

        for k in (1, 2):
            x = BOARD.x + k * CELL
            y = BOARD.y + k * CELL
            gfx.line(surface, p.border, (x, BOARD.y + 8), (x, BOARD.bottom - 8), 6)
            gfx.line(surface, p.border, (BOARD.x + 8, y), (BOARD.right - 8, y), 6)
        for i, cell in enumerate(self.game.board):
            if not cell:
                continue
            progress = min(1.0, (self.time - self.placed_at.get(i, -1.0)) / DRAW_SECONDS)
            (draw_x if cell == "X" else draw_o)(surface, cell_rect(i), progress, 14)
        self._draw_win_line(surface, t)
        self._draw_side(surface, t)

    def _draw_win_line(self, surface: Canvas, t: Theme) -> None:
        line = winning_line(self.game.board)
        if line is None or self.ended_at is None:
            return
        k = min(1.0, max(0.0, (self.time - self.ended_at - DRAW_SECONDS) / 0.25))
        if k <= 0:
            return
        a = pygame.Vector2(cell_rect(line[0]).center)
        b = pygame.Vector2(cell_rect(line[2]).center)
        direction = (b - a).normalize()
        a -= direction * 40
        b += direction * 40
        draw.thick_line(surface, t.palette.text, a, a + (b - a) * k, 10)

    def _draw_side(self, surface: Canvas, t: Theme) -> None:
        p = t.palette
        draw.text(surface, "Tic-tac-toe", t.font(t.size.heading, "bold"), p.text, (SIDE_X, 96))
        status, color = self._status()
        draw.text(surface, status, t.font(t.size.title, "semibold"), color, (SIDE_X, 146))
        for label, y in (("Computer", 190), ("Who starts", 276)):
            draw.text(
                surface,
                label.upper(),
                t.font(t.size.caption, "semibold"),
                p.text_muted,
                (SIDE_X, y),
            )
        self.level_picker.draw(surface)
        self.first_picker.draw(surface)

        wins, draws, losses = self.tally()
        for i, (label, value, color) in enumerate(
            (("You", wins, p.success), ("Draws", draws, p.text_muted), ("CPU", losses, p.danger))
        ):
            box = pygame.Rect(SIDE_X + i * 116, 380, 108, 84)
            draw.rounded_rect(surface, box, p.surface_alt, t.radius.md)
            draw.text(
                surface,
                label.upper(),
                t.font(t.size.caption, "semibold"),
                p.text_muted,
                (box.centerx, box.y + 14),
                "midtop",
            )
            draw.text(
                surface,
                str(value),
                t.font(t.size.heading, "bold"),
                color,
                (box.centerx, box.y + 36),
                "midtop",
            )
        draw.text(
            surface,
            f"Record vs {self.level} computer",
            t.font(t.size.caption),
            p.text_muted,
            (SIDE_X, 476),
        )
        self.new_btn.draw(surface)
        draw.text(
            surface,
            "Click or press 1–9 · Arrows + Enter · N new round",
            t.font(t.size.caption),
            p.text_muted,
            (SIDE_X, 612),
        )
