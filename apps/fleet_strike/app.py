"""Fleet Strike UI: drag-and-drop placement, two grids of open water, a computer admiral."""

from __future__ import annotations

import random
from typing import Literal

import pygame

from apps.fleet_strike.logic import (
    LEVELS,
    SIZE,
    Admiral,
    Board,
    Cell,
    Level,
    Ship,
    ShotResult,
    ship_cells,
)
from core import draw, gfx
from core.base_app import BaseApp
from core.canvas import Canvas
from core.input import DIRECTION_STEPS, action_of, is_action
from core.registry import register_app
from core.theme import Color, Theme, lerp_color, with_alpha
from core.widgets import Button, ButtonMenu, SegmentedControl, draw_panel

ACCENT: Color = (56, 189, 248)
WATER: Color = (12, 42, 74)
WATER_LINE: Color = (22, 66, 108)
HULL: Color = (148, 163, 184)
HIT: Color = (249, 115, 22)
MISS: Color = (186, 230, 253)
CELL = 40
OWN = pygame.Rect(100, 190, CELL * SIZE, CELL * SIZE)
ENEMY = pygame.Rect(780, 190, CELL * SIZE, CELL * SIZE)
CPU_DELAY = 0.6
Phase = Literal["placing", "battle", "over"]


def cell_rect(grid: pygame.Rect, cell: Cell) -> pygame.Rect:
    r, c = cell
    return pygame.Rect(grid.x + c * CELL, grid.y + r * CELL, CELL, CELL)


