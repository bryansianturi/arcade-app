"""Star Siege UI: starfield, vector ships, particles and HUD."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Literal

import pygame

from apps.star_siege.logic import (
    ENEMY_H,
    ENEMY_W,
    FIELD_H,
    FIELD_W,
    PLAYER_H,
    PLAYER_W,
    PLAYER_Y,
    SHIELD_CELL,
    Event,
    SiegeGame,
)
from core import draw, gfx
from core.base_app import BaseApp
from core.canvas import Canvas
from core.registry import register_app
from core.theme import Color, Theme, lerp_color
from core.widgets import ButtonMenu, draw_panel

ACCENT: Color = (236, 72, 153)
PLAYER_COLOR: Color = (56, 189, 248)
ENEMY_COLORS: tuple[Color, Color, Color] = ((251, 191, 36), (167, 139, 250), (45, 212, 191))
SHIELD_COLOR: Color = (74, 222, 128)
ENEMY_SHOT: Color = (251, 113, 133)
SPACE: Color = (10, 12, 22)

FIELD = pygame.Rect((1280 - FIELD_W) // 2, 76, FIELD_W, FIELD_H)

LEFT_KEYS = (pygame.K_LEFT, pygame.K_a)
RIGHT_KEYS = (pygame.K_RIGHT, pygame.K_d)
FIRE_KEYS = (pygame.K_SPACE, pygame.K_UP, pygame.K_w)

State = Literal["ready", "playing", "over"]


@dataclass
class Particle:
    x: float
    y: float
    vx: float
    vy: float
    life: float
    max_life: float
    color: Color
    size: float


@register_app
class StarSiegeApp(BaseApp):
    """Shoot down descending drone formations before they reach you."""

    @classmethod
    def draw_icon(cls, surface: Canvas, rect: pygame.Rect, theme: Theme) -> None:
        draw.rounded_rect(surface, rect, SPACE, theme.radius.md)
        draw.rounded_rect(surface, rect, ACCENT, theme.radius.md, 2)
        u = rect.width / 8
        cx = rect.centerx
        for i, color in enumerate(ENEMY_COLORS):
            x = rect.x + (2 + i * 2) * u
            gfx.circle(surface, color, (x, rect.y + 2.2 * u), u * 0.6)
        gfx.line(surface, (220, 245, 255), (cx, rect.y + 3.6 * u), (cx, rect.y + 4.6 * u), 2)
        body = [
            (cx, rect.y + 5 * u),
            (cx + 1.6 * u, rect.y + 6.6 * u),
            (cx - 1.6 * u, rect.y + 6.6 * u),
        ]
        gfx.polygon(surface, PLAYER_COLOR, body)

    def on_enter(self) -> None:
        self.rng = random.Random()
        self.game = SiegeGame(self.rng)
        self.state: State = "ready"
        self.held: set[int] = set()
        self.fire_held = False
        self.particles: list[Particle] = []
        self.flash = 0.0
        self.time = 0.0
        self.new_best = False
        self.menu: ButtonMenu | None = None
        self.stars = [
            (
                self.rng.uniform(0, FIELD_W),
                self.rng.uniform(0, FIELD_H),
                self.rng.choice((1, 1, 2)),
                self.rng.uniform(0, math.tau),
            )
            for _ in range(110)
        ]

    def _start(self) -> None:
        self.game = SiegeGame(self.rng)
        self.state = "playing"
        self.menu = None
        self.particles.clear()

    def on_pause(self) -> None:
        # Keys released while the pause menu is open would otherwise stay "held".
        self.held.clear()
        self.fire_held = False

    # ------------------------------------------------------------------ input
    def handle_event(self, event: pygame.event.Event) -> None:
        if self.state == "over" and self.menu is not None:
            self.menu.handle_event(event)
            return
        if event.type == pygame.KEYDOWN:
            if self.state == "ready" and event.key in (pygame.K_SPACE, pygame.K_RETURN):
                self._start()
                return
            self.held.add(event.key)
            if event.key in FIRE_KEYS:
                self.fire_held = True
                self.game.fire()
        elif event.type == pygame.KEYUP:
            self.held.discard(event.key)
            if event.key in FIRE_KEYS:
                self.fire_held = any(k in self.held for k in FIRE_KEYS)

    def update(self, dt: float) -> None:
        self.time += dt
        self.flash = max(0.0, self.flash - dt)
        self._update_particles(dt)
        if self.menu is not None:
            self.menu.update(dt)
        if self.state != "playing":
            return
        game = self.game
        left = any(k in self.held for k in LEFT_KEYS)
        right = any(k in self.held for k in RIGHT_KEYS)
        game.move = int(right) - int(left)
        if self.fire_held:
            game.fire()  # holding fire auto-repeats at the cooldown rate
        for event in game.update(dt):
            self._on_event(event)
        if game.over:
            self._game_over()

    def _game_over(self) -> None:
        self.state = "over"
        self.new_best = self.game.score > 0 and self.submit_score(self.game.score)
        self.menu = ButtonMenu(
            self.theme,
            (FIELD.centerx, FIELD.centery + 80),
            [("Play again", self._start), ("Back to menu", self.exit_to_launcher)],
            accent=ACCENT,
        )

    # ------------------------------------------------------------------ effects
    def _on_event(self, event: Event) -> None:
        if event.kind == "enemy_destroyed":
            self._burst(event.x, event.y, ENEMY_COLORS[event.variant], 22, 220)
        elif event.kind == "shield_hit":
            self._burst(event.x, event.y, SHIELD_COLOR, 6, 90, size=2.5)
        elif event.kind in ("player_hit", "game_over"):
            self._burst(event.x, event.y, PLAYER_COLOR, 40, 300)
            self.flash = 0.25

    def _burst(
        self, x: float, y: float, color: Color, n: int, speed: float, size: float = 3.5
    ) -> None:
        for _ in range(n):
            angle = self.rng.uniform(0, math.tau)
            v = self.rng.uniform(0.25, 1.0) * speed
            life = self.rng.uniform(0.35, 0.8)
            self.particles.append(
                Particle(
                    x,
                    y,
                    math.cos(angle) * v,
                    math.sin(angle) * v,
                    life,
                    life,
                    color,
                    self.rng.uniform(1.5, size),
                )
            )

    def _update_particles(self, dt: float) -> None:
        alive = []
        for p in self.particles:
            p.life -= dt
            if p.life > 0:
                p.x += p.vx * dt
                p.y += p.vy * dt
                p.vx *= 1 - 2.5 * dt
                p.vy *= 1 - 2.5 * dt
                alive.append(p)
        self.particles = alive

    # ------------------------------------------------------------------ drawing
    def draw(self, surface: Canvas) -> None:
        t = self.theme
        surface.fill(t.palette.bg)
        self._draw_hud(surface, t)
        field = Canvas.new(FIELD.size, alpha=True)
        field.fill(SPACE)
        self._draw_stars(field)
        self._draw_shields(field)
        self._draw_enemies(field)
        self._draw_bullets(field)
        self._draw_player(field)
        self._draw_particles(field)
        if self.flash > 0:
            field.fill((int(90 * self.flash / 0.25),) * 3, special_flags=pygame.BLEND_RGB_ADD)
        # Round the corners of the playfield.
        draw.round_corners(field, t.radius.lg)
        draw.shadow(surface, FIELD, t.radius.lg, t.palette.shadow, (0, 8), 16)
        surface.blit(field, FIELD.topleft)

        game = self.game
        if self.state == "ready":
            self._draw_card(surface, t, "Star Siege", "← → move · Space fire · Space to launch")
        elif self.state == "playing" and game.wave_intro > 0:
            alpha = min(1.0, game.wave_intro / 0.4)
            font = t.font(t.size.display, "bold")
            draw.text(
                surface,
                f"Wave {game.wave}",
                font,
                (*ACCENT, round(255 * alpha)),
                FIELD.center,
                "center",
            )
        elif self.state == "over" and self.menu is not None:
            sub = "New high score!" if self.new_best else f"Score {game.score:,} · wave {game.wave}"
            self._draw_card(
                surface,
                t,
                "Game over",
                sub,
                extra=self.menu.rect.height + 30,
                highlight=self.new_best,
            )
            self.menu.draw(surface)

    def _draw_hud(self, surface: Canvas, t: Theme) -> None:
        p = t.palette
        y = FIELD.y - 30
        draw.text(
            surface,
            f"{self.game.score:,}",
            t.font(t.size.heading, "bold"),
            ACCENT,
            (FIELD.x, y),
            "midleft",
        )
        best = self.best_score()
        best_text = f"Best {int(best.score):,}" if best else "Best —"
        draw.text(
            surface,
            f"Wave {self.game.wave} · {best_text}",
            t.font(t.size.label),
            p.text_muted,
            (FIELD.centerx, y),
            "center",
        )
        for i in range(self.game.lives):
            cx = FIELD.right - 18 - i * 40
            self._ship_shape(surface, cx, y - 9, 0.6, PLAYER_COLOR)

    def _draw_stars(self, field: Canvas) -> None:
        for x, y, size, phase in self.stars:
            yy = (y + self.time * (8 + size * 10)) % FIELD_H
            twinkle = 0.55 + 0.45 * math.sin(self.time * 2 + phase)
            c = round(150 * twinkle) + 40
            gfx.circle(field, (c, c, min(255, c + 30)), (x, yy), size * 0.8)

    def _draw_shields(self, field: Canvas) -> None:
        dark = lerp_color(SHIELD_COLOR, SPACE, 0.35)
        for shield in self.game.shields:
            for r, c in shield.cells:
                color = SHIELD_COLOR if (r + c) % 3 else dark
                gfx.rect(
                    field,
                    color,
                    (
                        shield.x + c * SHIELD_CELL,
                        shield.y + r * SHIELD_CELL,
                        SHIELD_CELL,
                        SHIELD_CELL,
                    ),
                )

    def _draw_enemies(self, field: Canvas) -> None:
        flap = math.sin(self.time * 6)
        for e in self.game.alive_enemies():
            box = self.game.enemy_box(e)
            cx, cy = box.center
            color = ENEMY_COLORS[e.kind]
            if e.kind == 0:  # diamond core
                s = ENEMY_H * 0.5
                pts = [(cx, cy - s), (cx + s * 1.1, cy), (cx, cy + s), (cx - s * 1.1, cy)]
                gfx.polygon(field, color, pts)
                gfx.circle(field, SPACE, (cx, cy), 6)
                gfx.circle(field, (255, 255, 255), (cx, cy), 3)
                for side in (-1, 1):
                    gfx.line(
                        field,
                        color,
                        (cx + side * s * 1.1, cy),
                        (cx + side * (s * 1.1 + 6), cy - 6 + flap * 3),
                        3,
                    )
            elif e.kind == 1:  # winged chevron
                w, h = ENEMY_W / 2, ENEMY_H / 2
                wing = 4 + flap * 4
                pts = [
                    (cx, cy - h),
                    (cx + w, cy - h * 0.2 - wing),
                    (cx + w * 0.55, cy + h),
                    (cx, cy + h * 0.35),
                    (cx - w * 0.55, cy + h),
                    (cx - w, cy - h * 0.2 - wing),
                ]
                gfx.polygon(field, color, pts)
                for side in (-1, 1):
                    gfx.circle(field, SPACE, (cx + side * 6, cy - 2), 3)
            else:  # ringed orb
                r = ENEMY_H * 0.38
                ring = pygame.Rect(0, 0, ENEMY_W, 10 + flap * 3)
                ring.center = (round(cx), round(cy + 2))
                gfx.ellipse(field, lerp_color(color, SPACE, 0.4), ring, 3)
                gfx.circle(field, color, (cx, cy), r)
                gfx.circle(
                    field,
                    lerp_color(color, (255, 255, 255), 0.6),
                    (cx - r * 0.35, cy - r * 0.35),
                    r * 0.3,
                )

    def _draw_bullets(self, field: Canvas) -> None:
        for b in self.game.bullets:
            box = b.box
            rect = pygame.Rect(round(box.x), round(box.y), round(box.w), round(box.h))
            if b.friendly:
                glow = rect.inflate(6, 6)
                gfx.rect(field, lerp_color(PLAYER_COLOR, SPACE, 0.6), glow, border_radius=4)
                gfx.rect(field, (220, 245, 255), rect, border_radius=2)
            else:
                # A little zig-zag bolt.
                x, y = rect.centerx, rect.y
                wob = 3 if int(self.time * 20) % 2 else -3
                pts = [(x, y), (x + wob, y + 5), (x - wob, y + 10), (x, y + rect.height)]
                gfx.lines(field, ENEMY_SHOT, False, pts, 3)

    def _ship_shape(
        self, surface: Canvas, cx: float, top: float, scale: float, color: Color
    ) -> None:
        w, h = PLAYER_W * scale, PLAYER_H * scale
        body = [
            (cx, top),
            (cx + w * 0.5, top + h),
            (cx + w * 0.18, top + h * 0.78),
            (cx - w * 0.18, top + h * 0.78),
            (cx - w * 0.5, top + h),
        ]
        gfx.polygon(surface, color, body)
        gfx.circle(surface, (225, 245, 255), (cx, top + h * 0.5), max(2, 4 * scale))

    def _draw_player(self, field: Canvas) -> None:
        game = self.game
        if game.over and self.state != "ready":
            return
        if game.invulnerable > 0 and int(self.time * 12) % 2 == 0:
            return  # blink while invulnerable
        cx = game.player_x
        flame = 6 + 4 * abs(math.sin(self.time * 30))
        gfx.polygon(
            field,
            (255, 170, 60),
            [
                (cx - 6, PLAYER_Y + PLAYER_H * 0.78),
                (cx + 6, PLAYER_Y + PLAYER_H * 0.78),
                (cx, PLAYER_Y + PLAYER_H + flame),
            ],
        )
        self._ship_shape(field, cx, PLAYER_Y, 1.0, PLAYER_COLOR)

    def _draw_particles(self, field: Canvas) -> None:
        for p in self.particles:
            k = p.life / p.max_life
            color = lerp_color(SPACE, p.color, min(1.0, k * 1.4))
            gfx.circle(field, color, (p.x, p.y), max(1.0, p.size * k))

    def _draw_card(
        self,
        surface: Canvas,
        t: Theme,
        title: str,
        sub: str,
        extra: int = 0,
        highlight: bool = False,
    ) -> None:
        p = t.palette
        draw.overlay(surface, (*SPACE, 150))
        panel = pygame.Rect(0, 0, 440, 140 + extra)
        panel.midtop = (FIELD.centerx, FIELD.centery - 130)
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
            (panel.centerx, panel.y + 82),
            "midtop",
        )
