"""Paddle Duel UI: mode chooser, court, scores and match dialog."""

from __future__ import annotations

import random
from collections import deque
from collections.abc import Callable
from typing import Literal

import pygame

from apps.paddle_duel.logic import (
    BALL_R,
    FIELD_H,
    FIELD_W,
    PADDLE_H,
    PADDLE_MARGIN,
    PADDLE_W,
    WIN_SCORE,
    CpuController,
    Level,
    Paddle,
    PaddleDuel,
    Side,
)
from core import draw, gfx
from core.base_app import BaseApp
from core.canvas import Canvas
from core.registry import register_app
from core.theme import Color, Theme, lerp_color
from core.widgets import ButtonMenu, draw_panel

ACCENT: Color = (101, 163, 13)
SIDE_COLORS: dict[Side, Color] = {"left": (56, 189, 248), "right": (251, 146, 60)}
FIELD = pygame.Rect((1280 - FIELD_W) // 2, 84, FIELD_W, FIELD_H)

State = Literal["choose", "playing", "over"]


#: (up, down) keys per side in 2-player mode.
TWO_PLAYER_KEYS: dict[Side, tuple[int, int]] = {
    "left": (pygame.K_w, pygame.K_s),
    "right": (pygame.K_UP, pygame.K_DOWN),
}


@register_app
class PaddleDuelApp(BaseApp):
    """Keep the ball out of your goal. Two players or against the computer."""

    @classmethod
    def draw_icon(cls, surface: Canvas, rect: pygame.Rect, theme: Theme) -> None:
        draw.rounded_rect(surface, rect, (15, 23, 42), theme.radius.md)
        u = rect.width / 8
        gfx.rect(
            surface,
            SIDE_COLORS["left"],
            (rect.x + u, rect.y + 2 * u, 0.7 * u, 3 * u),
            border_radius=2,
        )
        gfx.rect(
            surface,
            SIDE_COLORS["right"],
            (rect.right - 1.7 * u, rect.y + 3 * u, 0.7 * u, 3 * u),
            border_radius=2,
        )
        gfx.circle(surface, (255, 255, 255), (rect.x + 4.6 * u, rect.y + 3.4 * u), 0.55 * u)

    # ------------------------------------------------------------------ lifecycle
    def on_enter(self) -> None:
        self.rng = random.Random()
        self.state: State = "choose"
        self.cpu: CpuController | None = None
        self.mode_label = ""
        self._level: Level | None = None
        self.game = PaddleDuel(self.rng)
        self.game.serve_timer = 10**9  # idle behind the chooser
        self.held: set[int] = set()
        self.trail: deque[tuple[float, float]] = deque(maxlen=8)
        self.flash: dict[Side, float] = {"left": 0.0, "right": 0.0}
        self.new_best = False
        self.menu: ButtonMenu | None = self._chooser()

    def _chooser(self) -> ButtonMenu:
        items: list[tuple[str, Callable[[], None]]] = [
            (f"vs CPU · {lvl.title()}", lambda lvl=lvl: self._start(lvl))  # type: ignore[misc]
            for lvl in ("easy", "medium", "hard")
        ]
        items.append(("2 Players", lambda: self._start(None)))
        return ButtonMenu(
            self.theme, (FIELD.centerx, FIELD.centery + 60), items, width=280, accent=ACCENT
        )

    def _start(self, level: Level | None) -> None:
        self.game = PaddleDuel(self.rng)
        self.cpu = CpuController(self.game.right, level, self.rng) if level else None
        self.mode_label = f"vs CPU · {level.title()}" if level else "2 Players"
        self._level = level
        self.state = "playing"
        self.menu = None
        self.trail.clear()

    def restart(self) -> None:
        if self.state == "choose":
            return
        self._start(self._level)

    def on_pause(self) -> None:
        self.held.clear()

    def on_exit(self) -> None:
        if self.state != "choose" and self.game.best_rally:
            self.submit_score(self.game.best_rally, "rally")

    # ------------------------------------------------------------------ input
    def _direction(self, side: Side) -> float:
        """-1 (up), 0 or 1 (down) for a human-controlled paddle.

        Against the CPU the player uses the shared up/down controls (keyboard or
        gamepad). Two players on one keyboard need separate keys, so 2-player mode
        uses fixed keys: W/S on the left and ↑/↓ on the right.
        """
        if self.cpu is not None:
            return float(self.input.held("down")) - float(self.input.held("up"))
        up, down = TWO_PLAYER_KEYS[side]
        return float(down in self.held) - float(up in self.held)

    def handle_event(self, event: pygame.event.Event) -> None:
        if self.menu is not None:
            self.menu.handle_event(event)
            return
        if event.type == pygame.KEYDOWN:
            self.held.add(event.key)
        elif event.type == pygame.KEYUP:
            self.held.discard(event.key)

    def _check_achievements(self) -> None:
        g = self.game
        self.unlock_milestones(g.best_rally, {"rally_15": 15})
        if g.winner == "left" and self.cpu is not None:
            self.unlock("beat_cpu")
            if self._level == "hard":
                self.unlock("beat_hard")

    def update(self, dt: float) -> None:
        self._check_achievements()
        for side in self.flash:
            self.flash[side] = max(0.0, self.flash[side] - dt)
        if self.menu is not None:
            self.menu.update(dt)
        if self.state != "playing":
            return
        g = self.game
        for paddle in (g.left, g.right):
            if paddle is g.right and self.cpu is not None:
                continue
            paddle.move = self._direction(paddle.side)
        if self.cpu is not None:
            self.cpu.update(g, dt)
        for event in g.update(dt):
            if event.kind == "hit" and event.side is not None:
                self.flash[event.side] = 0.15
            elif event.kind == "point":
                self.trail.clear()
        if not g.serving:
            self.trail.append((g.ball_x, g.ball_y))
        if g.winner is not None:
            self._match_over()

    def _match_over(self) -> None:
        self.state = "over"
        self.new_best = self.game.best_rally > 0 and self.submit_score(
            self.game.best_rally, "rally"
        )
        self.menu = ButtonMenu(
            self.theme,
            (FIELD.centerx, FIELD.centery + 70),
            [("Rematch", self.restart), ("Change mode", self._to_chooser)],
            accent=ACCENT,
        )

    def _to_chooser(self) -> None:
        self.state = "choose"
        self.menu = self._chooser()

    # ------------------------------------------------------------------ drawing
    def draw(self, surface: Canvas) -> None:
        t = self.theme
        p = t.palette
        g = self.game
        surface.fill(p.bg)
        court = (13, 20, 33) if t.mode == "dark" else (30, 41, 59)
        draw.shadow(surface, FIELD, t.radius.lg, p.shadow, (0, 8), 16)
        draw.rounded_rect(surface, FIELD, court, t.radius.lg)
        line = lerp_color(court, (255, 255, 255), 0.18)
        for dash_y in range(FIELD.y + 14, FIELD.bottom - 14, 28):
            gfx.rect(surface, line, (FIELD.centerx - 2, dash_y, 4, 14), border_radius=2)

        score_font = t.font(96, "bold")
        sides: tuple[tuple[Side, int], ...] = (
            ("left", FIELD.centerx - 90),
            ("right", FIELD.centerx + 90),
        )
        for side, score_x in sides:
            color = lerp_color(court, SIDE_COLORS[side], 0.5)
            draw.text(
                surface, str(g.scores[side]), score_font, color, (score_x, FIELD.y + 30), "midtop"
            )

        for i, (x, y) in enumerate(self.trail):
            k = (i + 1) / len(self.trail)
            gfx.circle(
                surface,
                lerp_color(court, (255, 255, 255), 0.35 * k),
                (FIELD.x + x, FIELD.y + y),
                BALL_R * k,
            )
        for paddle in (g.left, g.right):
            self._draw_paddle(surface, paddle)
        if (not g.serving and self.state == "playing") or self.state == "over":
            gfx.circle(surface, (255, 255, 255), (FIELD.x + g.ball_x, FIELD.y + g.ball_y), BALL_R)
        self._draw_hud(surface, t)

        if self.state == "choose" and self.menu is not None:
            self._card(surface, t, "Paddle Duel", f"First to {WIN_SCORE} wins")
            self.menu.draw(surface)
        elif self.state == "over" and self.menu is not None:
            assert g.winner is not None
            if self.cpu is not None:
                title = "You win!" if g.winner == "left" else "The CPU wins"
            else:
                title = f"{'Left' if g.winner == 'left' else 'Right'} player wins!"
            sub = (
                f"New best rally: {g.best_rally}!"
                if self.new_best
                else f"Longest rally {g.best_rally}"
            )
            self._card(surface, t, title, sub, good=self.new_best)
            self.menu.draw(surface)

    def _draw_paddle(self, surface: Canvas, paddle: Paddle) -> None:
        x = PADDLE_MARGIN if paddle.side == "left" else FIELD_W - PADDLE_MARGIN - PADDLE_W
        rect = pygame.Rect(
            FIELD.x + x, round(FIELD.y + paddle.y - PADDLE_H / 2), PADDLE_W, PADDLE_H
        )
        color = SIDE_COLORS[paddle.side]
        if self.flash[paddle.side] > 0:
            color = lerp_color(color, (255, 255, 255), self.flash[paddle.side] / 0.15 * 0.6)
            rect = rect.inflate(4, 4)
        gfx.rect(surface, color, rect, border_radius=PADDLE_W // 2)

    def _draw_hud(self, surface: Canvas, t: Theme) -> None:
        p = t.palette
        g = self.game
        y = FIELD.y - 30
        left_keys = self.input.labels("up", "down") if self.cpu is not None else "W / S"
        right_label = "CPU" if self.cpu is not None else "↑ / ↓"
        draw.text(
            surface,
            left_keys,
            t.font(t.size.label, "semibold"),
            SIDE_COLORS["left"],
            (FIELD.x, y),
            "midleft",
        )
        draw.text(
            surface,
            right_label,
            t.font(t.size.label, "semibold"),
            SIDE_COLORS["right"],
            (FIELD.right, y),
            "midright",
        )
        best = self.best_score("rally")
        best_text = f"Best rally {int(best.score)}" if best else "Best rally —"
        middle = (
            f"{self.mode_label} · Rally {g.rally} · {best_text}"
            if self.state != "choose"
            else best_text
        )
        draw.text(surface, middle, t.font(t.size.label), p.text_muted, (FIELD.centerx, y), "center")

    def _card(self, surface: Canvas, t: Theme, title: str, sub: str, good: bool = False) -> None:
        assert self.menu is not None
        p = t.palette
        draw.overlay(surface, p.overlay)
        panel = pygame.Rect(0, 0, 400, self.menu.rect.height + 150)
        panel.midbottom = (FIELD.centerx, self.menu.rect.bottom + 32)
        draw_panel(surface, panel, t)
        draw.text(
            surface,
            title,
            t.font(t.size.heading, "bold"),
            p.text,
            (panel.centerx, panel.y + 28),
            "midtop",
        )
        draw.text(
            surface,
            sub,
            t.font(t.size.label, "semibold" if good else "regular"),
            p.success if good else p.text_muted,
            (panel.centerx, panel.y + 74),
            "midtop",
        )
