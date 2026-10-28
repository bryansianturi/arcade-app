"""Skyhop UI: night sky, parallax skyline, neon gates and a glowing orb."""

from __future__ import annotations

import math
import random

import pygame

from apps.skyhop.logic import FIELD_H, FIELD_W, GATE_W, PLAYER_R, PLAYER_X, Skyhop
from core import draw, gfx
from core.base_app import BaseApp
from core.canvas import Canvas
from core.registry import register_app
from core.theme import Color, Theme, lerp_color
from core.widgets import ButtonMenu, draw_panel

ACCENT: Color = (250, 204, 21)
GATE: Color = (45, 212, 191)
SKY_TOP: Color = (15, 23, 42)
SKY_BOTTOM: Color = (49, 46, 129)
FIELD = pygame.Rect((1280 - FIELD_W) // 2, 62, FIELD_W, FIELD_H)
HOP_KEYS = (pygame.K_SPACE, pygame.K_UP, pygame.K_w)


@register_app
class SkyhopApp(BaseApp):
    """Hop through the gaps. One button, many retries."""

    @classmethod
    def draw_icon(cls, surface: Canvas, rect: pygame.Rect, theme: Theme) -> None:
        draw.rounded_rect(surface, rect, SKY_BOTTOM, theme.radius.md)
        u = rect.width / 8
        gfx.rect(surface, GATE, (rect.x + 5 * u, rect.y, 1.6 * u, 2.6 * u))
        gfx.rect(surface, GATE, (rect.x + 5 * u, rect.y + 5.4 * u, 1.6 * u, 2.6 * u))
        gfx.circle(surface, ACCENT, (rect.x + 2.8 * u, rect.y + 4 * u), 1.1 * u)

    def on_enter(self) -> None:
        self.game = Skyhop(random.Random())
        self.menu: ButtonMenu | None = None
        self.new_best = False
        self.pulse = 0.0
        rng = random.Random(7)  # fixed skyline/stars so they don't flicker between runs
        self.stars = [
            (rng.uniform(0, FIELD_W), rng.uniform(0, FIELD_H * 0.6), rng.uniform(0.6, 1.8))
            for _ in range(70)
        ]
        self.skyline = [(rng.uniform(40, 90), rng.uniform(60, 200)) for _ in range(40)]

    def restart(self) -> None:
        self.game = Skyhop(random.Random())
        self.menu = None

    def _hop(self) -> None:
        if self.game.state in ("ready", "flying"):
            self.game.hop()

    def handle_event(self, event: pygame.event.Event) -> None:
        if self.menu is not None:
            self.menu.handle_event(event)
            return
        if (event.type == pygame.KEYDOWN and event.key in HOP_KEYS) or (
            event.type == pygame.MOUSEBUTTONDOWN and event.button == 1
        ):
            self._hop()

    def update(self, dt: float) -> None:
        self.pulse = max(0.0, self.pulse - dt)
        if self.menu is not None:
            self.menu.update(dt)
            return
        if self.game.update(dt):
            self.pulse = 0.25
        if self.game.state == "over":
            self.new_best = self.game.score > 0 and self.submit_score(self.game.score)
            self.menu = ButtonMenu(
                self.theme,
                (FIELD.centerx, FIELD.centery + 70),
                [("Fly again", self.restart), ("Back to menu", self.exit_to_launcher)],
                accent=ACCENT,
            )

    # ------------------------------------------------------------------ drawing
    def draw(self, surface: Canvas) -> None:
        t = self.theme
        g = self.game
        surface.fill(t.palette.bg)
        field = draw.vertical_gradient(FIELD.size, SKY_TOP, SKY_BOTTOM, surface.scale).copy()
        for x, y, r in self.stars:
            sx = (x - g.distance * 0.05) % FIELD_W
            twinkle = 0.6 + 0.4 * math.sin(g.time * 2 + x)
            gfx.circle(field, lerp_color(SKY_TOP, (255, 255, 255), twinkle), (sx, y), r)
        self._draw_skyline(field, g.distance * 0.3)
        for gate in g.gates:
            self._draw_gate(field, gate.x, gate.top_bottom, gate.bottom_top)
        self._draw_ground(field, g.distance)
        self._draw_player(field)

        score_font = t.font(72, "bold")
        scale = 1 + self.pulse * 0.8
        if g.state != "ready":
            img = score_font.render(str(g.score), True, (255, 255, 255))
            img = img.scaled(scale)
            field.blit(img, img.get_rect(midtop=(FIELD_W // 2, 24)))

        draw.round_corners(field, t.radius.lg)
        draw.shadow(surface, FIELD, t.radius.lg, t.palette.shadow, (0, 8), 16)
        surface.blit(field, FIELD.topleft)
        self._draw_hud(surface, t)

        if g.state == "ready":
            draw.text(
                surface,
                "Space, ↑ or click to hop",
                t.font(t.size.title, "semibold"),
                (255, 255, 255),
                (FIELD.centerx, FIELD.y + round(FIELD_H * 0.62)),
                "center",
            )
        if self.menu is not None:
            self._draw_over(surface, t)

    def _draw_skyline(self, field: Canvas, offset: float) -> None:
        color = lerp_color(SKY_TOP, SKY_BOTTOM, 0.55)
        total = sum(w for w, _ in self.skyline)
        x = -(offset % total)
        base = FIELD_H - 56
        while x < FIELD_W:
            for w, h in self.skyline:
                if x > FIELD_W:
                    break
                gfx.rect(field, color, (x, base - h, w - 4, h))
                x += w

    def _draw_gate(self, field: Canvas, x: float, top_end: float, bottom_start: float) -> None:
        dark = lerp_color(GATE, SKY_TOP, 0.5)
        for rect in (
            pygame.Rect(x, -10, GATE_W, top_end + 10),
            pygame.Rect(x, bottom_start, GATE_W, FIELD_H),
        ):
            gfx.rect(field, dark, rect, border_radius=10)
            gfx.rect(field, GATE, rect, 3, border_radius=10)
        for y in (top_end - 14, bottom_start):  # caps
            gfx.rect(field, GATE, (x - 6, y, GATE_W + 12, 14), border_radius=6)

    def _draw_ground(self, field: Canvas, distance: float) -> None:
        ground_y = FIELD_H - 56
        gfx.rect(field, (17, 24, 39), (0, ground_y, FIELD_W, 56))
        gfx.line(field, GATE, (0, ground_y), (FIELD_W, ground_y), 2)
        for i in range(-1, FIELD_W // 40 + 2):
            x = i * 40 - distance % 40
            gfx.line(
                field, lerp_color((17, 24, 39), GATE, 0.3), (x, ground_y + 10), (x - 20, FIELD_H), 2
            )

    def _draw_player(self, field: Canvas) -> None:
        g = self.game
        center = pygame.Vector2(PLAYER_X, g.y)
        glow = Canvas.new((PLAYER_R * 6, PLAYER_R * 6), alpha=True)
        for i in range(6, 0, -1):
            gfx.circle(
                glow,
                (*ACCENT, 12 * (7 - i)),
                (PLAYER_R * 3, PLAYER_R * 3),
                PLAYER_R * (1 + i * 0.3),
            )
        field.blit(glow, center - pygame.Vector2(PLAYER_R * 3, PLAYER_R * 3))
        gfx.circle(field, ACCENT, center, PLAYER_R)
        # A little "eye" that points where the orb is heading.
        heading = pygame.Vector2(1, 0).rotate(g.tilt)
        gfx.circle(field, (255, 255, 255), center + heading * 6, 5)
        gfx.circle(field, SKY_TOP, center + heading * 8, 2.5)
        flap = math.sin(g.time * (30 if g.vy < 0 else 8)) * 5
        wing_base = center - heading * 4
        gfx.polygon(
            field,
            lerp_color(ACCENT, (255, 255, 255), 0.4),
            [
                wing_base,
                wing_base + pygame.Vector2(-14, -8 - flap),
                wing_base + pygame.Vector2(-4, 2),
            ],
        )

    def _draw_hud(self, surface: Canvas, t: Theme) -> None:
        p = t.palette
        best = self.best_score()
        best_value = max(self.game.score, int(best.score) if best else 0)
        y = FIELD.y - 30
        draw.text(surface, "Skyhop", t.font(t.size.title, "bold"), p.text, (FIELD.x, y), "midleft")
        draw.text(
            surface,
            f"Best {best_value}",
            t.font(t.size.label, "semibold"),
            ACCENT if t.mode == "dark" else p.text,
            (FIELD.right, y),
            "midright",
        )

    def _draw_over(self, surface: Canvas, t: Theme) -> None:
        assert self.menu is not None
        p = t.palette
        panel = pygame.Rect(0, 0, 380, self.menu.rect.height + 150)
        panel.midbottom = (FIELD.centerx, self.menu.rect.bottom + 32)
        draw_panel(surface, panel, t)
        draw.text(
            surface,
            f"Score {self.game.score}",
            t.font(t.size.heading, "bold"),
            p.text,
            (panel.centerx, panel.y + 28),
            "midtop",
        )
        sub = "New best!" if self.new_best else "Hop again?"
        draw.text(
            surface,
            sub,
            t.font(t.size.label, "semibold"),
            p.success if self.new_best else p.text_muted,
            (panel.centerx, panel.y + 74),
            "midtop",
        )
        self.menu.draw(surface)
