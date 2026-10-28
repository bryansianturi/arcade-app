"""Snake UI: start screen, smooth interpolated rendering, game over dialog."""

from __future__ import annotations

import math
import random
from typing import Literal

import pygame

from apps.snake.logic import DOWN, LEFT, RIGHT, UP, Direction, SnakeGame
from core import draw, gfx
from core.base_app import BaseApp
from core.canvas import Canvas
from core.input import Action, action_of, is_action
from core.registry import register_app
from core.theme import Color, Theme, lerp_color
from core.widgets import ButtonMenu, SegmentedControl, draw_panel

ACCENT: Color = (46, 204, 113)
FOOD: Color = (255, 99, 132)
COLS, ROWS, CELL = 30, 20, 30
BOARD = pygame.Rect((1280 - COLS * CELL) // 2, 82, COLS * CELL, ROWS * CELL)
SHAKE_SECONDS = 0.35

DIRECTIONS: dict[Action, Direction] = {"up": UP, "down": DOWN, "left": LEFT, "right": RIGHT}


def direction_of(event: pygame.event.Event) -> Direction | None:
    action = action_of(event)
    return None if action is None else DIRECTIONS.get(action)


Mode = Literal["ready", "playing", "paused", "over"]
MODES = ("walls", "wrap")


@register_app
class SnakeApp(BaseApp):
    """Classic snake with walls or wrap-around edges."""

    @classmethod
    def draw_icon(cls, surface: Canvas, rect: pygame.Rect, theme: Theme) -> None:
        draw.rounded_rect(surface, rect, ACCENT, theme.radius.md)
        u = rect.width / 6
        path = [(1, 4.2), (1, 2.5), (3, 2.5), (3, 4.2), (5, 4.2), (5, 1.6)]
        pts = [(rect.x + x * u, rect.y + y * u) for x, y in path]
        dark = (16, 70, 42)
        gfx.lines(surface, dark, False, pts, max(3, round(u * 0.9)))
        for p in pts:
            gfx.circle(surface, dark, p, u * 0.45)
        gfx.circle(surface, FOOD, (rect.x + 1.4 * u, rect.y + 1.2 * u), u * 0.55)
        gfx.circle(surface, (255, 255, 255), (pts[-1][0], pts[-1][1] + u * 0.1), u * 0.18)

    def on_enter(self) -> None:
        self.wrap = bool(self.data.get("wrap", False))
        self.mode_picker = SegmentedControl(
            self.theme,
            (BOARD.centerx - 130, BOARD.centery + 40, 260, 40),
            ["Walls", "Wrap-around"],
            int(self.wrap),
            self._set_wrap,
            accent=ACCENT,
        )
        self.mode_picker.focused = True
        self.menu: ButtonMenu | None = None
        self.shake = 0.0
        self.time = 0.0
        self.new_best = False
        self._new_game()
        self.state: Mode = "ready"

    def _set_wrap(self, index: int) -> None:
        self.wrap = index == 1
        self.data["wrap"] = self.wrap
        self.data.save()
        self._new_game()

    @property
    def variant(self) -> str:
        return MODES[int(self.wrap)]

    def _new_game(self) -> None:
        self.game = SnakeGame(COLS, ROWS, self.wrap, random.Random())

    def _start(self) -> None:
        self._new_game()
        self.state = "playing"
        self.menu = None

    def _game_over(self) -> None:
        self.state = "over"
        self.shake = SHAKE_SECONDS
        self.new_best = self.game.score > 0 and self.submit_score(self.game.score, self.variant)
        self.menu = ButtonMenu(
            self.theme,
            (BOARD.centerx, BOARD.centery + 70),
            [("Play again", self._start), ("Change mode", self._to_ready)],
            accent=ACCENT,
        )

    def _to_ready(self) -> None:
        self._new_game()
        self.state = "ready"
        self.menu = None

    def on_pause(self) -> None:
        if self.state == "playing":
            self.state = "paused"

    # ------------------------------------------------------------------ events
    def handle_event(self, event: pygame.event.Event) -> None:
        if self.state == "over" and self.menu is not None:
            self.menu.handle_event(event)
            return
        if self.state == "ready":
            if self.mode_picker.handle_event(event):
                return
            if is_action(event, "action", repeat=False):
                self._start()
            elif (direction := direction_of(event)) is not None:
                self._start()
                self.game.turn(direction)
            return
        if event.type == pygame.KEYDOWN and event.key == pygame.K_p and self.state == "playing":
            self.pause()  # P is a shortcut for the pause menu
        elif self.state == "paused" and is_action(event, "action", repeat=False):
            self.state = "playing"
        elif self.state == "playing" and (direction := direction_of(event)) is not None:
            self.game.turn(direction)

    def _check_achievements(self) -> None:
        score = self.game.score
        self.unlock_milestones(score, {"first_bite": 1, "score_25": 25, "score_50": 50})
        if score >= 20 and not self.game.wrap:
            self.unlock("walls_20")

    def update(self, dt: float) -> None:
        self._check_achievements()
        self.time += dt
        self.shake = max(0.0, self.shake - dt)
        if self.state == "playing":
            self.game.update(dt)
            if not self.game.alive:
                self._game_over()
        if self.state == "ready":
            self.mode_picker.update(dt)
        if self.menu is not None:
            self.menu.update(dt)

    # ------------------------------------------------------------------ drawing
    def draw(self, surface: Canvas) -> None:
        t = self.theme
        p = t.palette
        surface.fill(p.bg)
        offset = (0, 0)
        if self.shake > 0:
            k = self.shake / SHAKE_SECONDS * 8
            offset = (round(math.sin(self.time * 90) * k), round(math.cos(self.time * 70) * k))
        board = BOARD.move(offset)
        self._draw_hud(surface, t)
        self._draw_board(surface, t, board)
        self._draw_food(surface, board)
        self._draw_snake(surface, board)

        if self.state == "ready":
            self._draw_card(
                surface,
                t,
                "Snake",
                f"{self.input.label('action')} to start · "
                f"{self.input.labels('left', 'right')} switch mode",
                140,
            )
            self.mode_picker.draw(surface)
        elif self.state == "paused":
            self._draw_card(surface, t, "Paused", f"{self.input.label('action')} to continue", 0)
        elif self.state == "over" and self.menu is not None:
            title = "Board cleared!" if self.game.won else "Game over"
            sub = "New high score!" if self.new_best else f"Score {self.game.score}"
            self._draw_card(
                surface, t, title, sub, self.menu.rect.height + 40, highlight=self.new_best
            )
            self.menu.draw(surface)

    def _draw_hud(self, surface: Canvas, t: Theme) -> None:
        p = t.palette
        y = BOARD.y - 50
        draw.text(surface, "Snake", t.font(t.size.heading, "bold"), p.text, (BOARD.x, y))
        best = self.best_score(self.variant)
        best_text = f"Best {int(best.score)}" if best else "Best —"
        mode = "Wrap-around" if self.wrap else "Walls"
        draw.text(
            surface,
            f"{mode} · {best_text}",
            t.font(t.size.label),
            p.text_muted,
            (BOARD.centerx, y + 18),
            "center",
        )
        draw.text(
            surface,
            str(self.game.score),
            t.font(t.size.heading, "bold"),
            ACCENT,
            (BOARD.right, y),
            "topright",
        )
        draw.text(
            surface,
            f"P or {self.input.label('pause')} pause",
            t.font(t.size.caption),
            p.text_muted,
            (BOARD.centerx, BOARD.bottom + 10),
            "midtop",
        )

    def _draw_board(self, surface: Canvas, t: Theme, board: pygame.Rect) -> None:
        p = t.palette
        draw.shadow(surface, board, t.radius.md, p.shadow, (0, 8), 16)
        draw.rounded_rect(surface, board, p.surface, t.radius.md)
        checker = lerp_color(p.surface, p.surface_alt, 0.45)
        for y in range(ROWS):
            for x in range(y % 2, COLS, 2):
                gfx.rect(surface, checker, (board.x + x * CELL, board.y + y * CELL, CELL, CELL))
        edge = ACCENT if self.wrap else p.border
        style_width = 2 if self.wrap else 3
        draw.rounded_rect(surface, board.inflate(4, 4), edge, t.radius.md + 2, style_width)

    def _cell_center(self, board: pygame.Rect, pos: tuple[float, float]) -> tuple[float, float]:
        return (board.x + (pos[0] + 0.5) * CELL, board.y + (pos[1] + 0.5) * CELL)

    def _draw_food(self, surface: Canvas, board: pygame.Rect) -> None:
        if self.game.food is None:
            return
        cx, cy = self._cell_center(board, self.game.food)
        r = CELL * 0.32 + math.sin(self.time * 6) * 1.5
        gfx.circle(surface, lerp_color(FOOD, (0, 0, 0), 0.25), (cx, cy + 2), r)
        gfx.circle(surface, FOOD, (cx, cy), r)
        gfx.circle(
            surface,
            lerp_color(FOOD, (255, 255, 255), 0.5),
            (cx - r * 0.35, cy - r * 0.35),
            r * 0.28,
        )
        gfx.ellipse(surface, ACCENT, (cx, cy - r - 6, 9, 6))

    def _segment_positions(self) -> list[tuple[float, float]]:
        """Interpolate between the last two steps so movement looks smooth."""
        game = self.game
        alpha = game.progress if self.state == "playing" else 1.0
        body = list(game.body)
        prev = game.prev_body
        out: list[tuple[float, float]] = []
        for i, (x, y) in enumerate(body):
            px, py = prev[i] if i < len(prev) else prev[-1]
            if abs(px - x) > 1 or abs(py - y) > 1:  # wrapped across an edge: don't smear
                px, py = x, y
            out.append((px + (x - px) * alpha, py + (y - py) * alpha))
        return out

    def _draw_snake(self, surface: Canvas, board: pygame.Rect) -> None:
        positions = self._segment_positions()
        n = len(positions)
        dead = not self.game.alive
        tail_color = lerp_color(ACCENT, (20, 60, 40), 0.55)
        for i in range(n - 1, -1, -1):
            cx, cy = self._cell_center(board, positions[i])
            color = lerp_color(ACCENT, tail_color, i / max(1, n - 1))
            if dead:
                color = lerp_color(color, (120, 120, 130), 0.6)
            size = CELL - 4 if i == 0 else CELL - 6 - min(6, i // 6)
            rect = pygame.Rect(0, 0, size, size)
            rect.center = (round(cx), round(cy))
            gfx.rect(surface, color, rect, border_radius=size // 3)
            # Bridge to the next segment so the body looks continuous.
            if i + 1 < n:
                nx, ny = self._cell_center(board, positions[i + 1])
                if abs(nx - cx) <= CELL and abs(ny - cy) <= CELL:
                    mid = pygame.Rect(0, 0, size, size)
                    mid.center = (round((cx + nx) / 2), round((cy + ny) / 2))
                    gfx.rect(surface, color, mid, border_radius=size // 3)
        self._draw_eyes(surface, board, positions[0])

    def _draw_eyes(self, surface: Canvas, board: pygame.Rect, head: tuple[float, float]) -> None:
        cx, cy = self._cell_center(board, head)
        dx, dy = self.game.direction
        px, py = -dy, dx  # perpendicular
        for side in (-1, 1):
            ex = cx + dx * 5 + px * 6 * side
            ey = cy + dy * 5 + py * 6 * side
            gfx.circle(surface, (255, 255, 255), (ex, ey), 4)
            if self.game.alive:
                gfx.circle(surface, (20, 24, 30), (ex + dx * 1.5, ey + dy * 1.5), 2)
            else:  # little x eyes
                for a, b in (((-2, -2), (2, 2)), ((-2, 2), (2, -2))):
                    gfx.line(
                        surface, (20, 24, 30), (ex + a[0], ey + a[1]), (ex + b[0], ey + b[1]), 2
                    )

    def _draw_card(
        self,
        surface: Canvas,
        t: Theme,
        title: str,
        sub: str,
        extra: int,
        highlight: bool = False,
    ) -> None:
        p = t.palette
        draw.overlay(surface, t.palette.overlay)
        panel = pygame.Rect(0, 0, 420, 130 + extra)
        panel.midtop = (BOARD.centerx, BOARD.centery - 120)
        draw_panel(surface, panel, t)
        draw.text(
            surface,
            title,
            t.font(t.size.heading, "bold"),
            p.text,
            (panel.centerx, panel.y + 34),
            "midtop",
        )
        draw.text(
            surface,
            sub,
            t.font(t.size.label, "semibold" if highlight else "regular"),
            p.success if highlight else p.text_muted,
            (panel.centerx, panel.y + 80),
            "midtop",
        )
