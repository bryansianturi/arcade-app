"""Sliding Tiles UI: numbered tiles that glide, 3×3 and 4×4 boards, timer and best times."""

from __future__ import annotations

import random

import pygame

from apps.sliding_tiles.logic import GAP, SlidingPuzzle
from core import draw
from core.base_app import BaseApp, format_score
from core.canvas import Canvas
from core.input import DIRECTION_STEPS, action_of
from core.registry import register_app
from core.theme import Color, Theme, lerp_color
from core.widgets import Button, ButtonMenu, SegmentedControl, draw_panel

ACCENT: Color = (253, 186, 116)
TILE: Color = (251, 146, 60)
SIZES = (3, 4)
BOARD = pygame.Rect(140, 80, 560, 560)
SIDE_X = 780
SLIDE_SECONDS = 0.1


@register_app
class SlidingTilesApp(BaseApp):
    """Slide the tiles back into order, 1 to 15 (or 1 to 8)."""

    @classmethod
    def draw_icon(cls, surface: Canvas, rect: pygame.Rect, theme: Theme) -> None:
        draw.rounded_rect(surface, rect, (67, 20, 7), theme.radius.md)
        cell = rect.width / 2.4
        font = theme.font(int(cell * 0.55), "bold")
        for i, label in enumerate(("1", "2", "3")):
            r, c = divmod(i, 2)
            box = pygame.Rect(0, 0, round(cell * 0.9), round(cell * 0.9))
            box.center = (round(rect.x + cell * (c + 0.7)), round(rect.y + cell * (r + 0.7)))
            draw.rounded_rect(surface, box, TILE, max(3, box.width // 6))
            draw.text(surface, label, font, (67, 20, 7), box.center, "center")

    # ------------------------------------------------------------------ lifecycle
    def on_enter(self) -> None:
        size = self.data.get("size", 4)
        self.size = size if size in SIZES else 4
        t = self.theme
        self.size_picker = SegmentedControl(
            t, (SIDE_X, 196, 300, 40), ["3 × 3", "4 × 4"], SIZES.index(self.size), self._set_size
        )
        self.buttons = [
            Button(t, (SIDE_X, 430, 144, 44), "Undo", self._undo),
            Button(
                t, (SIDE_X + 156, 430, 144, 44), "Shuffle", self._shuffle, "primary", accent=ACCENT
            ),
        ]
        self.time = 0.0
        self._shuffle()

    def on_exit(self) -> None:
        self.data["size"] = self.size
        self.data.save()

    def restart(self) -> None:
        self._shuffle()

    @property
    def variant(self) -> str:
        return f"{self.size}x{self.size}"

    def _set_size(self, index: int) -> None:
        self.size = SIZES[index]
        self._shuffle()

    def _shuffle(self) -> None:
        self.puzzle = SlidingPuzzle.shuffled(self.size, random.Random())
        self.elapsed = 0.0
        self.started = False
        self.offsets: dict[int, tuple[float, float]] = {}  # tile → remaining (dx, dy) in cells
        self.menu: ButtonMenu | None = None
        self.new_best = False

    def _undo(self) -> None:
        if self.menu is None and self.puzzle.undo():
            self.offsets.clear()

    # ------------------------------------------------------------------ moves
    def _animate(self, moved: list[int], before: dict[int, int]) -> None:
        for tile in moved:
            old = before[tile]
            new = self.puzzle.tiles.index(tile)
            (r0, c0), (r1, c1) = divmod(old, self.size), divmod(new, self.size)
            self.offsets[tile] = (c0 - c1, r0 - r1)

    def _after_move(self, moved: list[int], before: dict[int, int]) -> None:
        if not moved:
            return
        self.started = True
        self._animate(moved, before)
        if self.puzzle.solved:
            self._on_solved()

    def _click(self, r: int, c: int) -> None:
        if self.menu is not None:
            return
        before = {t: i for i, t in enumerate(self.puzzle.tiles)}
        self._after_move(self.puzzle.slide(r, c), before)

    def _push(self, direction: tuple[int, int]) -> None:
        if self.menu is not None:
            return
        before = {t: i for i, t in enumerate(self.puzzle.tiles)}
        self._after_move(self.puzzle.push(direction), before)

    def _on_solved(self) -> None:
        seconds = max(1, round(self.elapsed))
        self.new_best = self.submit_score(seconds, self.variant)
        if self.size == 3:
            self.unlock("solve_8")
        else:
            self.unlock("solve_15")
        if self.size == 4 and seconds < 120:
            self.unlock("fast_15")
        self.menu = ButtonMenu(
            self.theme,
            (BOARD.centerx, BOARD.centery + 40),
            [("Play again", self._shuffle)],
            accent=ACCENT,
        )

    # ------------------------------------------------------------------ events
    def cell_rect(self, r: int, c: int) -> pygame.Rect:
        step = BOARD.width / self.size
        return pygame.Rect(
            round(BOARD.x + c * step), round(BOARD.y + r * step), round(step), round(step)
        )

    def handle_event(self, event: pygame.event.Event) -> None:
        if self.menu is not None:
            self.menu.handle_event(event)
            return
        for widget in (self.size_picker, *self.buttons):
            if widget.handle_event(event):
                return
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for r in range(self.size):
                for c in range(self.size):
                    if self.cell_rect(r, c).collidepoint(event.pos):
                        self._click(r, c)
                        return
        elif event.type == pygame.KEYDOWN and event.key == pygame.K_u:
            self._undo()
        else:
            action = action_of(event)
            if action in DIRECTION_STEPS:
                self._push(DIRECTION_STEPS[action])

    def update(self, dt: float) -> None:
        self.time += dt
        if self.started and not self.puzzle.solved:
            self.elapsed += dt
        step = dt / SLIDE_SECONDS
        for tile, (dx, dy) in list(self.offsets.items()):
            length = max(abs(dx), abs(dy))
            if length <= step:
                del self.offsets[tile]
            else:
                k = (length - step) / length
                self.offsets[tile] = (dx * k, dy * k)
        for widget in (self.size_picker, *self.buttons):
            widget.update(dt)
        self.buttons[0].enabled = bool(self.puzzle._undo) and self.menu is None
        if self.menu is not None:
            self.menu.update(dt)

    # ------------------------------------------------------------------ drawing
    def draw(self, surface: Canvas) -> None:
        t = self.theme
        p = t.palette
        surface.fill(p.bg)
        frame = BOARD.inflate(28, 28)
        draw.shadow(surface, frame, t.radius.lg, p.shadow, (0, 8), 16)
        draw.rounded_rect(surface, frame, p.surface_alt, t.radius.lg)
        font = t.font(56 if self.size == 3 else 44, "bold")
        solved = self.puzzle.solved
        for i, tile in enumerate(self.puzzle.tiles):
            if tile == GAP:
                continue
            r, c = divmod(i, self.size)
            dx, dy = self.offsets.get(tile, (0.0, 0.0))
            step = BOARD.width / self.size
            rect = self.cell_rect(r, c).move(round(dx * step), round(dy * step)).inflate(-10, -10)
            home = tile == i + 1
            color = (
                lerp_color(TILE, (34, 197, 94), 0.75)
                if solved
                else TILE
                if home
                else lerp_color(TILE, p.surface, 0.25)
            )
            draw.shadow(surface, rect, 12, p.shadow, (0, 4), 8)
            draw.rounded_rect(surface, rect, color, 12)
            draw.rounded_rect(
                surface, rect.inflate(-8, -8), lerp_color(color, (255, 255, 255), 0.12), 10
            )
            draw.text(surface, str(tile), font, (67, 20, 7), rect.center, "center")
        self._draw_side(surface, t)
        if self.menu is not None:
            draw.overlay(surface, p.overlay)
            box = pygame.Rect(0, 0, 380, 130 + self.menu.rect.height)
            box.midbottom = (self.menu.rect.centerx, self.menu.rect.bottom + 28)
            draw_panel(surface, box, t)
            draw.text(
                surface,
                "Solved!",
                t.font(t.size.heading, "bold"),
                p.text,
                (box.centerx, box.y + 26),
                "midtop",
            )
            sub = f"{format_score(self.elapsed, 'time')} · {self.puzzle.moves} moves"
            draw.text(
                surface,
                "New best time!" if self.new_best else sub,
                t.font(t.size.label, "semibold"),
                p.success if self.new_best else p.text_muted,
                (box.centerx, box.y + 72),
                "midtop",
            )
            self.menu.draw(surface)

    def _draw_side(self, surface: Canvas, t: Theme) -> None:
        p = t.palette
        x = SIDE_X
        draw.text(surface, "Sliding Tiles", t.font(t.size.heading, "bold"), p.text, (x, 80))
        last = self.size * self.size - 1
        draw.text(
            surface,
            f"Put the tiles in order, 1 to {last}.",
            t.font(t.size.label),
            p.text_muted,
            (x, 126),
        )
        self.size_picker.draw(surface)
        best = self.best_score(self.variant)
        stats = (
            ("Time", format_score(self.elapsed, "time")),
            ("Moves", str(self.puzzle.moves)),
            ("Best", format_score(best.score, "time") if best else "—"),
        )
        for i, (label, value) in enumerate(stats):
            sx = x + i * 104
            draw.text(
                surface, label.upper(), t.font(t.size.caption, "semibold"), p.text_muted, (sx, 272)
            )
            draw.text(surface, value, t.font(t.size.heading, "bold"), p.text, (sx, 294))
        for button in self.buttons:
            button.draw(surface)
        hint = "Click a tile in the gap's row or column · arrows slide · U undo"
        draw.text(surface, hint, t.font(t.size.caption), p.text_muted, (x, 500))