def cell_at(grid: pygame.Rect, pos: tuple[int, int]) -> Cell | None:
    if not grid.collidepoint(pos):
        return None
    return ((pos[1] - grid.y) // CELL, (pos[0] - grid.x) // CELL)


@register_app
class FleetStrikeApp(BaseApp):
    """Place your fleet, then trade shots with the computer until one fleet is gone."""

    @classmethod
    def draw_icon(cls, surface: Canvas, rect: pygame.Rect, theme: Theme) -> None:
        draw.rounded_rect(surface, rect, WATER, theme.radius.md)
        n = 5
        step = rect.width / n
        for i in range(1, n):
            x = rect.x + i * step
            y = rect.y + i * step
            gfx.line(surface, WATER_LINE, (x, rect.y + 4), (x, rect.bottom - 4), 1)
            gfx.line(surface, WATER_LINE, (rect.x + 4, y), (rect.right - 4, y), 1)
        hull = pygame.Rect(
            round(rect.x + step * 0.6),
            round(rect.y + step * 1.25),
            round(step * 3.8),
            round(step * 0.5),
        )
        draw.rounded_rect(surface, hull, HULL, hull.height // 2)
        gfx.circle(surface, HIT, (rect.x + step * 3.5, rect.y + step * 3.5), step * 0.36)
        gfx.circle(surface, MISS, (rect.x + step * 1.5, rect.y + step * 3.5), step * 0.14)

    # ------------------------------------------------------------------ lifecycle
    def on_enter(self) -> None:
        level = self.data.get("level", "normal")
        self.level: Level = level if level in LEVELS else "normal"
        t = self.theme
        self.level_picker = SegmentedControl(
            t,
            (ENEMY.right - 330, 40, 330, 40),
            ["Easy", "Normal", "Hard"],
            LEVELS.index(self.level),
            self._set_level,
            accent=ACCENT,
        )
        self.shuffle_button = Button(t, (OWN.x, 620, 160, 44), "Shuffle", self._shuffle)
        self.start_button = Button(
            t, (ENEMY.x, 620, 220, 44), "Start battle", self._start, "primary", accent=ACCENT
        )
        self.time = 0.0
        self._new_game()

    def on_exit(self) -> None:
        self.data["level"] = self.level
        self.data.save()

    def restart(self) -> None:
        self._new_game()

    def _set_level(self, index: int) -> None:
        self.level = LEVELS[index]

    def _new_game(self) -> None:
        self.rng = random.Random()
        self.phase: Phase = "placing"
        self.own = Board.random(self.rng)
        self.enemy = Board.random(self.rng)
        self.admiral = Admiral(self.level, self.rng)
        self.held: Ship | None = None
        self.grab = 0  # index of the held ship's cell under the mouse
        self.ghost: list[Cell] = []
        self.mouse = (0, 0)
        self.cursor: Cell = (0, 0)
        self.cpu_timer = 0.0
        self.shots = 0
        self.hits = 0
        self.status = "Drag ships to move them · R or right-click rotates."
        self.ripples: list[tuple[pygame.Rect, Cell, float]] = []
        self.menu: ButtonMenu | None = None
        self.new_best = False

    def _shuffle(self) -> None:
        if self.phase == "placing":
            self.own = Board.random(self.rng)
            self.held = None

    def _start(self) -> None:
        if self.phase != "placing" or self.held is not None:
            return
        self.admiral = Admiral(self.level, self.rng)
        self.phase = "battle"
        self.status = "Your turn: pick a target in enemy waters."

    # ------------------------------------------------------------------ placement
    def _pick_up(self, cell: Cell) -> None:
        ship = self.own.ship_at(cell)
        if ship is not None:
            self.held = ship
            self.grab = ship.cells.index(cell)
            self._update_ghost(ship.horizontal)

    def _update_ghost(self, horizontal: bool) -> None:
        if self.held is None:
            return
        length = len(self.held.cells)
        r = (self.mouse[1] - OWN.y) // CELL
        c = (self.mouse[0] - OWN.x) // CELL
        start = (r, c - self.grab) if horizontal else (r - self.grab, c)
        self.ghost = ship_cells(start[0], start[1], length, horizontal)

    def _ghost_horizontal(self) -> bool:
        return len(self.ghost) < 2 or self.ghost[0][0] == self.ghost[1][0]

    def _rotate(self) -> None:
        if self.held is not None:
            self._update_ghost(not self._ghost_horizontal())

    def _drop(self) -> None:
        if self.held is not None and self.own.can_place(self.ghost, ignore=self.held):
            self.held.cells = list(self.ghost)
            self.held = None

    # ------------------------------------------------------------------ battle
    def _fire(self, cell: Cell) -> None:
        if self.phase != "battle" or self.cpu_timer > 0:
            return
        result = self.enemy.fire(cell)
        if result is None:
            return
        self.shots += 1
        self.hits += result != "miss"
        self.cursor = cell
        self.ripples.append((ENEMY, cell, 0.0))
        self.status = self._describe("You", result, self.enemy, cell)
        if self.enemy.defeated:
            self._finish(won=True)
            return
        self.cpu_timer = CPU_DELAY

    def _cpu_turn(self) -> None:
        cell = self.admiral.choose(self.own)
        result = self.own.fire(cell)
        assert result is not None
        self.ripples.append((OWN, cell, 0.0))
        self.status = self._describe("Enemy", result, self.own, cell)
        if self.own.defeated:
            self._finish(won=False)
        else:
            self.status += " · Your turn."

    def _describe(self, who: str, result: ShotResult, board: Board, cell: Cell) -> str:
        where = f"{'ABCDEFGHIJ'[cell[1]]}{cell[0] + 1}"
        if result == "sunk":
            ship = board.ship_at(cell)
            whose = "their" if who == "You" else "your"
            return f"{who} sank {whose} {ship.name if ship else 'ship'}! ({where})"
        return f"{who}: {where}, {'hit!' if result == 'hit' else 'miss.'}"

    def _finish(self, won: bool) -> None:
        self.phase = "over"
        if won:
            self.new_best = self.submit_score(self.shots, self.level)
            self.unlock("first_win")
            if self.level == "hard":
                self.unlock("win_hard")
            if self.shots <= 45:
                self.unlock("sharpshooter")
            if not self.own.sunk_ships():
                self.unlock("iron_hull")
        self.menu = ButtonMenu(
            self.theme, (640, 470), [("Play again", self._new_game)], accent=ACCENT
        )

    # ------------------------------------------------------------------ events
    def handle_event(self, event: pygame.event.Event) -> None:
        if self.menu is not None:
            self.menu.handle_event(event)
            return
        if event.type == pygame.MOUSEMOTION:
            self.mouse = event.pos
            if self.held is not None:
                self._update_ghost(self._ghost_horizontal())
            hover = cell_at(ENEMY, event.pos)
            if hover is not None and self.phase == "battle":
                self.cursor = hover
        if self.phase == "placing":
            self._placing_event(event)
        elif self.phase == "battle":
            self._battle_event(event)

    def _placing_event(self, event: pygame.event.Event) -> None:
        if self.held is None and (
            self.level_picker.handle_event(event)
            or self.shuffle_button.handle_event(event)
            or self.start_button.handle_event(event)
        ):
            return
        if event.type == pygame.MOUSEBUTTONDOWN:
            self.mouse = event.pos
            if event.button == 3:
                self._rotate()
            elif event.button == 1:
                if self.held is not None:
                    self._drop()
                elif (cell := cell_at(OWN, event.pos)) is not None:
                    self._pick_up(cell)
        elif event.type == pygame.KEYDOWN and event.key == pygame.K_r:
            self._rotate()
        elif is_action(event, "action", repeat=False) and self.held is None:
            self._start()

    def _battle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            cell = cell_at(ENEMY, event.pos)
            if cell is not None:
                self._fire(cell)
            return
        action = action_of(event)
        if action in DIRECTION_STEPS:
            dx, dy = DIRECTION_STEPS[action]
            r, c = self.cursor
            self.cursor = ((r + dy) % SIZE, (c + dx) % SIZE)
        elif action == "action":
            self._fire(self.cursor)

    def update(self, dt: float) -> None:
        self.time += dt
        self.ripples = [(g, c, age + dt) for g, c, age in self.ripples if age < 0.6]
        if self.phase == "placing":
            self.level_picker.update(dt)
            self.shuffle_button.update(dt)
            self.start_button.enabled = self.held is None
            self.start_button.update(dt)
        if self.menu is not None:
            self.menu.update(dt)
            return
        if self.cpu_timer > 0:
            self.cpu_timer -= dt
            if self.cpu_timer <= 0:
                self.cpu_timer = 0
                self._cpu_turn()

    # ------------------------------------------------------------------ drawing
    def draw(self, surface: Canvas) -> None:
        t = self.theme
        p = t.palette
        surface.fill(p.bg)
        draw.text(surface, "Fleet Strike", t.font(t.size.heading, "bold"), p.text, (OWN.x, 38))
        draw.text(surface, self.status, t.font(t.size.label, "semibold"), p.text_muted, (OWN.x, 90))
        draw.text(
            surface, "YOUR FLEET", t.font(t.size.caption, "semibold"), p.text_muted, (OWN.x, 140)
        )
        draw.text(
            surface,
            "ENEMY WATERS",
            t.font(t.size.caption, "semibold"),
            p.text_muted,
            (ENEMY.x, 140),
        )
        self._draw_grid(surface, t, OWN)
        self._draw_grid(surface, t, ENEMY)
        for ship in self.own.ships:
            if ship is not self.held:
                self._draw_ship(surface, OWN, ship.cells, HULL)
        for ship in self.enemy.ships:
            if ship.sunk:
                self._draw_ship(surface, ENEMY, ship.cells, lerp_color(HULL, HIT, 0.35))
            elif self.phase == "over":  # reveal what was left afloat
                self._draw_ship(surface, ENEMY, ship.cells, with_alpha(HULL, 110))
        self._draw_shots(surface, OWN, self.own)
        self._draw_shots(surface, ENEMY, self.enemy)
        for grid, cell, age in self.ripples:
            k = age / 0.6
            rect = cell_rect(grid, cell)
            gfx.circle(surface, lerp_color(MISS, WATER, k), rect.center, 8 + 18 * k, 2)
        if self.phase == "placing":
            self._draw_placing(surface, t)
        else:
            self._draw_fleet_status(surface, t)
            if self.phase == "battle" and self.cpu_timer <= 0:
                pulse = 0.6 + 0.4 * abs(((self.time * 2) % 2) - 1)
                rect = cell_rect(ENEMY, self.cursor).inflate(-2, -2)
                draw.rounded_rect(surface, rect, lerp_color(WATER, ACCENT, pulse), 6, 3)
        if self.menu is not None:
            self._draw_over(surface, t)

    def _draw_grid(self, surface: Canvas, t: Theme, grid: pygame.Rect) -> None:
        p = t.palette
        frame = grid.inflate(16, 16)
        draw.shadow(surface, frame, t.radius.md, p.shadow, (0, 6), 12)
        draw.rounded_rect(surface, frame, WATER, t.radius.md)
        for i in range(1, SIZE):
            gfx.line(
                surface, WATER_LINE, (grid.x + i * CELL, grid.y), (grid.x + i * CELL, grid.bottom)
            )
            gfx.line(
                surface, WATER_LINE, (grid.x, grid.y + i * CELL), (grid.right, grid.y + i * CELL)
            )
        small = t.font(t.size.caption, "semibold")
        for i in range(SIZE):
            draw.text(
                surface,
                "ABCDEFGHIJ"[i],
                small,
                p.text_muted,
                (grid.x + i * CELL + CELL / 2, grid.y - 12),
                "midbottom",
            )
            draw.text(
                surface,
                str(i + 1),
                small,
                p.text_muted,
                (grid.x - 14, grid.y + i * CELL + CELL / 2),
                "midright",
            )

    def _draw_ship(
        self,
        surface: Canvas,
        grid: pygame.Rect,
        cells: list[Cell],
        color: Color | tuple[int, int, int, int],
    ) -> None:
        rects = [cell_rect(grid, c) for c in cells]
        hull = rects[0].unionall(rects[1:]).inflate(-8, -8)
        draw.rounded_rect(surface, hull, color, min(hull.width, hull.height) // 2)
        if len(color) == 3:
            deck = lerp_color(color, (255, 255, 255), 0.25)
            for rect in rects[1:-1]:
                gfx.circle(surface, deck, rect.center, 4)

    def _draw_shots(self, surface: Canvas, grid: pygame.Rect, board: Board) -> None:
        for cell, result in board.shots.items():
            rect = cell_rect(grid, cell)
            if result == "miss":
                gfx.circle(surface, MISS, rect.center, 5)
            else:
                gfx.circle(surface, HIT, rect.center, 13)
                gfx.circle(surface, (254, 215, 170), rect.center, 6)

    def _draw_placing(self, surface: Canvas, t: Theme) -> None:
        p = t.palette
        if self.held is not None and self.ghost:
            ok = self.own.can_place(self.ghost, ignore=self.held)
            color = with_alpha(p.success if ok else p.danger, 170)
            visible = [c for c in self.ghost if 0 <= c[0] < SIZE and 0 <= c[1] < SIZE]
            if visible:
                self._draw_ship(surface, OWN, visible, color)
        self.level_picker.draw(surface)
        self.shuffle_button.draw(surface)
        self.start_button.draw(surface)
        hint = f"{self.input.label('action')} or the button starts the battle"
        draw.text(
            surface,
            hint,
            t.font(t.size.caption),
            p.text_muted,
            (ENEMY.x + 240, self.start_button.rect.centery),
            "midleft",
        )
        draw.text(
            surface,
            "The enemy fleet is hidden here.",
            t.font(t.size.title, "semibold"),
            lerp_color(WATER, MISS, 0.5),
            ENEMY.center,
            "center",
        )

    def _draw_fleet_status(self, surface: Canvas, t: Theme) -> None:
        p = t.palette
        font = t.font(t.size.caption, "semibold")
        for grid, board in ((OWN, self.own), (ENEMY, self.enemy)):
            x = grid.x
            for ship in board.ships:
                label = f"{ship.name} {len(ship.cells)}"
                color = p.danger if ship.sunk else p.text_muted
                rect = draw.text(surface, label, font, color, (x, 616))
                if ship.sunk:
                    gfx.line(
                        surface, p.danger, (rect.x, rect.centery), (rect.right, rect.centery), 2
                    )
                x = rect.right + 18
        accuracy = f"{self.hits / self.shots:.0%}" if self.shots else "—"
        draw.text(
            surface,
            f"Shots {self.shots} · Accuracy {accuracy}",
            t.font(t.size.label, "semibold"),
            p.text_muted,
            (ENEMY.right, 90),
            "topright",
        )

    def _draw_over(self, surface: Canvas, t: Theme) -> None:
        assert self.menu is not None
        p = t.palette
        won = self.enemy.defeated
        draw.overlay(surface, p.overlay)
        panel = pygame.Rect(0, 0, 420, 200 + self.menu.rect.height)
        panel.midbottom = (640, self.menu.rect.bottom + 32)
        draw_panel(surface, panel, t)
        draw.text(
            surface,
            "Victory!" if won else "Fleet lost",
            t.font(t.size.heading, "bold"),
            p.success if won else p.danger,
            (panel.centerx, panel.y + 26),
            "midtop",
        )
        accuracy = f"{self.hits / self.shots:.0%}" if self.shots else "—"
        detail = f"{self.shots} shots · {accuracy} accuracy · {self.level.title()}"
        draw.text(
            surface,
            detail,
            t.font(t.size.label),
            p.text_muted,
            (panel.centerx, panel.y + 74),
            "midtop",
        )
        if won:
            best = self.best_score(self.level)
            sub = "New best!" if self.new_best else (f"Best {best.score:.0f} shots" if best else "")
            draw.text(
                surface,
                sub,
                t.font(t.size.label, "semibold"),
                p.success if self.new_best else p.text_muted,
                (panel.centerx, panel.y + 102),
                "midtop",
            )
        else:
            left = sum(not s.sunk for s in self.enemy.ships)
            draw.text(
                surface,
                f"{left} enemy ship{'s' if left != 1 else ''} still afloat",
                t.font(t.size.label, "semibold"),
                p.text_muted,
                (panel.centerx, panel.y + 102),
                "midtop",
            )
        self.menu.draw(surface)
