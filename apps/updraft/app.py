"""Updraft UI: a dusk-to-night sky, four kinds of platforms and a bouncing spark."""

from __future__ import annotations

import math
import random

import pygame

from apps.updraft.logic import (
    FIELD_H,
    FIELD_W,
    PLATFORM_H,
    PLAYER_H,
    PLAYER_W,
    Kind,
    Platform,
    Updraft,
)
from core import draw, gfx
from core.base_app import BaseApp
from core.canvas import Canvas
from core.input import Action, is_action
from core.registry import register_app
from core.theme import Color, Theme, lerp_color
from core.widgets import ButtonMenu, draw_panel

ACCENT: Color = (251, 146, 60)
FIELD = pygame.Rect((1280 - int(FIELD_W)) // 2, 40, int(FIELD_W), int(FIELD_H))
DUSK = ((76, 29, 149), (251, 146, 60))  # (top, bottom) near the ground
NIGHT = ((2, 6, 23), (30, 27, 75))  # high up
NIGHT_AT = 15000.0  # height in px where the sky is fully dark
PLATFORM_COLORS: dict[Kind, Color] = {
    "normal": (226, 232, 240),
    "moving": (56, 189, 248),
    "crumble": (180, 140, 100),
    "spring": (74, 222, 128),
}
START_ACTIONS: tuple[Action, ...] = ("action", "up", "left", "right")


@register_app
class UpdraftApp(BaseApp):
    """Bounce from platform to platform and climb as high as you can."""

    @classmethod
    def draw_icon(cls, surface: Canvas, rect: pygame.Rect, theme: Theme) -> None:
        icon = draw.vertical_gradient(rect.size, DUSK[0], DUSK[1], surface.scale).copy()
        u = rect.width / 10
        for px, py, w in ((1.2, 7.6, 3.4), (5.4, 5.0, 3.2), (2.0, 2.6, 3.0)):
            gfx.rect(icon, (226, 232, 240), (px * u, py * u, w * u, 0.7 * u), border_radius=u)
        gfx.circle(icon, (255, 237, 213), (6.9 * u, 3.6 * u), 0.9 * u)
        draw.round_corners(icon, theme.radius.md)
        surface.blit(icon, rect.topleft)

    # ------------------------------------------------------------------ lifecycle
    def on_enter(self) -> None:
        rng = random.Random(11)  # fixed stars so they don't change between runs
        self.stars = [
            (rng.uniform(0, FIELD_W), rng.uniform(0, 3000), rng.uniform(0.7, 1.8))
            for _ in range(120)
        ]
        self._new_game()

    def restart(self) -> None:
        self._new_game()

    def _new_game(self) -> None:
        self.game = Updraft(random.Random())
        self.menu: ButtonMenu | None = None
        self.new_best = False

    def _steer(self) -> float:
        return float(self.input.held("right")) - float(self.input.held("left"))

    # ------------------------------------------------------------------ events
    def handle_event(self, event: pygame.event.Event) -> None:
        if self.menu is not None:
            self.menu.handle_event(event)
            return
        if self.game.state == "ready" and any(
            is_action(event, a, repeat=False) for a in START_ACTIONS
        ):
            self.game.start()

    def update(self, dt: float) -> None:
        if self.menu is not None:
            self.menu.update(dt)
            return
        g = self.game
        g.update(dt, self._steer())
        self.unlock_milestones(g.score, {"height_100": 100, "height_500": 500, "height_1000": 1000})
        if g.springs_used >= 10:
            self.unlock("springs_10")
        if g.state == "over":
            self.new_best = g.score > 0 and self.submit_score(g.score)
            self.menu = ButtonMenu(
                self.theme,
                (FIELD.centerx, FIELD.centery + 70),
                [("Climb again", self._new_game), ("Back to menu", self.exit_to_launcher)],
                accent=ACCENT,
            )

    # ------------------------------------------------------------------ drawing
    def _screen_y(self, world_y: float) -> float:
        return FIELD_H - (world_y - self.game.camera)

    def draw(self, surface: Canvas) -> None:
        t = self.theme
        g = self.game
        surface.fill(t.palette.bg)
        k = round(min(1.0, max(0.0, g.camera / NIGHT_AT)) * 40) / 40  # quantised: cached
        top = lerp_color(DUSK[0], NIGHT[0], k)
        bottom = lerp_color(DUSK[1], NIGHT[1], k)
        field = draw.vertical_gradient(FIELD.size, top, bottom, surface.scale).copy()
        self._draw_stars(field, k, top, bottom)
        for p in g.platforms:
            self._draw_platform(field, p)
        self._draw_player(field)
        if g.state != "ready":
            draw.text(
                field,
                str(g.score),
                t.font(56, "bold"),
                (255, 255, 255),
                (FIELD_W / 2, 20),
                "midtop",
            )
        draw.round_corners(field, t.radius.lg)
        draw.shadow(surface, FIELD, t.radius.lg, t.palette.shadow, (0, 8), 16)
        surface.blit(field, FIELD.topleft)
        self._draw_side(surface, t)
        if g.state == "ready":
            left, right = self.input.label("left"), self.input.label("right")
            prompt = f"{left} / {right} to steer · {self.input.label('action')} to start"
            font = t.font(t.size.label, "semibold")
            pill = pygame.Rect(0, 0, font.size(prompt)[0] + 36, 44)
            pill.center = (FIELD.centerx, round(FIELD.y + FIELD_H * 0.4))
            draw.rounded_rect(surface, pill, (15, 10, 40, 190), 22)
            draw.text(surface, prompt, font, (255, 255, 255), pill.center, "center")
        if self.menu is not None:
            self._draw_over(surface, t)

    def _draw_stars(self, field: Canvas, night: float, top: Color, bottom: Color) -> None:
        if night <= 0.05:
            return
        g = self.game
        for x, y, r in self.stars:
            sy = (y + g.camera * 0.15) % 3000
            if sy > FIELD_H:
                continue
            twinkle = 0.55 + 0.45 * math.sin(g.time * 2 + x)
            sky = lerp_color(top, bottom, sy / FIELD_H)
            color = lerp_color(sky, (255, 255, 255), twinkle * night)
            gfx.circle(field, color, (x, sy), r)

    def _draw_platform(self, field: Canvas, p: Platform) -> None:
        y = self._screen_y(p.y)
        if y < -20 or y > FIELD_H + 20:
            return
        color = PLATFORM_COLORS[p.kind]
        rect = pygame.Rect(round(p.x), round(y), round(p.w), round(PLATFORM_H))
        shade = lerp_color(color, (0, 0, 0), 0.35)
        if p.broken:  # two halves drifting apart as they fall
            half = rect.width // 2 - 2
            for dx in (-1, 1):
                piece = pygame.Rect(0, 0, half, rect.height)
                piece.center = (rect.centerx + dx * (half / 2 + 6), rect.centery)
                gfx.rect(field, shade, piece.move(0, 4), border_radius=6)
                gfx.rect(field, lerp_color(color, (0, 0, 0), 0.15), piece, border_radius=6)
            return
        gfx.rect(field, shade, rect.move(0, 4), border_radius=7)
        gfx.rect(field, color, rect, border_radius=7)
        if p.kind == "crumble":
            for i in range(1, 4):
                cx = rect.x + rect.width * i / 4
                gfx.line(field, shade, (cx - 3, rect.y + 2), (cx + 3, rect.bottom - 2), 2)
        elif p.kind == "spring":
            cx = rect.centerx
            for i in range(3):
                yy = rect.y - 4 - i * 5
                gfx.line(field, (21, 128, 61), (cx - 9, yy), (cx + 9, yy - 3), 3)
            gfx.rect(field, color, (cx - 12, rect.y - 20, 24, 6), border_radius=3)
        elif p.kind == "moving":
            for dx in (-1, 1):
                ax = rect.centerx + dx * (rect.width / 2 - 10)
                gfx.polygon(
                    field,
                    shade,
                    [
                        (ax + dx * 5, rect.centery),
                        (ax - dx * 2, rect.y + 3),
                        (ax - dx * 2, rect.bottom - 3),
                    ],
                )

    def _draw_player(self, field: Canvas) -> None:
        g = self.game
        squash = max(0.0, 1 - g.since_bounce / 0.15) * 0.35
        w = PLAYER_W * (1 + squash)
        h = PLAYER_H * (1 - squash) * (1 + min(0.15, max(0.0, g.vy / 9000)))
        feet = self._screen_y(g.y)
        for wrap in (-FIELD_W, 0.0, FIELD_W):  # draw across the wrap seam
            cx = g.x + wrap
            if cx < -w or cx > FIELD_W + w:
                continue
            body = pygame.Rect(0, 0, round(w), round(h))
            body.midbottom = (round(cx), round(feet))
            glow = body.inflate(24, 24)
            draw.rounded_rect(field, glow, (*ACCENT, 50), glow.width // 2)
            draw.rounded_rect(field, body, (255, 237, 213), round(min(w, h) / 2.2))
            look = max(-4.0, min(4.0, g.vx / 100))
            for ex in (-7, 7):
                eye = (body.centerx + ex + look, body.centery - 3)
                gfx.circle(field, (124, 45, 18), eye, 3.2)

    def _draw_side(self, surface: Canvas, t: Theme) -> None:
        p = t.palette
        g = self.game
        x = 80
        draw.text(surface, "Updraft", t.font(t.size.heading, "bold"), p.text, (x, 60))
        draw.text(surface, "Bounce up. Don't fall.", t.font(t.size.label), p.text_muted, (x, 104))
        best = self.best_score()
        rows = (
            ("Height", str(g.score)),
            ("Best", f"{max(g.score, int(best.score) if best else 0)}"),
            ("Springs", str(g.springs_used)),
        )
        for i, (label, value) in enumerate(rows):
            y = 160 + i * 74
            draw.text(
                surface, label.upper(), t.font(t.size.caption, "semibold"), p.text_muted, (x, y)
            )
            draw.text(surface, value, t.font(t.size.heading, "bold"), p.text, (x, y + 20))
        lx = FIELD.right + 48
        draw.text(surface, "Platforms", t.font(t.size.title, "bold"), p.text, (lx, 60))
        legend: tuple[tuple[Kind, str], ...] = (
            ("normal", "Solid"),
            ("moving", "Slides side to side"),
            ("crumble", "Breaks after one bounce"),
            ("spring", "Launches you high"),
        )
        for i, (kind, text) in enumerate(legend):
            y = 112 + i * 44
            gfx.rect(surface, PLATFORM_COLORS[kind], (lx, y + 4, 44, 12), border_radius=6)
            draw.text(surface, text, t.font(t.size.label), p.text_muted, (lx + 60, y))
        draw.text(
            surface,
            "The sides wrap around.",
            t.font(t.size.caption),
            p.text_muted,
            (lx, 112 + 4 * 44 + 8),
        )

    def _draw_over(self, surface: Canvas, t: Theme) -> None:
        assert self.menu is not None
        p = t.palette
        panel = pygame.Rect(0, 0, 380, self.menu.rect.height + 150)
        panel.midbottom = (FIELD.centerx, self.menu.rect.bottom + 32)
        draw_panel(surface, panel, t)
        draw.text(
            surface,
            f"Height {self.game.score}",
            t.font(t.size.heading, "bold"),
            p.text,
            (panel.centerx, panel.y + 28),
            "midtop",
        )
        sub = "New best!" if self.new_best else f"{self.game.springs_used} springs used"
        draw.text(
            surface,
            sub,
            t.font(t.size.label, "semibold"),
            p.success if self.new_best else p.text_muted,
            (panel.centerx, panel.y + 74),
            "midtop",
        )
        self.menu.draw(surface)
