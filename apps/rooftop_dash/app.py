"""Rooftop Dash UI: a night skyline in parallax, lit buildings, crates, drones and coins."""

from __future__ import annotations

import math
import random

import pygame

from apps.rooftop_dash.logic import (
    COIN_R,
    PLAYER_SCREEN_X,
    PX_PER_POINT,
    Obstacle,
    Roof,
    RooftopDash,
)
from core import draw, gfx
from core.base_app import BaseApp
from core.canvas import Canvas
from core.input import Action, is_action
from core.registry import register_app
from core.theme import Color, Theme, lerp_color
from core.widgets import ButtonMenu, draw_panel

ACCENT: Color = (244, 114, 182)
COIN: Color = (250, 204, 21)
VIEW = pygame.Rect(80, 60, 1120, 600)
SKY = ((15, 23, 42), (76, 29, 149))
FAR = (40, 32, 92)
NEAR = (30, 24, 70)
BUILDING = (24, 24, 38)
LEDGE = (99, 102, 241)
WINDOW = (253, 224, 71)
RUNNER = ACCENT
JUMP_ACTIONS: tuple[Action, ...] = ("action", "up")
#: Screen height (from the top of the view) where the camera keeps the runner's roof.
HORIZON = 0.68


@register_app
class RooftopDashApp(BaseApp):
    """Run the rooftops: jump the gaps, hop the crates, slide under the drones."""

    @classmethod
    def draw_icon(cls, surface: Canvas, rect: pygame.Rect, theme: Theme) -> None:
        icon = draw.vertical_gradient(rect.size, SKY[0], SKY[1], surface.scale).copy()
        u = rect.width / 10
        for bx, by, bw in ((-0.5, 6.4, 4.6), (5.6, 7.2, 5.0)):
            gfx.rect(icon, BUILDING, (bx * u, by * u, bw * u, 10 * u))
            gfx.rect(icon, LEDGE, (bx * u, by * u, bw * u, 0.35 * u))
        # A runner mid-leap over the gap: head, torso, a reaching arm and split legs.
        w = max(2, round(0.5 * u))
        hip, neck = (4.6 * u, 4.9 * u), (5.1 * u, 3.6 * u)
        gfx.line(icon, RUNNER, neck, hip, w + 1)
        gfx.line(icon, RUNNER, hip, (6.1 * u, 5.5 * u), w)
        gfx.line(icon, RUNNER, (6.1 * u, 5.5 * u), (6.0 * u, 6.3 * u), w)
        gfx.line(icon, RUNNER, hip, (3.5 * u, 5.3 * u), w)
        gfx.line(icon, RUNNER, (3.5 * u, 5.3 * u), (2.8 * u, 5.9 * u), w)
        gfx.line(icon, RUNNER, (5.0 * u, 3.9 * u), (6.2 * u, 3.4 * u), w)
        gfx.line(icon, RUNNER, (5.0 * u, 3.9 * u), (4.0 * u, 4.4 * u), w)
        gfx.circle(icon, (255, 228, 230), (5.4 * u, 2.9 * u), 0.62 * u)
        gfx.circle(icon, COIN, (7.6 * u, 3.4 * u), 0.55 * u)
        draw.round_corners(icon, theme.radius.md)
        surface.blit(icon, rect.topleft)

    # ------------------------------------------------------------------ lifecycle
    def on_enter(self) -> None:
        rng = random.Random(5)  # fixed skyline so it doesn't change between runs
        self.far = [(rng.uniform(50, 110), rng.uniform(80, 260)) for _ in range(30)]
        self.near = [(rng.uniform(70, 150), rng.uniform(60, 200)) for _ in range(24)]
        self.stars = [
            (rng.uniform(0, VIEW.width), rng.uniform(0, VIEW.height * 0.5)) for _ in range(60)
        ]
        self._new_game()

    def restart(self) -> None:
        self._new_game()

    def _new_game(self) -> None:
        self.game = RooftopDash(random.Random())
        self.cam_y = self.game.y
        self.menu: ButtonMenu | None = None
        self.new_best = False
        self.sparkles: list[tuple[float, float, float]] = []  # world x, y, age

    # ------------------------------------------------------------------ events
    def handle_event(self, event: pygame.event.Event) -> None:
        if self.menu is not None:
            self.menu.handle_event(event)
            return
        if any(is_action(event, a, repeat=False) for a in JUMP_ACTIONS) or (
            event.type == pygame.MOUSEBUTTONDOWN and event.button == 1
        ):
            self.game.jump()

    def update(self, dt: float) -> None:
        self.sparkles = [(x, y, age + dt) for x, y, age in self.sparkles if age < 0.4]
        if self.menu is not None:
            self.menu.update(dt)
            return
        g = self.game
        holding = any(self.input.held(a) for a in JUMP_ACTIONS) or pygame.mouse.get_pressed()[0]
        before = g.coins
        g.update(dt, holding, self.input.held("down"))
        if g.coins > before:
            self.sparkles.append((g.x, g.y + g.height / 2, 0.0))
        # The camera follows the roof the runner is on, gently.
        target = g.y if g.grounded else min(g.y, self.cam_y + 120)
        self.cam_y += (target - self.cam_y) * min(1.0, dt * 3)
        self.unlock_milestones(g.score, {"run_500": 500, "run_2000": 2000})
        if g.coins >= 50:
            self.unlock("coins_50")
        if g.drones_ducked >= 10:
            self.unlock("drones_10")
        if g.state == "over":
            self.new_best = g.score > 0 and self.submit_score(g.score)
            self.menu = ButtonMenu(
                self.theme,
                (VIEW.centerx, VIEW.centery + 60),
                [("Run again", self._new_game), ("Back to menu", self.exit_to_launcher)],
                accent=ACCENT,
            )

    # ------------------------------------------------------------------ drawing
    def _sx(self, x: float) -> float:
        return x - self.game.camera

    def _sy(self, y: float) -> float:
        return VIEW.height * HORIZON - (y - self.cam_y)

    def draw(self, surface: Canvas) -> None:
        t = self.theme
        g = self.game
        surface.fill(t.palette.bg)
        view = draw.vertical_gradient(VIEW.size, SKY[0], SKY[1], surface.scale).copy()
        for i, (x, y) in enumerate(self.stars):
            sx = (x - g.camera * 0.02) % VIEW.width
            tw = 0.5 + 0.5 * math.sin(g.time * 1.5 + i)
            gfx.circle(view, lerp_color(SKY[0], (255, 255, 255), 0.4 + 0.5 * tw), (sx, y), 1.2)
        gfx.circle(view, (254, 243, 199), (VIEW.width - 160, 110), 38)
        sky_at_moon = lerp_color(SKY[0], SKY[1], 100 / VIEW.height)
        gfx.circle(view, sky_at_moon, (VIEW.width - 146, 100), 34)  # cut out a crescent
        self._skyline(view, self.far, FAR, 0.1, 0.55)
        self._skyline(view, self.near, NEAR, 0.25, 0.68)
        for roof in g.roofs:
            self._draw_roof(view, roof)
        for coin in g.coin_list:
            if not coin.taken:
                self._draw_coin(view, coin.x, coin.y)
        for ob in g.obstacles:
            self._draw_obstacle(view, ob)
        for x, y, age in self.sparkles:
            k = age / 0.4
            gfx.circle(
                view, lerp_color(COIN, SKY[1], k), (self._sx(x), self._sy(y)), 10 + 20 * k, 2
            )
        self._draw_runner(view)
        self._draw_hud(view, t)
        draw.round_corners(view, t.radius.lg)
        draw.shadow(surface, VIEW, t.radius.lg, t.palette.shadow, (0, 8), 16)
        surface.blit(view, VIEW.topleft)
        p = t.palette
        draw.text(
            surface, "Rooftop Dash", t.font(t.size.title, "bold"), p.text, (VIEW.x, 32), "midleft"
        )
        jump, down = self.input.label("action"), self.input.label("down")
        hint = f"{jump} / {self.input.label('up')} jump (hold for height) · {down} slide"
        draw.text(surface, hint, t.font(t.size.caption), p.text_muted, (VIEW.right, 32), "midright")
        if g.state == "ready":
            font = t.font(t.size.title, "semibold")
            text = f"Press {jump} to run"
            pill = pygame.Rect(0, 0, font.size(text)[0] + 48, 56)
            pill.center = (VIEW.centerx, VIEW.y + 200)
            draw.rounded_rect(surface, pill, (15, 23, 42, 200), 28)
            draw.text(surface, text, font, (255, 255, 255), pill.center, "center")
        if self.menu is not None:
            self._draw_over(surface, t)

    def _skyline(
        self, view: Canvas, blocks: list[tuple[float, float]], color: Color, k: float, base: float
    ) -> None:
        total = sum(w for w, _ in blocks)
        x = -((self.game.camera * k) % total)
        ground = VIEW.height * base - (self.cam_y - 120) * k * 0.5
        while x < VIEW.width:
            for w, h in blocks:
                if x > VIEW.width:
                    break
                gfx.rect(view, color, (x, ground - h, w - 3, h + VIEW.height))
                x += w

    def _draw_roof(self, view: Canvas, roof: Roof) -> None:
        x0, x1 = self._sx(roof.x0), self._sx(roof.x1)
        if x1 < 0 or x0 > VIEW.width:
            return
        top = self._sy(roof.h)
        gfx.rect(view, BUILDING, (x0, top, x1 - x0, VIEW.height - top + 10))
        gfx.rect(view, LEDGE, (x0 - 4, top, x1 - x0 + 8, 6))
        # Windows: a fixed pattern per building, from its position.
        rng = random.Random(int(roof.x0))
        col_w, row_h = 34, 40
        for cx in range(int(x0) + 18, int(x1) - 24, col_w):
            for cy in range(int(top) + 28, VIEW.height, row_h):
                if rng.random() < 0.3:
                    gfx.rect(
                        view, lerp_color(BUILDING, WINDOW, rng.uniform(0.35, 0.8)), (cx, cy, 14, 18)
                    )
                else:
                    rng.random()

    def _draw_coin(self, view: Canvas, x: float, y: float) -> None:
        sx, sy = self._sx(x), self._sy(y)
        if sx < -20 or sx > VIEW.width + 20:
            return
        squeeze = abs(math.cos(self.game.time * 4 + x * 0.01))
        rect = pygame.Rect(0, 0, max(4, round(COIN_R * 2 * squeeze)), round(COIN_R * 2))
        rect.center = (round(sx), round(sy))
        gfx.ellipse(view, (202, 138, 4), rect)
        gfx.ellipse(view, COIN, rect.inflate(-4, -4))

    def _draw_obstacle(self, view: Canvas, ob: Obstacle) -> None:
        ox, oy, ow, oh = ob.box
        sx, top = self._sx(ox), self._sy(oy + oh)
        if sx + ow < 0 or sx > VIEW.width:
            return
        if ob.kind == "drone":
            body = pygame.Rect(round(sx), round(top), round(ow), round(oh))
            gfx.rect(view, (148, 163, 184), body, border_radius=8)
            gfx.rect(view, (71, 85, 105), body.inflate(-10, -12), border_radius=4)
            blink = (239, 68, 68) if int(self.game.time * 4) % 2 else (127, 29, 29)
            gfx.circle(view, blink, (body.centerx, body.bottom - 3), 3)
            spin = abs(math.sin(self.game.time * 40)) * 14 + 4
            for px in (body.x + 6, body.right - 6):
                gfx.line(view, (203, 213, 225), (px, body.y - 6), (px, body.y), 2)
                gfx.line(view, (226, 232, 240), (px - spin, body.y - 7), (px + spin, body.y - 7), 2)
        else:
            for i in range(round(oh / 34)):
                box = pygame.Rect(round(sx), round(self._sy(oy + 34 * (i + 1))), round(ow), 34)
                gfx.rect(view, (146, 64, 14), box, border_radius=3)
                gfx.rect(view, (180, 83, 9), box.inflate(-6, -6), border_radius=2)
                gfx.line(
                    view,
                    (120, 53, 15),
                    box.inflate(-8, -8).topleft,
                    box.inflate(-8, -8).bottomright,
                    3,
                )
                gfx.line(
                    view,
                    (120, 53, 15),
                    box.inflate(-8, -8).topright,
                    box.inflate(-8, -8).bottomleft,
                    3,
                )

    def _draw_runner(self, view: Canvas) -> None:
        g = self.game
        x, feet = PLAYER_SCREEN_X, self._sy(g.y)
        if g.sliding:
            body = pygame.Rect(0, 0, 50, 22)
            body.midbottom = (round(x), round(feet))
            gfx.rect(view, RUNNER, body, border_radius=11)
            gfx.circle(view, (255, 228, 230), (body.right - 9, body.centery - 2), 8)
            for i in range(3):  # dust trail
                gfx.circle(view, (148, 163, 184), (body.x - 8 - i * 12, feet - 4), 4 - i)
            return
        stride = math.sin(g.time * 18) if g.grounded and g.state == "running" else 0.6
        hip = (x, feet - 26)
        head = (x + 3, feet - 47)
        # Scarf streaming behind.
        wave = math.sin(g.time * 14) * 4
        gfx.polygon(
            view,
            COIN,
            [
                (x - 2, feet - 40),
                (x - 24, feet - 42 + wave),
                (x - 30, feet - 34 + wave),
                (x - 2, feet - 35),
            ],
        )
        gfx.line(view, RUNNER, (x + 2, feet - 40), hip, 8)
        for side in (1, -1):
            k = stride * side
            knee = (hip[0] + 8 * k, hip[1] + 13)
            foot = (hip[0] + 14 * k - 2, feet - 1 if g.grounded else feet - 6)
            gfx.line(view, lerp_color(RUNNER, (0, 0, 0), 0.2 if side < 0 else 0), hip, knee, 6)
            gfx.line(view, lerp_color(RUNNER, (0, 0, 0), 0.2 if side < 0 else 0), knee, foot, 6)
            hand = (x + 2 - 12 * k, feet - 26 - 4 * abs(k))
            gfx.line(view, lerp_color(RUNNER, (0, 0, 0), 0.25), (x + 2, feet - 38), hand, 5)
        gfx.circle(view, (255, 228, 230), head, 10)
        gfx.circle(view, (15, 23, 42), (head[0] + 4, head[1] - 1), 2)

    def _draw_hud(self, view: Canvas, t: Theme) -> None:
        g = self.game
        best = self.best_score()
        draw.text(view, f"{g.score:,}", t.font(44, "bold"), (255, 255, 255), (28, 20))
        coins = f"● {g.coins}"
        draw.text(view, coins, t.font(t.size.title, "bold"), COIN, (30, 76))
        if best:
            draw.text(
                view,
                f"Best {int(best.score):,}",
                t.font(t.size.label, "semibold"),
                (203, 213, 225),
                (VIEW.width - 28, 28),
                "topright",
            )

    def _draw_over(self, surface: Canvas, t: Theme) -> None:
        assert self.menu is not None
        p = t.palette
        g = self.game
        panel = pygame.Rect(0, 0, 400, self.menu.rect.height + 170)
        panel.midbottom = (VIEW.centerx, self.menu.rect.bottom + 32)
        draw_panel(surface, panel, t)
        draw.text(
            surface,
            f"Score {g.score:,}",
            t.font(t.size.heading, "bold"),
            p.text,
            (panel.centerx, panel.y + 26),
            "midtop",
        )
        cause = {
            "fell": "Missed the jump.",
            "wall": "Ran into a wall.",
            "crate": "Tripped on a crate.",
            "double": "Tripped on the crates.",
            "drone": "Clipped by a drone.",
        }.get(g.cause, "")
        sub = "New best!" if self.new_best else cause
        draw.text(
            surface,
            sub,
            t.font(t.size.label, "semibold"),
            p.success if self.new_best else p.text_muted,
            (panel.centerx, panel.y + 72),
            "midtop",
        )
        draw.text(
            surface,
            f"{int(g.x / PX_PER_POINT):,} m · {g.coins} coins",
            t.font(t.size.label),
            p.text_muted,
            (panel.centerx, panel.y + 98),
            "midtop",
        )
        self.menu.draw(surface)
