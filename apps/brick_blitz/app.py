"""Brick Blitz UI: bricks, paddle, ball trail, particles and HUD."""

from __future__ import annotations

import math
import random
from collections import deque
from dataclasses import dataclass
from typing import Literal

import pygame

from apps.brick_blitz.logic import (
    BALL_R,
    BRICK_H,
    BRICK_W,
    FIELD_H,
    FIELD_W,
    PADDLE_H,
    PADDLE_W,
    PADDLE_Y,
    BrickBlitz,
    Event,
)
from core import draw, gfx
from core.base_app import BaseApp
from core.canvas import Canvas
from core.registry import register_app
from core.theme import Color, Theme, lerp_color
from core.widgets import ButtonMenu, draw_panel

ACCENT: Color = (37, 99, 235)
ROW_COLORS: tuple[Color, ...] = (
    (251, 113, 133),
    (251, 146, 60),
    (250, 204, 21),
    (74, 222, 128),
    (45, 212, 191),
    (96, 165, 250),
    (167, 139, 250),
)
STEEL: Color = (100, 116, 139)
FIELD = pygame.Rect((1280 - FIELD_W) // 2, 62, FIELD_W, FIELD_H)
LEFT_KEYS = (pygame.K_LEFT, pygame.K_a)
RIGHT_KEYS = (pygame.K_RIGHT, pygame.K_d)

State = Literal["playing", "over"]


@dataclass
class Particle:
    x: float
    y: float
    vx: float
    vy: float
    life: float
    color: Color


@register_app
class BrickBlitzApp(BaseApp):
    """Keep the ball in play and clear every brick."""

    @classmethod
    def draw_icon(cls, surface: Canvas, rect: pygame.Rect, theme: Theme) -> None:
        draw.rounded_rect(surface, rect, (15, 23, 42), theme.radius.md)
        u = rect.width / 8
        for row, color in enumerate(ROW_COLORS[:3]):
            for col in range(3):
                r = pygame.Rect(rect.x + u + col * 2.1 * u, rect.y + u + row * 1.2 * u, 1.9 * u, u)
                gfx.rect(surface, color, r, border_radius=2)
        gfx.circle(surface, (255, 255, 255), (rect.x + 5 * u, rect.y + 5.3 * u), u * 0.5)
        gfx.rect(
            surface, ACCENT, (rect.x + 2 * u, rect.y + 6.6 * u, 4 * u, 0.6 * u), border_radius=3
        )

    def on_enter(self) -> None:
        self.rng = random.Random()
        self.game = BrickBlitz(self.rng)
        self.state: State = "playing"
        self.held: set[int] = set()
        self.particles: list[Particle] = []
        self.trail: deque[tuple[float, float]] = deque(maxlen=10)
        self.banner = 0.0
        self.time = 0.0
        self.menu: ButtonMenu | None = None
        self.new_best = False

    def restart(self) -> None:
        self.on_enter()

    def on_pause(self) -> None:
        self.held.clear()

    def _game_over(self) -> None:
        self.state = "over"
        self.new_best = self.game.score > 0 and self.submit_score(self.game.score)
        self.menu = ButtonMenu(
            self.theme,
            (FIELD.centerx, FIELD.centery + 70),
            [("Play again", self.restart), ("Back to menu", self.exit_to_launcher)],
            accent=ACCENT,
        )

    # ------------------------------------------------------------------ input
    def handle_event(self, event: pygame.event.Event) -> None:
        if self.menu is not None:
            self.menu.handle_event(event)
            return
        g = self.game
        if event.type == pygame.KEYDOWN:
            self.held.add(event.key)
            if event.key in (pygame.K_SPACE, pygame.K_UP, pygame.K_w):
                g.launch()
            if event.key in LEFT_KEYS + RIGHT_KEYS:
                g.target_x = None  # keyboard takes over from the mouse
        elif event.type == pygame.KEYUP:
            self.held.discard(event.key)
        elif event.type == pygame.MOUSEMOTION and event.rel != (0, 0):
            g.target_x = event.pos[0] - FIELD.x
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            g.launch()

    def update(self, dt: float) -> None:
        self.time += dt
        self.banner = max(0.0, self.banner - dt)
        self._update_particles(dt)
        if self.menu is not None:
            self.menu.update(dt)
        if self.state != "playing":
            return
        g = self.game
        g.move = int(any(k in self.held for k in RIGHT_KEYS)) - int(
            any(k in self.held for k in LEFT_KEYS)
        )
        for event in g.update(dt):
            self._on_event(event)
        if not g.attached:
            self.trail.append((g.ball_x, g.ball_y))
        else:
            self.trail.clear()
        if g.over:
            self._game_over()

    def _on_event(self, event: Event) -> None:
        if event.kind == "brick_broken":
            row = int((event.y - 70) // (BRICK_H + 6))
            self._burst(event.x, event.y, ROW_COLORS[row % len(ROW_COLORS)], 16)
        elif event.kind == "brick_hit":
            self._burst(event.x, event.y, STEEL if event.value < 0 else (255, 255, 255), 5)
        elif event.kind == "level_clear":
            self.banner = 1.6
        elif event.kind == "life_lost":
            self._burst(event.x, FIELD_H - 4, (251, 113, 133), 24)

    def _burst(self, x: float, y: float, color: Color, n: int) -> None:
        for _ in range(n):
            a = self.rng.uniform(0, math.tau)
            v = self.rng.uniform(60, 260)
            self.particles.append(
                Particle(x, y, math.cos(a) * v, math.sin(a) * v, self.rng.uniform(0.3, 0.7), color)
            )

    def _update_particles(self, dt: float) -> None:
        for p in self.particles:
            p.life -= dt
            p.x += p.vx * dt
            p.y += p.vy * dt
            p.vy += 500 * dt
        self.particles = [p for p in self.particles if p.life > 0]

    # ------------------------------------------------------------------ drawing
    def draw(self, surface: Canvas) -> None:
        t = self.theme
        p = t.palette
        g = self.game
        surface.fill(p.bg)
        self._draw_hud(surface, t)

        field = Canvas.new(FIELD.size, alpha=True)
        bg = (12, 17, 30) if t.mode == "dark" else (226, 232, 240)
        field.fill(bg)
        for brick in g.bricks:
            rect = pygame.Rect(round(brick.x), round(brick.y), round(BRICK_W), BRICK_H)
            if not brick.breakable:
                gfx.rect(field, STEEL, rect, border_radius=5)
                gfx.rect(field, lerp_color(STEEL, (255, 255, 255), 0.3), rect, 2, border_radius=5)
                continue
            color = ROW_COLORS[brick.row % len(ROW_COLORS)]
            # Damaged bricks fade towards the background.
            color = lerp_color(color, bg, 0.45 * (1 - brick.hp / brick.max_hp))
            gfx.rect(field, color, rect, border_radius=5)
            hi = pygame.Rect(rect.x + 4, rect.y + 3, rect.width - 8, 5)
            gfx.rect(field, lerp_color(color, (255, 255, 255), 0.35), hi, border_radius=3)
            for i in range(brick.hp - 1):  # pips show remaining extra hits
                gfx.circle(
                    field,
                    lerp_color(color, (0, 0, 0), 0.35),
                    (rect.centerx - 6 + i * 12, rect.centery + 2),
                    3,
                )

        for i, (x, y) in enumerate(self.trail):
            k = (i + 1) / len(self.trail)
            gfx.circle(field, lerp_color(bg, ACCENT, 0.5 * k), (x, y), BALL_R * k)
        paddle = pygame.Rect(0, 0, PADDLE_W, PADDLE_H)
        paddle.midtop = (round(g.paddle_x), PADDLE_Y)
        gfx.rect(field, ACCENT, paddle, border_radius=PADDLE_H // 2)
        ball_color = (255, 255, 255) if t.mode == "dark" else (15, 23, 42)
        gfx.circle(field, ball_color, (g.ball_x, g.ball_y), BALL_R)
        for part in self.particles:
            gfx.circle(
                field, lerp_color(bg, part.color, min(1.0, part.life * 2)), (part.x, part.y), 3
            )

        draw.round_corners(field, t.radius.lg)
        draw.shadow(surface, FIELD, t.radius.lg, p.shadow, (0, 8), 16)
        surface.blit(field, FIELD.topleft)

        if self.state == "playing" and g.attached:
            text = f"Level {g.level + 1}" if self.banner > 0 else "Space or click to launch"
            font = t.font(t.size.display if self.banner > 0 else t.size.title, "bold")
            draw.text(
                surface,
                text,
                font,
                ACCENT if self.banner > 0 else p.text_muted,
                (FIELD.centerx, FIELD.y + PADDLE_Y - 90),
                "center",
            )
        if self.menu is not None:
            self._draw_over(surface, t)

    def _draw_hud(self, surface: Canvas, t: Theme) -> None:
        p = t.palette
        g = self.game
        y = FIELD.y - 30
        draw.text(
            surface, f"{g.score:,}", t.font(t.size.heading, "bold"), ACCENT, (FIELD.x, y), "midleft"
        )
        best = self.best_score()
        best_text = f"Best {max(g.score, int(best.score) if best else 0):,}"
        draw.text(
            surface,
            f"Level {g.level + 1} · {best_text}",
            t.font(t.size.label),
            p.text_muted,
            (FIELD.centerx, y),
            "center",
        )
        for i in range(g.lives):
            gfx.circle(surface, ACCENT, (FIELD.right - 10 - i * 26, y), 8)
        draw.text(
            surface,
            "←/→ or mouse to move · Space / click to launch",
            t.font(t.size.caption),
            p.text_muted,
            (FIELD.centerx, FIELD.bottom + 8),
            "midtop",
        )

    def _draw_over(self, surface: Canvas, t: Theme) -> None:
        assert self.menu is not None
        p = t.palette
        panel = pygame.Rect(0, 0, 400, self.menu.rect.height + 150)
        panel.midbottom = (FIELD.centerx, self.menu.rect.bottom + 32)
        draw_panel(surface, panel, t)
        draw.text(
            surface,
            "Game over",
            t.font(t.size.heading, "bold"),
            p.text,
            (panel.centerx, panel.y + 28),
            "midtop",
        )
        sub = (
            "New high score!"
            if self.new_best
            else f"Score {self.game.score:,} · level {self.game.level + 1}"
        )
        draw.text(
            surface,
            sub,
            t.font(t.size.label, "semibold"),
            p.success if self.new_best else p.text_muted,
            (panel.centerx, panel.y + 74),
            "midtop",
        )
        self.menu.draw(surface)
