"""Nonogram UI: puzzle list, clue rows and columns, painting with the mouse or keys."""

from __future__ import annotations

import random

import pygame

from apps.nonogram.logic import BLANK, CROSS, FILL, Board, Puzzle, generate, load_puzzles
from core import draw, gfx
from core.base_app import BaseApp
from core.canvas import Canvas
from core.input import DIRECTION_STEPS, action_of
from core.registry import register_app
from core.theme import Color, Theme, lerp_color
from core.widgets import Button

ACCENT: Color = (79, 70, 229)
LIST_X, LIST_W = 48, 250
AREA = pygame.Rect(LIST_X + LIST_W + 40, 64, 1280 - 48 - (LIST_X + LIST_W + 40), 720 - 64 - 44)
REVEAL_SECONDS = 1.2


def clock(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 60}:{s % 60:02d}"


@register_app
class NonogramApp(BaseApp):
    """Use the number clues to fill in the hidden picture."""

    @classmethod
    def draw_icon(cls, surface: Canvas, rect: pygame.Rect, theme: Theme) -> None:
        draw.rounded_rect(surface, rect, (238, 242, 255), theme.radius.md)
        pattern = ("..#..", ".###.", "#####", ".#.#.", ".#.#.")
        cell = rect.width / 7
        for r, row in enumerate(pattern):
            for c, ch in enumerate(row):
                box = pygame.FRect(
                    rect.x + cell * (c + 1), rect.y + cell * (r + 1), cell - 1, cell - 1
                )
                if ch == "#":
                    gfx.rect(surface, ACCENT, box, border_radius=2)
                else:
                    gfx.rect(surface, (199, 210, 254), box, 1, border_radius=2)

    # ------------------------------------------------------------------ lifecycle
    def on_enter(self) -> None:
        self.puzzles = load_puzzles()
        best = self.data.get("best", {})
        self.best: dict[str, float] = best if isinstance(best, dict) else {}
        t = self.theme
        self.list_buttons: list[Button] = []
        y = 112
        for i, puzzle in enumerate(self.puzzles):
            self.list_buttons.append(
                Button(t, (LIST_X, y, LIST_W, 40), puzzle.name, lambda i=i: self._open(i), "ghost")  # type: ignore[misc]
            )
            y += 46
        y += 18
        self.random_buttons = [
            Button(t, (LIST_X, y, LIST_W, 40), "Random 10 × 10", lambda: self._random(10)),
            Button(t, (LIST_X, y + 48, LIST_W, 40), "Random 15 × 15", lambda: self._random(15)),
        ]
        self.tool_buttons = [
            Button(t, (LIST_X, 620, LIST_W // 2 - 6, 40), "Undo", self._undo),
            Button(t, (LIST_X + LIST_W // 2 + 6, 620, LIST_W // 2 - 6, 40), "Clear", self._clear),
        ]
        self.time = 0.0
        self.keyboard = False
        self.cursor = (0, 0)
        self.stroke: int | None = None  # the mark being painted while the mouse is held
        self.index: int | None = 0
        saved_index = self.data.get("index", 0)
        saved_marks = self.data.get("marks")
        if isinstance(saved_index, int) and 0 <= saved_index < len(self.puzzles):
            self._open(saved_index)
            self.board = Board.from_json(self.puzzles[saved_index], saved_marks)
            elapsed = self.data.get("elapsed", 0.0)
            self.elapsed = float(elapsed) if isinstance(elapsed, int | float) else 0.0
        else:
            self._open(0)

    def on_exit(self) -> None:
        d = self.data
        d["best"] = self.best
        if self.index is not None and not self.board.solved:
            d["index"], d["marks"], d["elapsed"] = (
                self.index,
                self.board.to_json(),
                round(self.elapsed, 1),
            )
        else:
            d["index"], d["marks"], d["elapsed"] = (
                self.index if self.index is not None else 0,
                None,
                0.0,
            )
        d.save()

    def restart(self) -> None:
        self._clear()

    def _start(self, puzzle: Puzzle) -> None:
        self.board = Board(puzzle)
        self.elapsed = 0.0
        self.solved_at: float | None = None
        self.new_best = False
        self.cursor = (0, 0)

    def _open(self, index: int) -> None:
        self.index = index
        self._start(self.puzzles[index])

    def _random(self, size: int) -> None:
        self.index = None
        self._start(generate(size, random.Random()))

    def _label(self, index: int) -> str:
        puzzle = self.puzzles[index]
        if puzzle.name in self.best:
            return puzzle.name
        return f"#{index + 1} · {puzzle.width} × {puzzle.height}"

    def _undo(self) -> None:
        if not self.board.solved:
            self.board.undo()

    def _clear(self) -> None:
        if not self.board.solved:
            self.board.clear()
            self.elapsed = 0.0

    # ------------------------------------------------------------------ layout
    def _layout(self) -> tuple[int, int, int, int, int]:
        """(cell size, grid x, grid y, row-clue width, column-clue height)."""
        p = self.board.puzzle
        row_len = max(len(c) for c in p.row_clues)
        col_len = max(len(c) for c in p.col_clues)
        cell = int(
            min(
                40,
                AREA.width / (p.width + row_len * 0.8 + 0.5),
                AREA.height / (p.height + col_len * 0.8 + 0.5),
            )
        )
        clue_w = round(row_len * cell * 0.8) + 8
        clue_h = round(col_len * cell * 0.8) + 8
        total_w = clue_w + p.width * cell
        total_h = clue_h + p.height * cell
        gx = AREA.x + (AREA.width - total_w) // 2 + clue_w
        gy = AREA.y + (AREA.height - total_h) // 2 + clue_h
        return cell, gx, gy, clue_w, clue_h

    def cell_rect(self, r: int, c: int) -> pygame.Rect:
        cell, gx, gy, _, _ = self._layout()
        return pygame.Rect(gx + c * cell, gy + r * cell, cell, cell)

    def cell_at(self, pos: tuple[int, int]) -> tuple[int, int] | None:
        cell, gx, gy, _, _ = self._layout()
        c, r = (pos[0] - gx) // cell, (pos[1] - gy) // cell
        if 0 <= r < self.board.puzzle.height and 0 <= c < self.board.puzzle.width:
            return r, c
        return None

    # ------------------------------------------------------------------ painting
    def _begin_stroke(self, r: int, c: int, tool: int) -> None:
        current = self.board.marks[r][c]
        self.stroke = BLANK if current == tool else tool
        self.board.checkpoint()
        self._paint(r, c)

    def _paint(self, r: int, c: int) -> None:
        if self.stroke is None or self.board.solved:
            return
        self.board.set(r, c, self.stroke)
        self._check_solved()

    def _check_solved(self) -> None:
        if self.board.solved and self.solved_at is None:
            self._on_solved()

    def _on_solved(self) -> None:
        self.solved_at = self.time
        seconds = max(1, round(self.elapsed))
        self.stroke = None
        self.unlock("solve_1")
        p = self.board.puzzle
        if self.index is not None:
            old = self.best.get(p.name)
            self.new_best = old is None or seconds < old
            if self.new_best:
                self.best[p.name] = seconds
                self.data["best"] = self.best
                self.data.save()
            if all(q.name in self.best for q in self.puzzles):
                self.unlock("gallery")
        elif p.width >= 15:
            self.unlock("big_random")

    # ------------------------------------------------------------------ events
    def handle_event(self, event: pygame.event.Event) -> None:
        for button in (*self.list_buttons, *self.random_buttons, *self.tool_buttons):
            if button.handle_event(event):
                return
        if (
            event.type == pygame.MOUSEBUTTONDOWN
            and event.button in (1, 3)
            and not self.board.solved
        ):
            self.keyboard = False
            hit = self.cell_at(event.pos)
            if hit is not None:
                self._begin_stroke(*hit, FILL if event.button == 1 else CROSS)
        elif event.type == pygame.MOUSEMOTION and self.stroke is not None:
            hit = self.cell_at(event.pos)
            if hit is not None:
                self._paint(*hit)
        elif event.type == pygame.MOUSEBUTTONUP:
            self.stroke = None
        elif event.type == pygame.KEYDOWN and event.key == pygame.K_u:
            self._undo()
        elif event.type == pygame.KEYDOWN and event.key == pygame.K_x and not self.board.solved:
            self._key_mark(CROSS)
        else:
            action = action_of(event)
            if action in DIRECTION_STEPS:
                if self.keyboard:
                    dc, dr = DIRECTION_STEPS[action]
                    p = self.board.puzzle
                    self.cursor = (
                        (self.cursor[0] + dr) % p.height,
                        (self.cursor[1] + dc) % p.width,
                    )
                self.keyboard = True
            elif action == "action" and not event.repeat and not self.board.solved:
                self._key_mark(FILL)

    def _key_mark(self, tool: int) -> None:
        self.keyboard = True
        self._begin_stroke(*self.cursor, tool)
        self.stroke = None

    # ------------------------------------------------------------------ frame
    def update(self, dt: float) -> None:
        self.time += dt
        if not self.board.solved and any(m == FILL for row in self.board.marks for m in row):
            self.elapsed += dt
        for button in (*self.list_buttons, *self.random_buttons, *self.tool_buttons):
            button.update(dt)
        for i, button in enumerate(self.list_buttons):
            button.variant = "primary" if i == self.index else "ghost"
            button.accent = ACCENT
            button.text = self._label(i)
        for button in self.tool_buttons:
            button.enabled = not self.board.solved

    # ------------------------------------------------------------------ drawing
    def draw(self, surface: Canvas) -> None:
        t = self.theme
        p = t.palette
        surface.fill(p.bg)
        draw.text(surface, "Nonogram", t.font(t.size.heading, "bold"), p.text, (LIST_X, 44))
        draw.text(
            surface, "PUZZLES", t.font(t.size.caption, "semibold"), p.text_muted, (LIST_X, 88)
        )
        for button, puzzle in zip(self.list_buttons, self.puzzles, strict=True):
            button.draw(surface)
            if puzzle.name in self.best:
                draw.text(
                    surface,
                    clock(self.best[puzzle.name]),
                    t.font(t.size.caption, "semibold"),
                    p.success if button.variant != "primary" else (255, 255, 255),
                    (button.rect.right - 12, button.rect.centery),
                    "midright",
                )
        for button in (*self.random_buttons, *self.tool_buttons):
            button.draw(surface)
        self._draw_board(surface, t)

    def _draw_board(self, surface: Canvas, t: Theme) -> None:
        p = t.palette
        b = self.board
        puzzle = b.puzzle
        cell, gx, gy, clue_w, clue_h = self._layout()
        grid = pygame.Rect(gx, gy, puzzle.width * cell, puzzle.height * cell)
        solved = b.solved
        reveal = (
            min(1.0, (self.time - self.solved_at) / REVEAL_SECONDS)
            if self.solved_at is not None and solved
            else 0.0
        )

        # Header: name (hidden until solved, so it doesn't give the picture away) and timer
        title = self._label(self.index) if self.index is not None else puzzle.name
        if solved:
            title = puzzle.name
        draw.text(
            surface,
            title,
            t.font(t.size.title, "semibold"),
            p.text,
            (AREA.x, AREA.y - 30),
            "midleft",
        )
        status = clock(self.elapsed)
        if solved:
            status = f"Solved in {clock(self.elapsed)}" + (" · new best!" if self.new_best else "")
        draw.text(
            surface,
            status,
            t.font(t.size.label, "semibold"),
            p.success if solved else p.text_muted,
            (AREA.right, AREA.y - 30),
            "midright",
        )

        # Clues
        font = t.font(max(11, int(cell * 0.42)), "semibold")
        step = cell * 0.8
        for r, clue in enumerate(puzzle.row_clues):
            done = b.row_done(r)
            band = pygame.Rect(gx - clue_w, gy + r * cell, clue_w - 4, cell)
            if r == self.cursor[0] and self.keyboard:
                draw.rounded_rect(surface, band, lerp_color(p.bg, ACCENT, 0.15), 4)
            for k, n in enumerate(reversed(clue)):
                x = gx - 10 - k * step
                draw.text(
                    surface,
                    str(n),
                    font,
                    p.text_muted if done else p.text,
                    (x, band.centery),
                    "midright",
                )
        for c, clue in enumerate(puzzle.col_clues):
            done = b.col_done(c)
            band = pygame.Rect(gx + c * cell, gy - clue_h, cell, clue_h - 4)
            if c == self.cursor[1] and self.keyboard:
                draw.rounded_rect(surface, band, lerp_color(p.bg, ACCENT, 0.15), 4)
            for k, n in enumerate(reversed(clue)):
                y = gy - 8 - k * step
                draw.text(
                    surface,
                    str(n),
                    font,
                    p.text_muted if done else p.text,
                    (band.centerx, y),
                    "midbottom",
                )

        # Grid
        draw.shadow(surface, grid, 4, p.shadow, (0, 6), 12)
        gfx.rect(surface, p.surface, grid)
        for r, c in b.cells():
            rect = self.cell_rect(r, c)
            mark = b.marks[r][c]
            if solved:
                if puzzle.filled(r, c):
                    # Cells light up in a diagonal wave as the picture is revealed.
                    wave = min(
                        1.0, max(0.0, reveal * 2.2 - (r + c) / (puzzle.width + puzzle.height))
                    )
                    gfx.rect(surface, lerp_color(p.text, puzzle.color, wave), rect.inflate(-1, -1))
                continue
            if mark == FILL:
                gfx.rect(surface, p.text, rect.inflate(-2, -2), border_radius=3)
            elif mark == CROSS:
                arm = cell * 0.28
                cx, cy = rect.center
                ink = p.text_muted
                gfx.line(surface, ink, (cx - arm, cy - arm), (cx + arm, cy + arm), 2)
                gfx.line(surface, ink, (cx - arm, cy + arm), (cx + arm, cy - arm), 2)
        if not solved:
            for i in range(puzzle.width + 1):
                x = gx + i * cell
                bold = i % 5 == 0
                gfx.line(
                    surface,
                    p.text_muted if bold else p.border,
                    (x, gy),
                    (x, grid.bottom),
                    2 if bold else 1,
                )
            for i in range(puzzle.height + 1):
                y = gy + i * cell
                bold = i % 5 == 0
                gfx.line(
                    surface,
                    p.text_muted if bold else p.border,
                    (gx, y),
                    (grid.right, y),
                    2 if bold else 1,
                )
            if self.keyboard:
                draw.rounded_rect(surface, self.cell_rect(*self.cursor).inflate(4, 4), ACCENT, 4, 3)
        hint = "Left click fill · right click cross · drag to paint · arrows + Space / X · U undo"
        draw.text(
            surface, hint, t.font(t.size.caption), p.text_muted, (AREA.centerx, 706), "midbottom"
        )
