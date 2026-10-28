"""Sudoku UI: board rendering, number pad, difficulty chooser and solved dialog."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Literal

import pygame

from apps.sudoku.logic import DIFFICULTIES, PEERS, Difficulty, SudokuGame
from core import draw, gfx
from core.base_app import AppMeta, BaseApp, format_score
from core.canvas import Canvas
from core.registry import register_app
from core.theme import Color, Theme, lerp_color
from core.widgets import Button, ButtonMenu, Grid, draw_panel

ACCENT: Color = (155, 120, 255)
CELL = 68
BOARD = pygame.Rect(80, 54, CELL * 9, CELL * 9)
SIDE_X = BOARD.right + 56
SIDE_W = 1280 - SIDE_X - 80
CHECK_SECONDS = 2.5
SAVE_KEY = "saved_game"

DIGIT_KEYS = {getattr(pygame, f"K_{d}"): d for d in range(1, 10)} | {
    getattr(pygame, f"K_KP{d}"): d for d in range(1, 10)
}
MOVE_KEYS = {
    pygame.K_UP: (-1, 0),
    pygame.K_w: (-1, 0),
    pygame.K_DOWN: (1, 0),
    pygame.K_s: (1, 0),
    pygame.K_LEFT: (0, -1),
    pygame.K_a: (0, -1),
    pygame.K_RIGHT: (0, 1),
    pygame.K_d: (0, 1),
}

Mode = Literal["choose", "playing", "solved"]


def cell_rect(i: int) -> pygame.Rect:
    return pygame.Rect(BOARD.x + (i % 9) * CELL, BOARD.y + (i // 9) * CELL, CELL, CELL)


def cell_at(pos: tuple[int, int]) -> int | None:
    if not BOARD.collidepoint(pos):
        return None
    return ((pos[1] - BOARD.y) // CELL) * 9 + (pos[0] - BOARD.x) // CELL


@register_app
class SudokuApp(BaseApp):
    """Classic 9×9 Sudoku with three difficulties and best times per difficulty."""

    meta = AppMeta(
        id="sudoku",
        name="Sudoku",
        description="Logic puzzles with notes, checks and best times.",
        category="game",
        accent=ACCENT,
        tracks_scores=True,
        score_order="lower",
        score_format="time",
        variants=DIFFICULTIES,
    )

    @classmethod
    def draw_icon(cls, surface: Canvas, rect: pygame.Rect, theme: Theme) -> None:
        draw.rounded_rect(surface, rect, ACCENT, theme.radius.md)
        inner = rect.inflate(-rect.width // 3, -rect.height // 3)
        step = inner.width / 3
        for k in (1, 2):
            x = round(inner.x + k * step)
            y = round(inner.y + k * step)
            gfx.line(surface, (255, 255, 255), (x, inner.y), (x, inner.bottom), 2)
            gfx.line(surface, (255, 255, 255), (inner.x, y), (inner.right, y), 2)
        font = theme.font(max(8, round(step * 0.8)), "bold")
        for (c, r), digit in (((0, 0), "5"), ((2, 1), "3"), ((1, 2), "9")):
            pos = (round(inner.x + (c + 0.5) * step), round(inner.y + (r + 0.5) * step))
            draw.text(surface, digit, font, (255, 255, 255), pos, "center")

    # ------------------------------------------------------------------ lifecycle
    def on_enter(self) -> None:
        self.game: SudokuGame | None = None
        self.mode: Mode = "choose"
        self.check_cells: set[int] = set()
        self.check_timer = 0.0
        self.toast = ""
        self.new_best = False
        self._build_side_panel()
        self.dialog: ButtonMenu | None = self._chooser()

    def on_exit(self) -> None:
        if self.game is not None and self.mode == "playing":
            self.data[SAVE_KEY] = _serialize(self.game)
        else:
            self.data.pop(SAVE_KEY, None)
        self.data.save()

    def restart(self) -> None:
        """Restart = a fresh puzzle at the same difficulty."""
        difficulty = self.game.difficulty if self.game else "easy"
        self.data.pop(SAVE_KEY, None)
        self.data.save()
        self._start(difficulty)

    def _start(self, difficulty: Difficulty) -> None:
        self._begin(SudokuGame.new(difficulty))

    def _continue(self, saved: dict[str, Any]) -> None:
        self._begin(_deserialize(saved))

    def _begin(self, game: SudokuGame) -> None:
        self.game = game
        self.mode = "playing"
        self.dialog = None
        self.check_cells.clear()
        self.toast = ""

    # ------------------------------------------------------------------ UI building
    def _chooser(self) -> ButtonMenu:
        items: list[tuple[str, Callable[[], None]]] = []
        saved = self.data.get(SAVE_KEY)
        if isinstance(saved, dict) and _valid_save(saved):
            label = (
                f"Continue · {saved['difficulty'].title()} {format_score(saved['elapsed'], 'time')}"
            )
            items.append((label, lambda: self._continue(saved)))
        for d in DIFFICULTIES:
            best = self.best_score(d)
            suffix = f"   · best {format_score(best.score, 'time')}" if best else ""
            items.append((f"{d.title()}{suffix}", lambda d=d: self._start(d)))  # type: ignore[misc]
        return ButtonMenu(self.theme, (640, 390), items, width=320, accent=ACCENT)

    def _open_chooser(self) -> None:
        if self.game is not None and self.mode == "playing":
            # Keep the current game so "Continue" is offered.
            self.data[SAVE_KEY] = _serialize(self.game)
        self.mode = "choose"
        self.dialog = self._chooser()

    def _build_side_panel(self) -> None:
        t = self.theme
        pad = Grid(pygame.Rect(SIDE_X, 214, SIDE_W, 3 * 72 + 2 * 12), 3, 72, 12)
        self.digit_buttons = [
            Button(t, pad.cell(d - 1), str(d), lambda d=d: self._enter(d), font_size=28)  # type: ignore[misc]
            for d in range(1, 10)
        ]
        actions = Grid(pygame.Rect(SIDE_X, 478, SIDE_W, 48), 4, 48, 12)
        self.pencil_btn = Button(t, actions.cell(0), "Notes", self._toggle_pencil)
        self.action_buttons = [
            self.pencil_btn,
            Button(t, actions.cell(1), "Erase", self._erase),
            Button(t, actions.cell(2), "Undo", self._undo),
            Button(t, actions.cell(3), "Check", self._check),
        ]
        self.new_btn = Button(
            t, (SIDE_X, 540, SIDE_W, 48), "New game", self._open_chooser, "primary", accent=ACCENT
        )

    def _widgets(self) -> list[Button]:
        return [*self.digit_buttons, *self.action_buttons, self.new_btn]

    # ------------------------------------------------------------------ actions
    def _enter(self, digit: int) -> None:
        if self.game is None or self.mode != "playing":
            return
        self.game.enter(digit)
        if self.game.solved:
            self._on_solved()

    def _erase(self) -> None:
        if self.game and self.mode == "playing":
            self.game.erase()

    def _undo(self) -> None:
        if self.game and self.mode == "playing":
            self.game.undo()

    def _toggle_pencil(self) -> None:
        if self.game:
            self.game.toggle_pencil()

    def _check(self) -> None:
        if self.game is None or self.mode != "playing":
            return
        self.check_cells = self.game.wrong_cells()
        self.check_timer = CHECK_SECONDS
        n = len(self.check_cells)
        self.toast = "Looking good so far!" if n == 0 else f"{n} cell{'s' if n > 1 else ''} wrong"

    def _on_solved(self) -> None:
        assert self.game is not None
        self.mode = "solved"
        seconds = round(self.game.elapsed)
        self.new_best = self.submit_score(seconds, self.game.difficulty)
        self.data.pop(SAVE_KEY, None)
        self.data.save()
        self.dialog = ButtonMenu(
            self.theme,
            (640, 420),
            [("New game", self._open_chooser), ("Back to menu", self.exit_to_launcher)],
            accent=ACCENT,
        )

    # ------------------------------------------------------------------ events
    def handle_event(self, event: pygame.event.Event) -> None:
        if self.dialog is not None:
            self.dialog.handle_event(event)
            return
        for button in self._widgets():
            if button.handle_event(event):
                return
        game = self.game
        if game is None:
            return
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            index = cell_at(event.pos)
            if index is not None:
                game.select(index)
        elif event.type == pygame.KEYDOWN:
            self._handle_key(event, game)

    def _handle_key(self, event: pygame.event.Event, game: SudokuGame) -> None:
        mods = pygame.key.get_mods()
        if event.key in MOVE_KEYS:
            game.move(*MOVE_KEYS[event.key])
        elif event.key in DIGIT_KEYS:
            self._enter(DIGIT_KEYS[event.key])
            self._flash(self.digit_buttons[DIGIT_KEYS[event.key] - 1])
        elif event.key in (pygame.K_0, pygame.K_KP0, pygame.K_BACKSPACE, pygame.K_DELETE):
            self._erase()
        elif event.key == pygame.K_u or (
            event.key == pygame.K_z and mods & (pygame.KMOD_CTRL | pygame.KMOD_META)
        ):
            self._undo()
        elif event.key in (pygame.K_p, pygame.K_SPACE):
            self._toggle_pencil()
        elif event.key == pygame.K_c:
            self._check()
        elif event.key == pygame.K_n:
            self._open_chooser()

    @staticmethod
    def _flash(button: Button) -> None:
        button.flash()

    def update(self, dt: float) -> None:
        if self.game is not None and self.mode == "playing":
            self.game.tick(dt)
        if self.check_timer > 0:
            self.check_timer -= dt
            if self.check_timer <= 0:
                self.check_cells.clear()
                self.toast = ""
        for button in self._widgets():
            button.update(dt)
        if self.game is not None:
            self.pencil_btn.variant = "primary" if self.game.pencil else "secondary"
            self.pencil_btn.accent = ACCENT
            self.pencil_btn.text = "Notes: on" if self.game.pencil else "Notes"
        if self.dialog is not None:
            self.dialog.update(dt)

    # ------------------------------------------------------------------ drawing
    def draw(self, surface: Canvas) -> None:
        t = self.theme
        surface.fill(t.palette.bg)
        self._draw_board(surface, t)
        self._draw_side(surface, t)
        if self.dialog is not None:
            draw.overlay(surface, t.palette.overlay)
            self._draw_dialog(surface, t)

    def _draw_board(self, surface: Canvas, t: Theme) -> None:
        p = t.palette
        draw.shadow(surface, BOARD, t.radius.md, p.shadow, (0, 8), 16)
        draw.rounded_rect(surface, BOARD, p.surface, t.radius.md)
        game = self.game
        if game is not None:
            self._draw_cells(surface, t, game)
        # Grid lines: thin between cells, thick between boxes.
        for k in range(1, 9):
            thick = k % 3 == 0
            color = p.text_muted if thick else p.border
            width = 3 if thick else 1
            x = BOARD.x + k * CELL
            y = BOARD.y + k * CELL
            gfx.line(surface, color, (x, BOARD.y), (x, BOARD.bottom - 1), width)
            gfx.line(surface, color, (BOARD.x, y), (BOARD.right - 1, y), width)
        draw.rounded_rect(surface, BOARD, p.text_muted, t.radius.md, 3)

    def _draw_cells(self, surface: Canvas, t: Theme, game: SudokuGame) -> None:
        p = t.palette
        sel = game.selected
        sel_value = game.values[sel]
        conflicts = game.conflicts()
        related = PEERS[sel]
        big = t.font(36, "semibold")
        big_given = t.font(36, "bold")
        small = t.font(14, "medium")
        entry_color = lerp_color(ACCENT, p.text, 0.25)
        clip = surface.get_clip()
        surface.set_clip(BOARD)  # keep corner tints inside the rounded board
        for i in range(81):
            rect = cell_rect(i)
            value = game.values[i]
            tint: Color | None = None
            if i == sel:
                tint = lerp_color(p.surface, ACCENT, 0.42)
            elif value and value == sel_value:
                tint = lerp_color(p.surface, ACCENT, 0.24)
            elif i in related:
                tint = lerp_color(p.surface, ACCENT, 0.09)
            if i in conflicts or i in self.check_cells:
                tint = lerp_color(
                    tint or p.surface, p.danger, 0.3 if i in self.check_cells else 0.18
                )
            if tint is not None:
                gfx.rect(surface, tint, rect)

            if value:
                given = game.is_given(i)
                color = p.text if given else entry_color
                if i in conflicts or i in self.check_cells:
                    color = p.danger
                draw.text(
                    surface, str(value), big_given if given else big, color, rect.center, "center"
                )
            elif game.notes[i]:
                for d in game.note_digits(i):
                    r, c = divmod(d - 1, 3)
                    pos = (rect.x + 12 + c * 22, rect.y + 12 + r * 22)
                    hl = sel_value == d
                    draw.text(surface, str(d), small, ACCENT if hl else p.text_muted, pos, "center")
        surface.set_clip(clip)

    def _draw_side(self, surface: Canvas, t: Theme) -> None:
        p = t.palette
        game = self.game
        draw.text(surface, "Sudoku", t.font(t.size.heading, "bold"), p.text, (SIDE_X, 50))
        if game is not None:
            chip = game.difficulty.title()
            font = t.font(t.size.caption, "semibold")
            rect = pygame.Rect(0, 0, font.size(chip)[0] + 20, 26)
            rect.topright = (SIDE_X + SIDE_W, 56)
            draw.rounded_rect(surface, rect, lerp_color(p.surface, ACCENT, 0.3), t.radius.pill)
            draw.text(surface, chip, font, p.text, rect.center, "center")
            draw.text(
                surface,
                format_score(game.elapsed, "time"),
                t.font(t.size.display, "bold"),
                ACCENT,
                (SIDE_X, 96),
            )
            best = self.best_score(game.difficulty)
            best_text = f"Best {format_score(best.score, 'time')}" if best else "No best time yet"
            draw.text(surface, best_text, t.font(t.size.label), p.text_muted, (SIDE_X, 154))
            if self.toast:
                color = p.success if not self.check_cells else p.danger
                draw.text(
                    surface,
                    self.toast,
                    t.font(t.size.label, "semibold"),
                    color,
                    (SIDE_X + SIDE_W, 154),
                    "topright",
                )

        for button in self._widgets():
            button.draw(surface)
        if game is not None:
            count_font = t.font(t.size.caption, "medium")
            for d, button in enumerate(self.digit_buttons, start=1):
                left = game.remaining(d)
                label = "✓" if left <= 0 else str(left)
                draw.text(
                    surface,
                    label,
                    count_font,
                    p.text_muted,
                    (button.rect.right - 10, button.rect.y + 6),
                    "topright",
                )

        hint = "Arrows move · 1–9 place · P notes · U undo · C check · N new"
        draw.text(
            surface,
            hint,
            t.font(t.size.caption),
            p.text_muted,
            (SIDE_X, BOARD.bottom),
            "bottomleft",
        )

    def _draw_dialog(self, surface: Canvas, t: Theme) -> None:
        assert self.dialog is not None
        p = t.palette
        menu = self.dialog.rect
        if self.mode == "solved" and self.game is not None:
            panel = pygame.Rect(0, 0, 400, menu.height + 210)
            panel.midbottom = (menu.centerx, menu.bottom + 32)
            draw_panel(surface, panel, t)
            draw.text(
                surface,
                "Solved!",
                t.font(t.size.heading, "bold"),
                p.text,
                (panel.centerx, panel.y + 30),
                "midtop",
            )
            time_text = format_score(round(self.game.elapsed), "time")
            draw.text(
                surface,
                time_text,
                t.font(t.size.display, "bold"),
                ACCENT,
                (panel.centerx, panel.y + 76),
                "midtop",
            )
            sub = "New best time!" if self.new_best else f"{self.game.difficulty.title()} puzzle"
            draw.text(
                surface,
                sub,
                t.font(t.size.label, "semibold"),
                p.success if self.new_best else p.text_muted,
                (panel.centerx, panel.y + 134),
                "midtop",
            )
        else:
            panel = pygame.Rect(0, 0, 400, menu.height + 150)
            panel.midbottom = (menu.centerx, menu.bottom + 32)
            draw_panel(surface, panel, t)
            draw.text(
                surface,
                "New puzzle",
                t.font(t.size.heading, "bold"),
                p.text,
                (panel.centerx, panel.y + 28),
                "midtop",
            )
            draw.text(
                surface,
                "Choose a difficulty",
                t.font(t.size.label),
                p.text_muted,
                (panel.centerx, panel.y + 72),
                "midtop",
            )
        self.dialog.draw(surface)


# ---------------------------------------------------------------------- persistence
def _serialize(game: SudokuGame) -> dict[str, Any]:
    return {
        "puzzle": game.puzzle,
        "solution": game.solution,
        "values": game.values,
        "notes": game.notes,
        "difficulty": game.difficulty,
        "elapsed": round(game.elapsed, 1),
    }


def _valid_save(data: dict[str, Any]) -> bool:
    try:
        lists_ok = all(len(data[k]) == 81 for k in ("puzzle", "solution", "values", "notes"))
        return lists_ok and data["difficulty"] in DIFFICULTIES and float(data["elapsed"]) >= 0
    except (KeyError, TypeError, ValueError):
        return False


def _deserialize(data: dict[str, Any]) -> SudokuGame:
    game = SudokuGame(
        puzzle=[int(v) for v in data["puzzle"]],
        solution=[int(v) for v in data["solution"]],
        difficulty=data["difficulty"],
        values=[int(v) for v in data["values"]],
        notes=[int(v) for v in data["notes"]],
    )
    game.elapsed = float(data["elapsed"])
    return game
