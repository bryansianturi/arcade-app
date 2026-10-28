"""Crate Keeper UI: level select, a warehouse floor, sliding crates and a keeper."""

from __future__ import annotations

import math
from typing import Literal

import pygame

from apps.crate_keeper.logic import DIRECTIONS, Game, Level, Pos, load_levels
from core import draw, gfx
from core.base_app import BaseApp
from core.canvas import Canvas, mouse_pos
from core.input import action_of, is_action
from core.registry import register_app
from core.theme import Color, Theme, lerp_color
from core.widgets import Button, ButtonMenu, Grid, draw_panel

ACCENT: Color = (217, 119, 6)
FLOOR: Color = (51, 47, 58)
FLOOR_ALT: Color = (56, 52, 64)
WALL: Color = (99, 86, 122)
WALL_TOP: Color = (129, 115, 155)
GOAL: Color = (250, 204, 21)
CRATE: Color = (194, 128, 64)
CRATE_DARK: Color = (138, 86, 40)
CRATE_HOME: Color = (74, 222, 128)
KEEPER: Color = (96, 165, 250)

BOARD_AREA = pygame.Rect(48, 96, 820, 584)
SIDE_X = 912
SLIDE_SECONDS = 0.09

Screen = Literal["levels", "play"]


@register_app
class CrateKeeperApp(BaseApp):
    """Push every crate onto a target. Plan ahead: crates can't be pulled."""

    @classmethod
    def draw_icon(cls, surface: Canvas, rect: pygame.Rect, theme: Theme) -> None:
        draw.rounded_rect(surface, rect, FLOOR, theme.radius.md)
        u = rect.width / 10
        crate = pygame.Rect(0, 0, round(u * 5), round(u * 5))
        crate.center = (round(rect.x + u * 5.6), round(rect.y + u * 4.4))
        draw_crate(surface, crate, False)
        gfx.circle(surface, GOAL, (rect.x + u * 5.6, rect.y + u * 8.2), u * 0.9, max(1.5, u * 0.35))
        gfx.circle(surface, KEEPER, (rect.x + u * 2.2, rect.y + u * 5.0), u * 1.4)

    # ------------------------------------------------------------------ lifecycle
    def on_enter(self) -> None:
        self.levels: list[Level] = load_levels()
        best = self.data.get("best", {})
        self.best: dict[str, list[int]] = best if isinstance(best, dict) else {}
        t = self.theme
        self.screen: Screen = "levels"
        grid = Grid(pygame.Rect(48, 150, 1184, 520), 5, 108, 16)
        self.level_cards = [grid.cell(i) for i in range(len(self.levels))]
        self.cursor = min(self._first_unsolved(), len(self.levels) - 1)
        self.keyboard = False
        bx = SIDE_X
        self.buttons = [
            Button(t, (bx, 470, 150, 44), "Undo", self._undo),
            Button(t, (bx + 162, 470, 150, 44), "Restart", self._restart_level),
            Button(t, (bx, 526, 312, 44), "All levels", self._to_levels, "ghost"),
        ]
        self.menu: ButtonMenu | None = None
        self.time = 0.0
        self.index = 0
        self.game = Game(self.levels[0])
        self.slide: tuple[Pos, Pos | None, Pos | None, float] | None = None

    def on_exit(self) -> None:
        self.data["best"] = self.best
        self.data.save()

    def restart(self) -> None:
        if self.screen == "play":
            self._restart_level()

    def captures_pause(self) -> bool:
        return self.screen == "play" and self.menu is None  # Esc returns to the level list

    def _first_unsolved(self) -> int:
        return next(
            (i for i in range(len(self.levels)) if str(i) not in self.best), len(self.levels)
        )

    def unlocked(self, index: int) -> bool:
        return index <= self._first_unsolved()

    # ------------------------------------------------------------------ navigation
    def _open(self, index: int) -> None:
        if not self.unlocked(index):
            return
        self.index = index
        self.game = Game(self.levels[index])
        self.screen = "play"
        self.menu = None
        self.slide = None

    def _to_levels(self) -> None:
        self.screen = "levels"
        self.menu = None
        self.cursor = self.index

    def _undo(self) -> None:
        if self.menu is None and self.game.undo():
            self.slide = None

    def _restart_level(self) -> None:
        self.game.restart()
        self.menu = None
        self.slide = None

    def _next(self) -> None:
        if self.index + 1 < len(self.levels):
            self._open(self.index + 1)
        else:
            self._to_levels()

    def _step(self, direction: str) -> None:
        if self.menu is not None or self.screen != "play":
            return
        before_player = self.game.player
        dr, dc = DIRECTIONS[direction]
        result = self.game.move(direction)
        if result == "blocked":
            return
        box_from = (before_player[0] + dr, before_player[1] + dc) if result == "push" else None
        box_to = (box_from[0] + dr, box_from[1] + dc) if box_from else None
        self.slide = (before_player, box_from, box_to, 0.0)
        if self.game.solved:
            self._on_solved()

    def _on_solved(self) -> None:
        g = self.game
        key = str(self.index)
        old = self.best.get(key)
        self.new_best = old is None or g.moves < old[0]
        if self.new_best:
            self.best[key] = [g.moves, g.pushes]
            self.data["best"] = self.best
            self.data.save()
        solved = len(self.best)
        self.unlock_milestones(solved, {"solve_1": 1, "solve_5": 5, "solve_all": len(self.levels)})
        items = [("Levels", self._to_levels)]
        if self.index + 1 < len(self.levels):
            items.insert(0, ("Next level", self._next))
        self.menu = ButtonMenu(
            self.theme, (BOARD_AREA.centerx, BOARD_AREA.centery + 60), items, accent=ACCENT
        )

    # ------------------------------------------------------------------ events
    def handle_event(self, event: pygame.event.Event) -> None:
        if self.screen == "levels":
            self._levels_event(event)
            return
        if self.menu is not None:
            self.menu.handle_event(event)
            return
        for button in self.buttons:
            if button.handle_event(event):
                return
        action = action_of(event)
        if action in DIRECTIONS:
            self._step(action)  # held keys repeat, so you can walk along a corridor
        elif action == "pause" and not event.repeat:
            self._to_levels()
        elif event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_u, pygame.K_BACKSPACE) or (
                event.key == pygame.K_z and event.mod & (pygame.KMOD_CTRL | pygame.KMOD_META)
            ):
                self._undo()
            elif event.key == pygame.K_r:
                self._restart_level()

    def _levels_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.MOUSEMOTION:
            self.keyboard = False
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for i, rect in enumerate(self.level_cards):
                if rect.collidepoint(event.pos):
                    self._open(i)
            return
        action = action_of(event)
        if action is None:
            return
        self.keyboard = True
        moves = {"left": -1, "right": 1, "up": -5, "down": 5}
        if action in moves:
            self.cursor = max(0, min(len(self.levels) - 1, self.cursor + moves[action]))
        elif is_action(event, "action", repeat=False):
            self._open(self.cursor)

    # ------------------------------------------------------------------ frame
    def update(self, dt: float) -> None:
        self.time += dt
        if self.slide is not None:
            p, bf, bt, k = self.slide
            k += dt / SLIDE_SECONDS
            self.slide = None if k >= 1 else (p, bf, bt, k)
        for button in self.buttons:
            button.update(dt)
        self.buttons[0].enabled = self.game.can_undo and self.menu is None
        if self.menu is not None:
            self.menu.update(dt)

    # ------------------------------------------------------------------ drawing
    def draw(self, surface: Canvas) -> None:
        t = self.theme
        surface.fill(t.palette.bg)
        if self.screen == "levels":
            self._draw_levels(surface, t)
        else:
            self._draw_play(surface, t)

    def _draw_levels(self, surface: Canvas, t: Theme) -> None:
        p = t.palette
        draw.text(surface, "Crate Keeper", t.font(t.size.heading, "bold"), p.text, (48, 44))
        solved = len(self.best)
        draw.text(
            surface,
            f"{solved} of {len(self.levels)} solved · push every crate onto a target",
            t.font(t.size.label),
            p.text_muted,
            (48, 92),
        )
        for i, rect in enumerate(self.level_cards):
            open_ = self.unlocked(i)
            done = str(i) in self.best
            hover = open_ and not self.keyboard and rect.collidepoint(mouse_pos())
            draw_panel(surface, rect, t)
            if (self.keyboard and i == self.cursor) or hover:
                draw.rounded_rect(surface, rect.inflate(6, 6), ACCENT, t.radius.lg + 3, 2)
            number = t.font(t.size.title, "bold")
            color = ACCENT if done else p.text if open_ else p.text_muted
            draw.text(surface, f"{i + 1:02d}", number, color, (rect.x + 20, rect.y + 18))
            draw.text(
                surface,
                self.levels[i].name if open_ else "Locked",
                t.font(t.size.label, "semibold"),
                p.text if open_ else p.text_muted,
                (rect.x + 20, rect.y + 54),
            )
            if done:
                moves, pushes = self.best[str(i)]
                info = f"Best {moves} moves · {pushes} pushes"
            elif open_:
                info = "Not solved yet"
            else:
                info = "Solve the previous level"
            draw.text(
                surface, info, t.font(t.size.caption), p.text_muted, (rect.x + 20, rect.y + 78)
            )
            if done:
                gfx.circle(surface, p.success, (rect.right - 26, rect.y + 28), 11)
                gfx.lines(
                    surface,
                    (255, 255, 255),
                    False,
                    [
                        (rect.right - 31, rect.y + 28),
                        (rect.right - 27, rect.y + 32),
                        (rect.right - 20, rect.y + 24),
                    ],
                    2.5,
                )
            elif not open_:
                draw.lock_icon(surface, (rect.right - 26, rect.y + 28), p.text_muted, 18)
        draw.text(
            surface,
            "Click a level, or use the arrows and Space",
            t.font(t.size.caption),
            p.text_muted,
            (48, 690),
        )

    def _tile(self) -> tuple[int, int, int]:
        level = self.game.level
        size = min(64, BOARD_AREA.width // level.width, BOARD_AREA.height // level.height)
        x = BOARD_AREA.centerx - size * level.width // 2
        y = BOARD_AREA.centery - size * level.height // 2
        return size, x, y

    def _cell(self, pos: Pos | tuple[float, float]) -> pygame.FRect:
        size, x, y = self._tile()
        return pygame.FRect(x + pos[1] * size, y + pos[0] * size, size, size)

    def _draw_play(self, surface: Canvas, t: Theme) -> None:
        p = t.palette
        g = self.game
        level = g.level
        size, _, _ = self._tile()
        for r, c in sorted(level.floor()):
            gfx.rect(surface, FLOOR if (r + c) % 2 else FLOOR_ALT, self._cell((r, c)))
        for r, c in level.walls:
            if any((r + dr, c + dc) in level.floor() for dr in (-1, 0, 1) for dc in (-1, 0, 1)):
                draw_wall(surface, self._cell((r, c)))
        pulse = 0.5 + 0.5 * math.sin(self.time * 4)
        for goal in level.goals:
            cell = self._cell(goal)
            gfx.circle(
                surface,
                lerp_color(FLOOR, GOAL, 0.6 + 0.3 * pulse),
                cell.center,
                size * 0.2,
                max(2, size / 16),
            )
            gfx.circle(surface, GOAL, cell.center, size * 0.07)

        k = 1.0
        moving_box = None
        if self.slide is not None:
            _, _, box_to, k = self.slide
            moving_box = box_to
        ease = 1 - (1 - k) ** 2
        for box in g.boxes:
            pos: tuple[float, float] = box
            if box == moving_box and self.slide is not None and self.slide[1] is not None:
                a = self.slide[1]
                pos = (a[0] + (box[0] - a[0]) * ease, a[1] + (box[1] - a[1]) * ease)
            cell = self._cell(pos).inflate(-size * 0.12, -size * 0.12)
            draw_crate(
                surface,
                pygame.Rect(round(cell.x), round(cell.y), round(cell.w), round(cell.h)),
                box in level.goals,
            )
        player: tuple[float, float] = g.player
        if self.slide is not None:
            a = self.slide[0]
            player = (a[0] + (g.player[0] - a[0]) * ease, a[1] + (g.player[1] - a[1]) * ease)
        draw_keeper(surface, self._cell(player), g.facing, self.time)

        self._draw_side(surface, t)
        if self.menu is not None:
            draw.overlay(surface, p.overlay)
            panel = pygame.Rect(0, 0, 400, 150 + self.menu.rect.height)
            panel.midbottom = (self.menu.rect.centerx, self.menu.rect.bottom + 28)
            draw_panel(surface, panel, t)
            draw.text(
                surface,
                "Level complete!",
                t.font(t.size.heading, "bold"),
                p.text,
                (panel.centerx, panel.y + 28),
                "midtop",
            )
            sub = f"{g.moves} moves · {g.pushes} pushes" + (" · new best!" if self.new_best else "")
            draw.text(
                surface,
                sub,
                t.font(t.size.label, "semibold"),
                p.success if self.new_best else p.text_muted,
                (panel.centerx, panel.y + 74),
                "midtop",
            )
            self.menu.draw(surface)

    def _draw_side(self, surface: Canvas, t: Theme) -> None:
        p = t.palette
        g = self.game
        x = SIDE_X
        draw.text(
            surface, f"Level {self.index + 1}", t.font(t.size.label, "semibold"), ACCENT, (x, 96)
        )
        draw.text(surface, g.level.name, t.font(t.size.heading, "bold"), p.text, (x, 120))
        stats = [
            ("Moves", str(g.moves)),
            ("Pushes", str(g.pushes)),
            ("Crates home", f"{g.boxes_home} / {len(g.level.goals)}"),
        ]
        best = self.best.get(str(self.index))
        stats.append(("Best", f"{best[0]} moves" if best else "—"))
        for i, (label, value) in enumerate(stats):
            y = 196 + i * 62
            draw.text(
                surface, label.upper(), t.font(t.size.caption, "semibold"), p.text_muted, (x, y)
            )
            draw.text(surface, value, t.font(t.size.title, "bold"), p.text, (x, y + 20))
        for button in self.buttons:
            button.draw(surface)
        moves = self.input.labels("up", "down", "left", "right", sep="")
        hint = f"{moves} move · U undo · R restart · Esc levels"
        draw.text(surface, hint, t.font(t.size.caption), p.text_muted, (x, 592))
        draw.text(
            surface,
            "Crates can only be pushed, never pulled.",
            t.font(t.size.caption),
            p.text_muted,
            (x, 614),
        )


# ---------------------------------------------------------------------- art
def draw_wall(surface: Canvas, cell: pygame.FRect) -> None:
    gfx.rect(surface, WALL, cell)
    gfx.rect(surface, WALL_TOP, (cell.x, cell.y, cell.w, cell.h * 0.18))
    mortar = lerp_color(WALL, (0, 0, 0), 0.25)
    gfx.line(
        surface, mortar, (cell.x, cell.y + cell.h * 0.58), (cell.right, cell.y + cell.h * 0.58), 1
    )
    gfx.line(
        surface,
        mortar,
        (cell.centerx, cell.y + cell.h * 0.18),
        (cell.centerx, cell.y + cell.h * 0.58),
        1,
    )


def draw_crate(surface: Canvas, rect: pygame.Rect, home: bool) -> None:
    base = lerp_color(CRATE, CRATE_HOME, 0.55) if home else CRATE
    dark = lerp_color(CRATE_DARK, (22, 101, 52), 0.6) if home else CRATE_DARK
    draw.rounded_rect(surface, rect, dark, max(2, rect.width // 10))
    inner = rect.inflate(-rect.width * 0.18, -rect.height * 0.18)
    draw.rounded_rect(surface, inner, base, max(2, rect.width // 14))
    w = max(2, rect.width / 12)
    gfx.line(surface, dark, inner.topleft, inner.bottomright, w)
    gfx.line(surface, dark, inner.topright, inner.bottomleft, w)


def draw_keeper(surface: Canvas, cell: pygame.FRect, facing: str, time: float) -> None:
    cx, cy = cell.center
    r = cell.w * 0.34
    bob = math.sin(time * 6) * cell.h * 0.015
    shadow = lerp_color(FLOOR, (0, 0, 0), 0.45)
    gfx.ellipse(surface, shadow, (cx - r * 0.9, cy + r * 0.7, r * 1.8, r * 0.5))
    gfx.circle(surface, KEEPER, (cx, cy + bob), r)
    dr, dc = DIRECTIONS[facing]
    # Eyes look the way the keeper faces (squeezed together when facing sideways).
    spread = r * (0.36 if dc == 0 else 0.22)
    for side in (-1, 1):
        ex = cx + dc * r * 0.35 + side * spread
        ey = cy + bob - r * 0.15 + dr * r * 0.3
        gfx.circle(surface, (255, 255, 255), (ex, ey), r * 0.22)
        gfx.circle(surface, (15, 23, 42), (ex + dc * r * 0.08, ey + dr * r * 0.08), r * 0.11)
