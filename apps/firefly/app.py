"""Firefly UI: a glowing maze, a firefly, four shades and a side panel."""

from __future__ import annotations

import math
import random
from collections import deque
from typing import Literal

import pygame

from apps.firefly.logic import (
    COLS,
    DOWN,
    HOUSE,
    LEFT,
    MAZE,
    PERSONALITIES,
    PLAYER_START,
    RIGHT,
    ROWS,
    UP,
    Direction,
    Event,
    Firefly,
    Personality,
    Shade,
    Tile,
    step,
    walkable,
)
from core import draw, gfx
from core.base_app import BaseApp
from core.canvas import Canvas
from core.input import Action, action_of, is_action
from core.registry import register_app
from core.theme import Color, Theme, lerp_color
from core.widgets import ButtonMenu, draw_panel

ACCENT: Color = (190, 242, 100)
NIGHT: Color = (8, 14, 18)
HEDGE: Color = (28, 70, 58)
HEDGE_LIGHT: Color = (44, 102, 82)
MOTE: Color = (254, 240, 138)
LANTERN: Color = (251, 146, 60)
FRIGHT: Color = (59, 130, 246)
SHADE_COLORS: dict[Personality, Color] = {
    "stalker": (248, 113, 113),
    "ambusher": (232, 121, 249),
    "flanker": (45, 212, 191),
    "wanderer": (251, 146, 60),
}
SHADE_INFO: dict[Personality, str] = {
    "stalker": "heads straight for you",
    "ambusher": "cuts you off ahead",
    "flanker": "closes in from the other side",
    "wanderer": "keen from afar, shy up close",
}

CELL = 27
MAZE_RECT = pygame.Rect(150, 86, COLS * CELL, ROWS * CELL)
PANEL_X = MAZE_RECT.right + 56
DIRECTIONS: dict[Action, Direction] = {"up": UP, "down": DOWN, "left": LEFT, "right": RIGHT}

State = Literal["ready", "playing", "over"]


def _floor_tiles() -> frozenset[Tile]:
    """Tiles the firefly can reach, plus the shade house (for drawing wall edges)."""
    seen, queue = {PLAYER_START}, deque([PLAYER_START])
    while queue:
        tile = queue.popleft()
        for d in (UP, DOWN, LEFT, RIGHT):
            nxt = step(tile, d)
            if nxt not in seen and walkable(nxt):
                seen.add(nxt)
                queue.append(nxt)
    return frozenset(seen | set(HOUSE))


FLOOR = _floor_tiles()


def center(x: float, y: float) -> tuple[float, float]:
    return MAZE_RECT.x + (x + 0.5) * CELL, MAZE_RECT.y + (y + 0.5) * CELL


