"""Void Drift UI: neon vector ship, tumbling rocks, drones, particles and HUD."""

from __future__ import annotations

import math
import random
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Literal

import pygame

from apps.void_drift.logic import (
    FIELD_H,
    FIELD_W,
    SHIP_RADIUS,
    Drone,
    Event,
    Rock,
    VoidDrift,
    heading,
)
from core import draw, gfx
from core.base_app import BaseApp
from core.canvas import Canvas
from core.input import is_action
from core.registry import register_app
from core.theme import Color, Theme, lerp_color
from core.widgets import ButtonMenu, draw_panel

ACCENT: Color = (103, 232, 249)
SPACE: Color = (8, 10, 20)
ROCK_FILL: Color = (30, 36, 54)
ROCK_EDGE: Color = (148, 163, 184)
FLAME: Color = (251, 146, 60)
DRONE_COLORS: dict[str, Color] = {"large": (251, 191, 36), "small": (244, 114, 182)}
ENEMY_SHOT: Color = (248, 113, 113)

FIELD = pygame.Rect((1280 - FIELD_W) // 2, 88, FIELD_W, FIELD_H)
WAVE_INTRO_SECONDS = 1.6
SHAKE_SECONDS = 0.4

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


def wrapped(x: float, y: float, r: float) -> Iterator[tuple[float, float]]:
    """``(x, y)`` plus its copies across the edges it overlaps, so wrapping looks seamless."""
    xs = [x] + ([x + FIELD_W] if x < r else []) + ([x - FIELD_W] if x > FIELD_W - r else [])
    ys = [y] + ([y + FIELD_H] if y < r else []) + ([y - FIELD_H] if y > FIELD_H - r else [])
    for px in xs:
        for py in ys:
            yield px, py


def ship_points(x: float, y: float, angle: float, scale: float = 1.0) -> list[pygame.Vector2]:
    """Nose, right wing, tail notch, left wing."""
    center = pygame.Vector2(x, y)
    r = SHIP_RADIUS * scale
    shape = ((0.0, -1.35), (0.95, 1.0), (0.0, 0.55), (-0.95, 1.0))
    return [center + pygame.Vector2(px * r, py * r).rotate(angle) for px, py in shape]


def rock_points(rock: Rock, x: float, y: float) -> list[pygame.Vector2]:
    n = len(rock.shape)
    center = pygame.Vector2(x, y)
    return [
        center + pygame.Vector2(0, -rock.radius * k).rotate(rock.angle + i * 360 / n)
        for i, k in enumerate(rock.shape)
    ]


@register_app
class VoidDriftApp(BaseApp):
    """Fly, drift and shoot: rocks split, drones hunt, and every wave gets busier."""

    @classmethod
    def draw_icon(cls, surface: Canvas, rect: pygame.Rect, theme: Theme) -> None:
        draw.rounded_rect(surface, rect, (15, 23, 42), theme.radius.md)
        u = rect.width / 10
        center = pygame.Vector2(rect.x + 6.9 * u, rect.y + 3.1 * u)
        shape = (1.0, 0.78, 0.95, 0.82, 1.0, 0.74, 0.92, 0.86, 0.97)
        rock = [
            center + pygame.Vector2(0, -2.0 * u * k).rotate(i * 40 + 10)
            for i, k in enumerate(shape)
        ]
        gfx.polygon(surface, ROCK_FILL, rock)
        gfx.polygon(surface, ROCK_EDGE, rock, max(1.5, u * 0.25))
        for i in range(2):  # shots on their way
            gfx.circle(
                surface,
                (235, 252, 255),
                (rect.x + (4.6 + i * 0.9) * u, rect.y + (5.4 - i * 0.9) * u),
                u * 0.28,
            )
        ship = ship_points(rect.x + 3.0 * u, rect.y + 7.0 * u, 45, u * 1.25 / SHIP_RADIUS)
        gfx.polygon(surface, ACCENT, ship)

    # ------------------------------------------------------------------ lifecycle
    def on_enter(self) -> None:
        self.rng = random.Random()  # visuals only
        self.game = VoidDrift(random.Random())
        self.state: State = "ready"
        self.menu: ButtonMenu | None = None
        self.particles: list[Particle] = []
        self.time = 0.0
        self.shake = 0.0
        self.intro = 0.0
        self.new_best = False
        self.stars = [
            (
                self.rng.uniform(0, FIELD_W),
                self.rng.uniform(0, FIELD_H),
                self.rng.choice((1, 1, 1.5)),
            )
            for _ in range(120)
        ]

    def restart(self) -> None:
        self._start()

    def _start(self) -> None:
        self.game = VoidDrift(random.Random())
        self.state = "playing"
        self.menu = None
        self.particles.clear()
        self.intro = WAVE_INTRO_SECONDS

    def _game_over(self) -> None:
        self.state = "over"
        self.new_best = self.game.score > 0 and self.submit_score(self.game.score)
        self.menu = ButtonMenu(
            self.theme,
            (FIELD.centerx, FIELD.centery + 80),
            [("Play again", self._start), ("Back to menu", self.exit_to_launcher)],
            accent=ACCENT,
        )

    def on_exit(self) -> None:
        if self.state == "playing" and self.game.score > 0:
            self.submit_score(self.game.score)

    # ------------------------------------------------------------------ input
    def handle_event(self, event: pygame.event.Event) -> None:
        if self.state == "over" and self.menu is not None:
            self.menu.handle_event(event)
            return
        if self.state == "ready":
            if is_action(event, "action", repeat=False):
                self._start()
            return
        if is_action(event, "action", repeat=False):
            self.game.fire()
        elif is_action(event, "down", repeat=False):
            self.game.warp()

    def _check_achievements(self) -> None:
        g = self.game
        self.unlock_milestones(g.wave, {"wave_3": 3})
        self.unlock_milestones(g.drones_destroyed, {"drone": 1})
        self.unlock_milestones(g.score, {"score_10000": 10_000})

    def update(self, dt: float) -> None:
        self.time += dt
        self.shake = max(0.0, self.shake - dt)
        self.intro = max(0.0, self.intro - dt)
        self._update_particles(dt)
        if self.menu is not None:
            self.menu.update(dt)
        if self.state != "playing":
            return
        g = self.game
        g.turn = int(self.input.held("right")) - int(self.input.held("left"))
        g.thrust = self.input.held("up")
        if self.input.held("action"):
            g.fire()  # holding fire auto-repeats at the cooldown rate
        wave = g.wave
        for event in g.update(dt):
            self._on_event(event)
        if g.wave != wave:
            self.intro = WAVE_INTRO_SECONDS
        if g.thrust and g.ship_alive:
            self._exhaust()
        self._check_achievements()
        if g.over:
            self._game_over()

    # ------------------------------------------------------------------ effects
    def _on_event(self, event: Event) -> None:
        if event.kind == "rock_destroyed":
            self._burst(event.x, event.y, ROCK_EDGE, 6 + event.size * 6, 90 + event.size * 40)
        elif event.kind == "drone_destroyed":
            self._burst(event.x, event.y, DRONE_COLORS["large"], 30, 260)
        elif event.kind == "ship_destroyed":
            self._burst(event.x, event.y, ACCENT, 46, 320, size=4.5)
            self.shake = SHAKE_SECONDS
        elif event.kind == "warp":
            self._burst(event.x, event.y, (196, 181, 253), 18, 180)

    def _burst(
        self, x: float, y: float, color: Color, n: int, speed: float, size: float = 3.0
    ) -> None:
        for _ in range(n):
            a = self.rng.uniform(0, math.tau)
            v = self.rng.uniform(0.2, 1.0) * speed
            life = self.rng.uniform(0.35, 0.9)
            self.particles.append(
                Particle(
                    x,
                    y,
                    math.cos(a) * v,
                    math.sin(a) * v,
                    life,
                    life,
                    color,
                    self.rng.uniform(1.2, size),
                )
            )

    def _exhaust(self) -> None:
        s = self.game.ship
        dx, dy = heading(s.angle)
        for _ in range(2):
            spread = self.rng.uniform(-0.35, 0.35)
            v = self.rng.uniform(80, 180)
            vx = -dx * v + -dy * spread * v + s.vx
            vy = -dy * v + dx * spread * v + s.vy
            life = self.rng.uniform(0.15, 0.3)
            self.particles.append(
                Particle(
                    s.x - dx * SHIP_RADIUS * 0.6,
                    s.y - dy * SHIP_RADIUS * 0.6,
                    vx,
                    vy,
                    life,
                    life,
                    FLAME,
                    2.2,
                )
            )

    def _update_particles(self, dt: float) -> None:
        alive = []
        for p in self.particles:
            p.life -= dt
            if p.life > 0:
                p.x = (p.x + p.vx * dt) % FIELD_W
                p.y = (p.y + p.vy * dt) % FIELD_H
                p.vx *= 1 - 1.8 * dt
                p.vy *= 1 - 1.8 * dt
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
        self._draw_particles(field)
        for rock in self.game.rocks:
            self._draw_rock(field, rock)
        for drone in self.game.drones:
            self._draw_drone(field, drone)
        self._draw_bullets(field)
        self._draw_ship(field)
        draw.round_corners(field, t.radius.lg)
        offset = (0, 0)
        if self.shake > 0:
            k = self.shake / SHAKE_SECONDS * 7
            offset = (round(math.sin(self.time * 83) * k), round(math.cos(self.time * 67) * k))
        rect = FIELD.move(offset)
        draw.shadow(surface, rect, t.radius.lg, t.palette.shadow, (0, 8), 16)
        surface.blit(field, rect.topleft)

        g = self.game
        if self.state == "ready":
            inp = self.input
            hint = (
                f"{inp.labels('left', 'right')} turn · {inp.label('up')} thrust · "
                f"{inp.label('action')} fire · {inp.label('down')} warp"
            )
            self._draw_card(surface, t, "Void Drift", hint)
        elif self.state == "playing" and self.intro > 0:
            alpha = min(1.0, self.intro / 0.4)
            draw.text(
                surface,
                f"Wave {g.wave}",
                t.font(t.size.display, "bold"),
                (*ACCENT, round(255 * alpha)),
                FIELD.center,
                "center",
            )
        elif self.state == "over" and self.menu is not None:
            sub = "New high score!" if self.new_best else f"Score {g.score:,} · wave {g.wave}"
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
        y = FIELD.y - 34
        g = self.game
        draw.text(
            surface, f"{g.score:,}", t.font(t.size.heading, "bold"), ACCENT, (FIELD.x, y), "midleft"
        )
        best = self.best_score()
        best_text = f"Best {int(best.score):,}" if best else "Best —"
        draw.text(
            surface,
            f"Wave {g.wave} · {best_text}",
            t.font(t.size.label),
            p.text_muted,
            (FIELD.centerx, y),
            "center",
        )
        for i in range(g.lives):
            pts = ship_points(FIELD.right - 14 - i * 30, y + 2, 0, 0.8)
            gfx.polygon(surface, ACCENT, pts)

    def _draw_stars(self, field: Canvas) -> None:
        for i, (x, y, r) in enumerate(self.stars):
            twinkle = 0.45 + 0.35 * math.sin(self.time * 1.5 + i)
            gfx.circle(field, lerp_color(SPACE, (220, 230, 255), twinkle), (x, y), r)

    def _draw_rock(self, field: Canvas, rock: Rock) -> None:
        for x, y in wrapped(rock.x, rock.y, rock.radius):
            pts = rock_points(rock, x, y)
            gfx.polygon(field, ROCK_FILL, pts)
            gfx.polygon(field, ROCK_EDGE, pts, 2)

    def _draw_drone(self, field: Canvas, drone: Drone) -> None:
        color = DRONE_COLORS[drone.kind]
        r = drone.radius
        for x, y in wrapped(drone.x, drone.y, r * 1.6):
            body = pygame.FRect(0, 0, r * 3, r * 1.1)
            body.center = (x, y + r * 0.15)
            dome = pygame.FRect(0, 0, r * 1.4, r * 1.2)
            dome.midbottom = (x, body.centery)
            gfx.ellipse(field, lerp_color(color, SPACE, 0.55), dome)
            gfx.ellipse(field, color, dome, 2)
            gfx.ellipse(field, lerp_color(color, SPACE, 0.3), body)
            gfx.ellipse(field, color, body, 2)
            blink = int(self.time * 6) % 3
            for i in range(3):
                light = (255, 255, 255) if i == blink else lerp_color(color, SPACE, 0.4)
                gfx.circle(field, light, (x + (i - 1) * r * 0.8, body.centery), max(1.5, r * 0.14))

    def _draw_bullets(self, field: Canvas) -> None:
        for b in self.game.bullets:
            if b.friendly:
                gfx.circle(field, lerp_color(ACCENT, SPACE, 0.55), (b.x, b.y), 5)
                gfx.circle(field, (235, 252, 255), (b.x, b.y), 2.4)
            else:
                gfx.circle(field, lerp_color(ENEMY_SHOT, SPACE, 0.5), (b.x, b.y), 6)
                gfx.circle(field, ENEMY_SHOT, (b.x, b.y), 3)

    def _draw_ship(self, field: Canvas) -> None:
        g = self.game
        if not g.ship_alive or (self.state == "over"):
            return
        if g.invulnerable > 0 and self.state == "playing" and int(self.time * 12) % 2 == 0:
            return  # blink while invulnerable
        s = g.ship
        for x, y in wrapped(s.x, s.y, SHIP_RADIUS * 1.6):
            if g.thrust:
                dx, dy = heading(s.angle)
                flicker = 1.0 + 0.35 * math.sin(self.time * 40)
                tail = pygame.Vector2(x, y) - pygame.Vector2(dx, dy) * SHIP_RADIUS * (1.0 + flicker)
                side = pygame.Vector2(-dy, dx) * SHIP_RADIUS * 0.35
                base = pygame.Vector2(x, y) - pygame.Vector2(dx, dy) * SHIP_RADIUS * 0.5
                gfx.polygon(field, FLAME, [base + side, tail, base - side])
            pts = ship_points(x, y, s.angle)
            gfx.polygon(field, lerp_color(ACCENT, SPACE, 0.75), pts)
            gfx.polygon(field, ACCENT, pts, 2)

    def _draw_particles(self, field: Canvas) -> None:
        for p in self.particles:
            k = p.life / p.max_life
            gfx.circle(
                field,
                lerp_color(SPACE, p.color, min(1.0, k * 1.3)),
                (p.x, p.y),
                p.size * (0.5 + k * 0.5),
            )

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
        draw.overlay(surface, p.overlay)
        panel = pygame.Rect(0, 0, 560, 130 + extra)
        panel.midtop = (FIELD.centerx, FIELD.centery - 110)
        draw_panel(surface, panel, t)
        draw.text(
            surface,
            title,
            t.font(t.size.heading, "bold"),
            p.text,
            (panel.centerx, panel.y + 30),
            "midtop",
        )
        draw.text(
            surface,
            sub,
            t.font(t.size.label, "semibold" if highlight else "regular"),
            p.success if highlight else p.text_muted,
            (panel.centerx, panel.y + 78),
            "midtop",
        )
