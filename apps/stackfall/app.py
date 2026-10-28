"""Stackfall UI: board, hold and next panels, ghost piece, line-clear flashes."""

from __future__ import annotations

import random
from typing import Literal

import pygame

from apps.stackfall.logic import (
    HEIGHT,
    HIDDEN,
    WIDTH,
    Kind,
    Stackfall,
    StepResult,
    rotated_cells,
)
from core import draw, gfx
from core.base_app import BaseApp
from core.canvas import Canvas
from core.input import ACTIONDOWN, ACTIONUP, Action, is_action
from core.registry import register_app
from core.theme import Color, Theme, lerp_color
from core.widgets import ButtonMenu, draw_panel

ACCENT: Color = (192, 38, 211)
COLORS: dict[Kind, Color] = {
    "I": (34, 211, 238),
    "O": (250, 204, 21),
    "T": (192, 132, 252),
    "S": (74, 222, 128),
    "Z": (251, 113, 133),
    "J": (96, 165, 250),
    "L": (251, 146, 60),
}
CELL = 30
BOARD = pygame.Rect((1280 - WIDTH * CELL) // 2, 64, WIDTH * CELL, HEIGHT * CELL)
LEFT_X = BOARD.x - 40 - 200
RIGHT_X = BOARD.right + 40
DAS = 0.16  # delay before sideways auto-repeat
ARR = 0.045  # auto-repeat interval
FLASH_SECONDS = 0.25

# Movement, soft drop, rotate (up) and hard drop (action) use the shared controls.
# These extra keys are Stackfall-specific:
CW_KEYS = (pygame.K_x,)
CCW_KEYS = (pygame.K_z, pygame.K_LCTRL, pygame.K_RCTRL)
HOLD_KEYS = (pygame.K_c, pygame.K_LSHIFT, pygame.K_RSHIFT)

State = Literal["ready", "playing", "over"]


def draw_block(surface: Canvas, rect: pygame.Rect, color: Color) -> None:
    """One rounded block with a soft highlight."""
    inner = rect.inflate(-2, -2)
    gfx.rect(surface, color, inner, border_radius=5)
    hi = pygame.Rect(inner.x + 3, inner.y + 3, inner.width - 6, max(2, inner.height // 4))
    gfx.rect(surface, lerp_color(color, (255, 255, 255), 0.35), hi, border_radius=3)


def draw_mini(
    surface: Canvas, kind: Kind, center: tuple[int, int], size: int, color: Color
) -> None:
    """A piece centred in a preview box."""
    cells = rotated_cells(kind, 0)
    xs = [x for x, _ in cells]
    ys = [y for _, y in cells]
    w = (max(xs) - min(xs) + 1) * size
    h = (max(ys) - min(ys) + 1) * size
    ox = center[0] - w // 2 - min(xs) * size
    oy = center[1] - h // 2 - min(ys) * size
    for x, y in cells:
        draw_block(surface, pygame.Rect(ox + x * size, oy + y * size, size, size), color)


@register_app
class StackfallApp(BaseApp):
    """Rotate and drop falling pieces to complete and clear lines."""

    @classmethod
    def draw_icon(cls, surface: Canvas, rect: pygame.Rect, theme: Theme) -> None:
        draw.rounded_rect(surface, rect, (30, 27, 50), theme.radius.md)
        u = rect.width // 5
        cells: tuple[tuple[tuple[int, int], Kind], ...] = (
            ((1, 3), "J"),
            ((2, 3), "J"),
            ((3, 3), "S"),
            ((3, 2), "S"),
            ((2, 2), "T"),
            ((1, 2), "T"),
            ((2, 1), "T"),
            ((2, 0), "I"),
        )
        for (x, y), kind in cells:
            r = pygame.Rect(rect.x + u // 2 + x * u, rect.y + u // 2 + y * u, u, u)
            gfx.rect(surface, COLORS[kind], r.inflate(-2, -2), border_radius=2)

    # ------------------------------------------------------------------ lifecycle
    def on_enter(self) -> None:
        self.rng = random.Random()
        self.game = Stackfall(self.rng)
        self.state: State = "ready"
        self.held: set[int] = set()
        self.side_dir = 0
        self.side_timer = 0.0
        self.flashes: list[tuple[int, float]] = []  # (visible row, time left)
        self.menu: ButtonMenu | None = None
        self.new_best = False

    def _start(self) -> None:
        self.game = Stackfall(self.rng)
        self.state = "playing"
        self.menu = None
        self.flashes.clear()
        self.held.clear()
        self.side_dir = 0

    def restart(self) -> None:
        self._start()

    def on_pause(self) -> None:
        self.held.clear()
        self.side_dir = 0
        self.game.soft_dropping = False

    def on_exit(self) -> None:
        if self.state == "playing" and self.game.score > 0:
            self.submit_score(self.game.score)

    # ------------------------------------------------------------------ input
    def handle_event(self, event: pygame.event.Event) -> None:
        if self.state == "over" and self.menu is not None:
            self.menu.handle_event(event)
            return
        if event.type == ACTIONUP:
            if event.action == "down":
                self.game.soft_dropping = self.input.held("down")
            elif event.action in ("left", "right"):
                self._update_side_dir()
            return
        if event.type == pygame.KEYUP:
            self.held.discard(event.key)
            return
        if self.state == "ready":
            if is_action(event, "action", repeat=False):
                self._start()
            return
        if self.state != "playing":
            return
        # OS key-repeat is ignored everywhere: we do our own auto-repeat (DAS/ARR).
        if event.type == ACTIONDOWN and not event.repeat:
            self._on_action(event.action)
        elif event.type == pygame.KEYDOWN and event.key not in self.held:
            self.held.add(event.key)
            if event.key == pygame.K_p:
                self.pause()  # shortcut for the pause menu
            elif event.key in CW_KEYS:
                self.game.rotate(1)
            elif event.key in CCW_KEYS:
                self.game.rotate(-1)
            elif event.key in HOLD_KEYS:
                self.game.hold()

    def _on_action(self, action: Action) -> None:
        g = self.game
        if action in ("left", "right"):
            self._update_side_dir(prefer=-1 if action == "left" else 1)
            g.move(self.side_dir)
            self.side_timer = -DAS
        elif action == "down":
            g.soft_dropping = True
        elif action == "up":
            g.rotate(1)
        elif action == "action":
            self._after_step(g.hard_drop())

    def _update_side_dir(self, prefer: int = 0) -> None:
        left = self.input.held("left")
        right = self.input.held("right")
        if prefer:
            self.side_dir = prefer  # the most recently pressed direction wins
        elif left != right:
            self.side_dir = -1 if left else 1
            self.side_timer = -DAS
        else:
            self.side_dir = 0

    def _after_step(self, result: StepResult) -> None:
        if len(result.cleared) >= 4:
            self.unlock("clear_4")
        for row in result.cleared:
            if row >= 0:
                self.flashes.append((row, FLASH_SECONDS))
        if result.game_over:
            self.state = "over"
            self.new_best = self.game.score > 0 and self.submit_score(self.game.score)
            self.menu = ButtonMenu(
                self.theme,
                (BOARD.centerx, BOARD.centery + 70),
                [("Play again", self._start), ("Back to menu", self.exit_to_launcher)],
                width=240,
                accent=ACCENT,
            )

    def _check_achievements(self) -> None:
        self.unlock_milestones(self.game.lines, {"lines_40": 40})
        self.unlock_milestones(self.game.level, {"level_5": 5})

    def update(self, dt: float) -> None:
        self._check_achievements()
        self.flashes = [(r, t - dt) for r, t in self.flashes if t - dt > 0]
        if self.menu is not None:
            self.menu.update(dt)
        if self.state != "playing":
            return
        if self.side_dir:
            self.side_timer += dt
            while self.side_timer >= ARR:
                self.side_timer -= ARR
                self.game.move(self.side_dir)
        self._after_step(self.game.update(dt))

    # ------------------------------------------------------------------ drawing
    def _cell_rect(self, x: int, y: int) -> pygame.Rect:
        """Screen rect of board cell (x, y) in *grid* coordinates (including hidden rows)."""
        return pygame.Rect(BOARD.x + x * CELL, BOARD.y + (y - HIDDEN) * CELL, CELL, CELL)

    def draw(self, surface: Canvas) -> None:
        t = self.theme
        p = t.palette
        g = self.game
        surface.fill(p.bg)

        frame = BOARD.inflate(16, 16)
        draw.shadow(surface, frame, t.radius.lg, p.shadow, (0, 8), 16)
        well = (16, 15, 28) if t.mode == "dark" else (30, 32, 48)
        draw.rounded_rect(surface, frame, well, t.radius.lg)
        draw.rounded_rect(surface, frame, p.border, t.radius.lg, 2)
        grid_line = lerp_color(well, (255, 255, 255), 0.05)
        for x in range(1, WIDTH):
            gfx.line(
                surface,
                grid_line,
                (BOARD.x + x * CELL, BOARD.y),
                (BOARD.x + x * CELL, BOARD.bottom),
            )
        for y in range(1, HEIGHT):
            gfx.line(
                surface, grid_line, (BOARD.x, BOARD.y + y * CELL), (BOARD.right, BOARD.y + y * CELL)
            )

        clip = surface.get_clip()
        surface.set_clip(BOARD)
        dim = 0.55 if self.state == "over" else 0.0
        for y, row in enumerate(g.grid):
            for x, kind in enumerate(row):
                if kind is not None:
                    draw_block(surface, self._cell_rect(x, y), lerp_color(COLORS[kind], well, dim))
        if self.state == "playing":
            ghost = g.ghost()
            for x, y in ghost.cells():
                r = self._cell_rect(x, y).inflate(-4, -4)
                gfx.rect(surface, lerp_color(COLORS[ghost.kind], well, 0.45), r, 2, border_radius=5)
            for x, y in g.piece.cells():
                draw_block(surface, self._cell_rect(x, y), COLORS[g.piece.kind])
        for flash_row, left in self.flashes:
            k = left / FLASH_SECONDS
            layer = Canvas.new((BOARD.width, CELL), alpha=True)
            layer.fill((255, 255, 255, round(200 * k)))
            surface.blit(layer, (BOARD.x, BOARD.y + flash_row * CELL))
        surface.set_clip(clip)

        self._draw_side(surface, t)
        if self.state == "ready":
            self._card(surface, t, "Stackfall", f"Press {self.input.label('action')} to start")
        elif self.state == "over" and self.menu is not None:
            sub = "New high score!" if self.new_best else f"Score {g.score:,}"
            self._card(
                surface, t, "Game over", sub, extra=self.menu.rect.height + 20, good=self.new_best
            )
            self.menu.draw(surface)

    def _box(self, surface: Canvas, t: Theme, rect: pygame.Rect, title: str) -> None:
        draw_panel(surface, rect, t)
        draw.text(
            surface,
            title.upper(),
            t.font(t.size.caption, "semibold"),
            t.palette.text_muted,
            (rect.x + 16, rect.y + 14),
        )

    def _draw_side(self, surface: Canvas, t: Theme) -> None:
        p = t.palette
        g = self.game
        hold = pygame.Rect(LEFT_X, BOARD.y, 200, 130)
        self._box(surface, t, hold, "Hold")
        if g.hold_kind is not None:
            color = (
                COLORS[g.hold_kind]
                if g.can_hold
                else lerp_color(COLORS[g.hold_kind], p.surface, 0.6)
            )
            draw_mini(surface, g.hold_kind, (hold.centerx, hold.centery + 12), 24, color)

        stats = pygame.Rect(LEFT_X, hold.bottom + 20, 200, 300)
        self._box(surface, t, stats, "Stats")
        best = self.best_score()
        best_value = max(g.score, int(best.score) if best else 0)
        rows = (
            ("Score", f"{g.score:,}"),
            ("Best", f"{best_value:,}"),
            ("Level", str(g.level)),
            ("Lines", str(g.lines)),
        )
        for i, (label, value) in enumerate(rows):
            y = stats.y + 44 + i * 62
            draw.text(surface, label, t.font(t.size.caption), p.text_muted, (stats.x + 16, y))
            draw.text(
                surface,
                value,
                t.font(t.size.title, "bold"),
                ACCENT if i == 0 else p.text,
                (stats.x + 16, y + 18),
            )

        nxt = pygame.Rect(RIGHT_X, BOARD.y, 200, 420)
        self._box(surface, t, nxt, "Next")
        for i, kind in enumerate(g.upcoming()):
            size = 24 if i == 0 else 18
            cy = nxt.y + (90 if i == 0 else 150 + (i - 1) * 64)
            draw_mini(surface, kind, (nxt.centerx, cy), size, COLORS[kind])

        inp = self.input
        controls = (
            f"{inp.labels('left', 'right')} move   {inp.label('down')} soft drop",
            f"{inp.label('up')}/X rotate   Z rotate back",
            f"{inp.label('action')} drop   C hold",
            f"P or {inp.label('pause')} pause",
        )
        for i, line in enumerate(controls):
            draw.text(
                surface,
                line,
                t.font(t.size.caption),
                p.text_muted,
                (RIGHT_X, nxt.bottom + 24 + i * 22),
            )

    def _card(
        self,
        surface: Canvas,
        t: Theme,
        title: str,
        sub: str,
        extra: int = 0,
        good: bool = False,
    ) -> None:
        p = t.palette
        panel = pygame.Rect(0, 0, 300, 120 + extra)
        panel.midtop = (BOARD.centerx, BOARD.centery - 110)
        draw_panel(surface, panel, t)
        draw.text(
            surface,
            title,
            t.font(t.size.heading, "bold"),
            p.text,
            (panel.centerx, panel.y + 26),
            "midtop",
        )
        draw.text(
            surface,
            sub,
            t.font(t.size.label, "semibold" if good else "regular"),
            p.success if good else p.text_muted,
            (panel.centerx, panel.y + 72),
            "midtop",
        )