@register_app
class FireflyApp(BaseApp):
    """Collect the light, dodge the shades, grab a lantern to turn the tables."""

    @classmethod
    def draw_icon(cls, surface: Canvas, rect: pygame.Rect, theme: Theme) -> None:
        draw.rounded_rect(surface, rect, NIGHT, theme.radius.md)
        u = rect.width / 10
        for i in range(3):
            gfx.circle(surface, MOTE, (rect.x + (5.6 + i * 1.4) * u, rect.y + 6.6 * u), u * 0.3)
        cx, cy = rect.x + 3.4 * u, rect.y + 6.4 * u
        gfx.circle(surface, lerp_color(NIGHT, ACCENT, 0.3), (cx, cy), u * 2.2)
        gfx.circle(surface, ACCENT, (cx, cy), u * 1.25)
        draw_shade_body(
            surface, rect.x + 7.0 * u, rect.y + 3.3 * u, u * 1.5, SHADE_COLORS["stalker"], 0.0
        )
        draw_eyes(surface, rect.x + 7.0 * u, rect.y + 3.0 * u, u * 1.5, LEFT)

    # ------------------------------------------------------------------ lifecycle
    def on_enter(self) -> None:
        self.game = Firefly(random.Random())
        self.state: State = "ready"
        self.menu: ButtonMenu | None = None
        self.time = 0.0
        self.flash = 0.0
        self.popups: list[tuple[float, float, str, float]] = []  # x, y, text, time left
        self.new_best = False

    def restart(self) -> None:
        self._start()

    def _start(self) -> None:
        self.game = Firefly(random.Random())
        self.state = "playing"
        self.menu = None
        self.popups.clear()

    def _game_over(self) -> None:
        self.state = "over"
        self.new_best = self.game.score > 0 and self.submit_score(self.game.score)
        self.menu = ButtonMenu(
            self.theme,
            (MAZE_RECT.centerx, MAZE_RECT.centery + 70),
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
        action = action_of(event)
        if self.state == "ready":
            if is_action(event, "action", repeat=False):
                self._start()
            elif action in DIRECTIONS:
                self._start()
                self.game.want = DIRECTIONS[action]
            return
        if action in DIRECTIONS:
            self.game.want = DIRECTIONS[action]

    def _check_achievements(self) -> None:
        g = self.game
        self.unlock_milestones(g.level, {"clear_1": 2, "level_3": 3})
        self.unlock_milestones(g.combo, {"combo_4": 4})

    def update(self, dt: float) -> None:
        self.time += dt
        self.flash = max(0.0, self.flash - dt)
        self.popups = [(x, y, s, t - dt) for x, y, s, t in self.popups if t - dt > 0]
        if self.menu is not None:
            self.menu.update(dt)
        if self.state != "playing":
            return
        for event in self.game.update(dt):
            self._on_event(event)
        self._check_achievements()
        if self.game.over:
            self._game_over()

    def _on_event(self, event: Event) -> None:
        if event.kind == "shade_caught":
            x, y = center(*event.tile)
            self.popups.append((x, y, str(event.points), 1.0))
        elif event.kind == "player_caught":
            self.flash = 0.5

    # ------------------------------------------------------------------ drawing
    def draw(self, surface: Canvas) -> None:
        t = self.theme
        surface.fill(t.palette.bg)
        frame = MAZE_RECT.inflate(24, 24)
        draw.shadow(surface, frame, t.radius.lg, t.palette.shadow, (0, 8), 16)
        draw.rounded_rect(surface, frame, NIGHT, t.radius.lg)
        self._draw_walls(surface)
        self._draw_items(surface)
        g = self.game
        clip = surface.get_clip()
        surface.set_clip(MAZE_RECT)
        if self.state != "over" or g.pause > 0:
            for shade in g.shades:
                self._draw_shade(surface, shade)
            self._draw_player(surface)
        surface.set_clip(clip)
        for x, y, text, left in self.popups:
            draw.text(
                surface,
                text,
                t.font(t.size.label, "bold"),
                (*ACCENT, round(255 * min(1.0, left * 2))),
                (x, y - (1 - left) * 24),
                "center",
            )
        if self.flash > 0:
            draw.overlay(surface, (255, 255, 255, round(70 * self.flash)))
        self._draw_panel(surface, t)

        if self.state == "ready":
            moves = self.input.labels("up", "down", "left", "right", sep="")
            self._draw_card(
                surface, t, "Firefly", f"{moves} to fly · {self.input.label('action')} to start"
            )
        elif self.state == "playing" and g.pending == "level":
            self._banner(surface, t, "Maze cleared!")
        elif self.state == "playing" and g.pending == "respawn":
            self._banner(surface, t, "Caught!")
        elif self.state == "over" and self.menu is not None:
            sub = "New high score!" if self.new_best else f"Score {g.score:,} · level {g.level}"
            self._draw_card(surface, t, "Game over", sub, self.menu.rect.height + 30, self.new_best)
            self.menu.draw(surface)

    def _draw_walls(self, surface: Canvas) -> None:
        """Walls are drawn as rounded hedges: an inset block per tile, bridged to
        neighbouring wall tiles so each wall reads as one soft shape."""
        inset = 4
        size = CELL - 2 * inset

        def wall(c: int, r: int) -> bool:
            return 0 <= r < ROWS and 0 <= c < COLS and MAZE[r][c] == "#"

        for color, lift in ((HEDGE, 0), (HEDGE_LIGHT, -2)):
            for r, row in enumerate(MAZE):
                for c, ch in enumerate(row):
                    if ch != "#":
                        continue
                    x, y = MAZE_RECT.x + c * CELL + inset, MAZE_RECT.y + r * CELL + inset + lift
                    h = size if lift == 0 else 4  # the highlight is a thin top edge
                    if lift and wall(c, r - 1):
                        continue
                    gfx.rect(surface, color, (x, y, size, h), border_radius=6 if lift == 0 else 2)
                    if wall(c + 1, r) and (lift == 0 or not wall(c + 1, r - 1)):
                        gfx.rect(surface, color, (x + size // 2, y, CELL, h))
                    if lift == 0 and wall(c, r + 1):
                        gfx.rect(surface, color, (x, y + size // 2, size, CELL))
                        if wall(c + 1, r) and wall(c + 1, r + 1):
                            gfx.rect(surface, color, (x + size // 2, y + size // 2, CELL, CELL))
        door = MAZE_RECT.x + 0, MAZE_RECT.y
        for r, row in enumerate(MAZE):
            for c, ch in enumerate(row):
                if ch == "-":
                    x, y = door[0] + c * CELL, door[1] + r * CELL
                    gfx.rect(
                        surface,
                        (253, 186, 116),
                        (x + 2, y + CELL / 2 - 2, CELL - 4, 4),
                        border_radius=2,
                    )

    def _draw_items(self, surface: Canvas) -> None:
        g = self.game
        for i, tile in enumerate(sorted(g.motes)):
            twinkle = 0.7 + 0.3 * math.sin(self.time * 3 + i * 1.3)
            gfx.circle(surface, lerp_color(NIGHT, MOTE, 0.25 * twinkle), center(*tile), 5)
            gfx.circle(surface, lerp_color(NIGHT, MOTE, twinkle), center(*tile), 2.2)
        pulse = 0.5 + 0.5 * math.sin(self.time * 5)
        for tile in g.lanterns:
            draw_lantern(surface, *center(*tile), pulse)

    def _positions(self, x: float, y: float) -> list[tuple[float, float]]:
        """The actor's pixel centre, plus a copy when it is crossing a tunnel edge."""
        px, py = center(x, y)
        out = [(px, py)]
        if x < 0:
            out.append((px + COLS * CELL, py))
        elif x > COLS - 1:
            out.append((px - COLS * CELL, py))
        return out

    def _draw_player(self, surface: Canvas) -> None:
        g = self.game
        p = g.player
        if g.pending == "respawn":
            fade = max(0.0, g.pause - 0.6)
            if fade <= 0:
                return
        direction = p.direction if p.direction != (0, 0) else (g.want if g.want != (0, 0) else LEFT)
        for px, py in self._positions(p.x, p.y):
            glow = 0.55 + 0.25 * math.sin(self.time * 7)
            gfx.circle(surface, lerp_color(NIGHT, ACCENT, 0.18 + 0.1 * glow), (px, py), CELL * 0.85)
            gfx.circle(surface, lerp_color(NIGHT, ACCENT, 0.4), (px, py), CELL * 0.55)
            # Wings flutter at right angles to the flight direction.
            flap = math.sin(self.time * 30) * 0.25 + 0.75
            side = pygame.Vector2(-direction[1], direction[0])
            back = pygame.Vector2(direction) * -3
            for sign in (-1, 1):
                wing = pygame.FRect(0, 0, 9, 9)
                wing.center = pygame.Vector2(px, py) + side * sign * 8 * flap + back
                gfx.ellipse(surface, (226, 232, 240), wing)
            gfx.circle(surface, ACCENT, (px, py), CELL * 0.3)
            gfx.circle(
                surface,
                (247, 254, 231),
                (px + direction[0] * 3, py + direction[1] * 3),
                CELL * 0.12,
            )

    def _draw_shade(self, surface: Canvas, s: Shade) -> None:
        g = self.game
        if s.state == "returning":
            color = None
        elif s.frightened:
            ending = g.fright_timer < 2 and int(self.time * 8) % 2 == 0
            color = (226, 232, 240) if ending else FRIGHT
        else:
            color = SHADE_COLORS[s.personality]
        for px, py in self._positions(s.x, s.y):
            if color is not None:
                draw_shade_body(surface, px, py, CELL * 0.9, color, self.time)
            if s.frightened:
                for dx in (-3.5, 3.5):
                    gfx.circle(surface, (254, 226, 226), (px + dx, py - 2), 2)
                pts = [(px - 6 + i * 3, py + 5 + (2 if i % 2 else -1)) for i in range(5)]
                gfx.lines(surface, (254, 226, 226), False, pts, 1.5)
            else:
                draw_eyes(surface, px, py - 1, CELL * 0.9, s.direction)

    def _draw_panel(self, surface: Canvas, t: Theme) -> None:
        p = t.palette
        g = self.game
        x = PANEL_X
        draw.text(surface, "Firefly", t.font(t.size.heading, "bold"), p.text, (x, MAZE_RECT.y - 6))
        draw.text(
            surface, f"{g.score:,}", t.font(t.size.display, "bold"), ACCENT, (x, MAZE_RECT.y + 40)
        )
        best = self.best_score()
        best_text = f"Best {int(best.score):,}" if best else "No best yet"
        draw.text(
            surface,
            f"Level {g.level} · {best_text}",
            t.font(t.size.label),
            p.text_muted,
            (x, MAZE_RECT.y + 100),
        )
        for i in range(max(0, g.lives)):
            cx, cy = x + 12 + i * 30, MAZE_RECT.y + 150
            gfx.circle(surface, lerp_color(p.bg, ACCENT, 0.3), (cx, cy), 12)
            gfx.circle(surface, ACCENT, (cx, cy), 7)

        card = pygame.Rect(x, MAZE_RECT.y + 190, 1280 - 48 - x, 4 * 54 + 64)
        draw_panel(surface, card, t)
        draw.text(
            surface,
            "THE SHADES",
            t.font(t.size.caption, "semibold"),
            p.text_muted,
            (card.x + 20, card.y + 18),
        )
        for i, personality in enumerate(PERSONALITIES):
            cy = card.y + 66 + i * 54
            draw_shade_body(surface, card.x + 34, cy, 26, SHADE_COLORS[personality], self.time + i)
            draw_eyes(surface, card.x + 34, cy - 1, 26, RIGHT)
            draw.text(
                surface,
                personality.title(),
                t.font(t.size.label, "semibold"),
                p.text,
                (card.x + 62, cy - 2),
                "bottomleft",
            )
            draw.text(
                surface,
                SHADE_INFO[personality],
                t.font(t.size.caption),
                p.text_muted,
                (card.x + 62, cy + 2),
            )
        hint = f"Lanterns let you catch shades · {self.input.label('pause')} pause"
        draw.text(surface, hint, t.font(t.size.caption), p.text_muted, (x, card.bottom + 18))

    def _banner(self, surface: Canvas, t: Theme, text: str) -> None:
        font = t.font(t.size.heading, "bold")
        rect = pygame.Rect(0, 0, font.size(text)[0] + 48, 56)
        rect.center = MAZE_RECT.center
        draw_panel(surface, rect, t)
        draw.text(surface, text, font, ACCENT, rect.center, "center")

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
        panel = pygame.Rect(0, 0, 440, 130 + extra)
        panel.midtop = (MAZE_RECT.centerx, MAZE_RECT.centery - 110)
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


def draw_shade_body(
    surface: Canvas, x: float, y: float, size: float, color: Color, time: float
) -> None:
    """A will-o'-wisp: a round body under a flickering flame-like tip."""
    r = size / 2
    body_y = y + r * 0.2
    flicker = math.sin(time * 11) * r * 0.18
    sway = math.sin(time * 7) * r * 0.2
    tip = (x + sway, y - r * 1.15 + flicker)
    gfx.polygon(
        surface,
        color,
        [
            (x - r * 0.78, body_y - r * 0.1),
            (x - r * 0.3, y - r * 0.55),
            tip,
            (x + r * 0.35, y - r * 0.5),
            (x + r * 0.78, body_y - r * 0.1),
        ],
    )
    gfx.circle(surface, color, (x, body_y), r * 0.8)


def draw_lantern(surface: Canvas, x: float, y: float, pulse: float) -> None:
    """A small paper lantern with a warm halo."""
    gfx.circle(surface, lerp_color(NIGHT, LANTERN, 0.18 + 0.12 * pulse), (x, y), 12 + 2 * pulse)
    body = pygame.FRect(0, 0, 13, 15)
    body.center = (x, y)
    gfx.rect(surface, LANTERN, body, border_radius=6)
    gfx.rect(surface, (253, 230, 138), body.inflate(-7, -6), border_radius=3)
    for cap_y in (body.top, body.bottom - 3):
        gfx.rect(surface, (120, 53, 15), (x - 4, cap_y, 8, 3), border_radius=1)


def draw_eyes(surface: Canvas, x: float, y: float, size: float, direction: Direction) -> None:
    r = size / 2
    for side in (-1, 1):
        ex, ey = x + side * r * 0.36, y - r * 0.2
        gfx.circle(surface, (255, 255, 255), (ex, ey), r * 0.26)
        gfx.circle(
            surface,
            (30, 41, 59),
            (ex + direction[0] * r * 0.11, ey + direction[1] * r * 0.11),
            r * 0.13,
        )
