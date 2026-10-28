"""Four in a Row UI: falling discs, column preview, background CPU thinking."""

from __future__ import annotations

import math
import random
import threading

import pygame

from apps.four_in_a_row.logic import (
    COLS,
    LEVELS,
    ROWS,
    Board,
    FourInARow,
    Level,
    Player,
    choose_move,
)
from core import draw
from core.base_app import AppMeta, BaseApp
from core.registry import register_app
from core.theme import Color, Theme, lerp_color
from core.widgets import Button, SegmentedControl

ACCENT: Color = (99, 102, 241)
DISC_COLORS: dict[int, Color] = {1: (45, 212, 191), 2: (251, 113, 133)}
CELL = 82
BOARD = pygame.Rect(110, 150, COLS * CELL, ROWS * CELL)
SIDE_X = BOARD.right + 80
GRAVITY = 4200.0  # px/s² for the falling animation
MIN_CPU_DELAY = 0.35  # so instant moves don't feel abrupt

COLUMN_KEYS = {getattr(pygame, f"K_{n}"): n - 1 for n in range(1, COLS + 1)} | {
    getattr(pygame, f"K_KP{n}"): n - 1 for n in range(1, COLS + 1)
}


def slot_center(row: int, col: int) -> tuple[int, int]:
    """Screen centre of a slot. Row 0 is the bottom row."""
    return (BOARD.x + col * CELL + CELL // 2, BOARD.bottom - row * CELL - CELL // 2)


class _CpuWorker:
    """Runs the search on a background thread so the UI keeps animating."""

    def __init__(self, board: Board, player: Player, level: Level, rng: random.Random) -> None:
        self.result: int | None = None
        self._thread = threading.Thread(
            target=self._run, args=(board.copy(), player, level, rng), daemon=True
        )
        self._thread.start()

    def _run(self, board: Board, player: Player, level: Level, rng: random.Random) -> None:
        self.result = choose_move(board, player, level, rng)

    @property
    def done(self) -> bool:
        return not self._thread.is_alive()


@register_app
class FourInARowApp(BaseApp):
    """Drop discs into a 7×6 grid and line up four before the computer does."""

    meta = AppMeta(
        id="four_in_a_row",
        name="Four in a Row",
        description="Drop discs and line up four before the computer does.",
        category="game",
        accent=ACCENT,
    )

    @classmethod
    def draw_icon(cls, surface: pygame.Surface, rect: pygame.Rect, theme: Theme) -> None:
        draw.rounded_rect(surface, rect, ACCENT, theme.radius.md)
        u = rect.width / 4
        pattern = ((0, 1), (1, 2), (2, 1), (0, 2), (1, 1), (2, 2), (0, 0))
        for i, (c, r) in enumerate(pattern):
            color = DISC_COLORS[1] if i % 2 == 0 else DISC_COLORS[2]
            pygame.draw.circle(
                surface,
                color,
                (rect.x + (c + 0.5) * u + u / 2, rect.y + (r + 0.5) * u + u / 2),
                u * 0.4,
            )

    # ------------------------------------------------------------------ lifecycle
    def on_enter(self) -> None:
        t = self.theme
        level = self.data.get("level", "medium")
        self.level: Level = level if level in LEVELS else "medium"
        self.human_first = bool(self.data.get("human_first", True))
        self.level_picker = SegmentedControl(
            t,
            (SIDE_X, 238, 340, 40),
            ["Easy", "Medium", "Hard"],
            LEVELS.index(self.level),
            self._set_level,
            accent=ACCENT,
        )
        self.first_picker = SegmentedControl(
            t,
            (SIDE_X, 324, 340, 40),
            ["You start", "CPU starts"],
            0 if self.human_first else 1,
            self._set_first,
            accent=ACCENT,
        )
        self.new_btn = Button(
            t, (SIDE_X, 560, 340, 52), "New round", self._new_round, "primary", accent=ACCENT
        )
        self.rng = random.Random()
        self.hover_col = COLS // 2
        self.time = 0.0
        self._new_round()

    def _set_level(self, index: int) -> None:
        self.level_picker.index = index
        self.level = LEVELS[index]
        self._save_prefs()
        self._new_round()

    def _set_first(self, index: int) -> None:
        self.first_picker.index = index
        self.human_first = index == 0
        self._save_prefs()
        self._new_round()

    def _save_prefs(self) -> None:
        self.data["level"] = self.level
        self.data["human_first"] = self.human_first
        self.data.save()

    def _new_round(self) -> None:
        self.game = FourInARow(human=1 if self.human_first else 2, level=self.level, rng=self.rng)
        self.worker: _CpuWorker | None = None  # a stale worker's result is simply dropped
        self.cpu_wait = 0.0
        self.falling: tuple[int, int, float, float] | None = None  # row, col, y, velocity
        self.recorded = False

    def restart(self) -> None:
        self._new_round()

    # ------------------------------------------------------------------ tally
    def tally(self) -> list[int]:
        raw = self.data.get("tally", {}).get(self.level, [0, 0, 0])
        return [int(v) for v in raw] if isinstance(raw, list) and len(raw) == 3 else [0, 0, 0]

    def _record_result(self) -> None:
        if self.recorded or not self.game.over:
            return
        self.recorded = True
        tally = self.tally()
        w = self.game.winner
        tally[0 if w == self.game.human else 1 if w is None else 2] += 1
        all_tallies = dict(self.data.get("tally", {}))
        all_tallies[self.level] = tally
        self.data["tally"] = all_tallies
        self.data.save()

    # ------------------------------------------------------------------ moves
    @property
    def busy(self) -> bool:
        return self.falling is not None

    def _drop(self, col: int) -> None:
        landed = self.game.drop(col)
        if landed is not None:
            row, col = landed
            self.falling = (row, col, float(BOARD.y - CELL // 2), 0.0)

    def _human_drop(self, col: int) -> None:
        if self.busy or self.game.over or self.game.turn != self.game.human:
            return
        self._drop(col)

    def handle_event(self, event: pygame.event.Event) -> None:
        for widget in (self.level_picker, self.first_picker, self.new_btn):
            if widget.handle_event(event):
                return
        if event.type == pygame.MOUSEMOTION:
            if BOARD.left <= event.pos[0] < BOARD.right:
                self.hover_col = (event.pos[0] - BOARD.x) // CELL
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            area = BOARD.inflate(0, CELL * 2)
            if area.collidepoint(event.pos):
                if self.game.over:
                    self._new_round()
                else:
                    self._human_drop((event.pos[0] - BOARD.x) // CELL)
        elif event.type == pygame.KEYDOWN:
            if event.key in COLUMN_KEYS:
                self.hover_col = COLUMN_KEYS[event.key]
                self._human_drop(self.hover_col)
            elif event.key in (pygame.K_LEFT, pygame.K_a):
                self.hover_col = max(0, self.hover_col - 1)
            elif event.key in (pygame.K_RIGHT, pygame.K_d):
                self.hover_col = min(COLS - 1, self.hover_col + 1)
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_DOWN, pygame.K_s):
                if self.game.over:
                    self._new_round()
                else:
                    self._human_drop(self.hover_col)
            elif event.key == pygame.K_n:
                self._new_round()

    def update(self, dt: float) -> None:
        self.time += dt
        for widget in (self.level_picker, self.first_picker, self.new_btn):
            widget.update(dt)
        self._update_falling(dt)
        if self.busy:
            return
        self._record_result()
        game = self.game
        if game.over or game.turn != game.cpu:
            return
        if self.worker is None:
            self.worker = _CpuWorker(game.board, game.cpu, game.level, self.rng)
            self.cpu_wait = 0.0
        self.cpu_wait += dt
        if self.worker.done and self.cpu_wait >= MIN_CPU_DELAY and self.worker.result is not None:
            col = self.worker.result
            self.worker = None
            self._drop(col)

    def _update_falling(self, dt: float) -> None:
        if self.falling is None:
            return
        row, col, y, vy = self.falling
        target = slot_center(row, col)[1]
        vy += GRAVITY * dt
        y += vy * dt
        if y >= target:
            if vy > 900:  # bounce once, softly
                y, vy = float(target), -vy * 0.25
            else:
                self.falling = None
                return
        self.falling = (row, col, y, vy)

    # ------------------------------------------------------------------ drawing
    def _status(self) -> tuple[str, Color]:
        p = self.theme.palette
        g = self.game
        if g.winner == g.human:
            return "You win!", p.success
        if g.winner is not None:
            return "The computer wins", p.danger
        if g.board.full():
            return "It's a draw", p.text_muted
        if g.turn == g.human:
            return "Your turn", p.text
        return "Thinking" + "." * (1 + int(self.time * 3) % 3), p.text_muted

    def draw(self, surface: pygame.Surface) -> None:
        t = self.theme
        p = t.palette
        surface.fill(p.bg)
        g = self.game

        # Layers, back to front: shadow, recessed slot background, hover column, discs,
        # then the frame with transparent holes (so a falling disc passes behind it).
        hole = CELL * 0.4
        frame = BOARD.inflate(24, 24)
        draw.shadow(surface, frame, t.radius.lg, p.shadow, (0, 10), 18)
        pygame.draw.rect(surface, lerp_color(p.bg, ACCENT, 0.08), frame, border_radius=t.radius.lg)
        preview = (
            not g.over and g.turn == g.human and not self.busy and g.board.can_drop(self.hover_col)
        )
        if preview:
            column = pygame.Rect(BOARD.x + self.hover_col * CELL, BOARD.y, CELL, BOARD.height)
            pygame.draw.rect(surface, lerp_color(p.bg, ACCENT, 0.3), column)
        for r in range(ROWS):
            for c in range(COLS):
                v = g.board.grid[r][c]
                if v and (self.falling is None or (r, c) != self.falling[:2]):
                    self._disc(surface, slot_center(r, c), DISC_COLORS[v], hole + 2)
        if self.falling is not None:
            row, col, y, _ = self.falling
            center = (slot_center(row, col)[0], round(y))
            self._disc(surface, center, DISC_COLORS[g.board.grid[row][col]], hole + 2)

        layer = pygame.Surface(frame.size, pygame.SRCALPHA)
        pygame.draw.rect(
            layer, lerp_color(ACCENT, p.bg, 0.35), layer.get_rect(), border_radius=t.radius.lg
        )
        for r in range(ROWS):
            for c in range(COLS):
                x, y = slot_center(r, c)
                pygame.draw.circle(layer, (0, 0, 0, 0), (x - frame.x, y - frame.y), hole)
        surface.blit(layer, frame.topleft)
        if preview:
            cx = BOARD.x + self.hover_col * CELL + CELL // 2
            self._disc(surface, (cx, frame.y - CELL // 2), DISC_COLORS[g.human], CELL * 0.38)

        if g.win_cells and not self.busy:
            pulse = 0.5 + 0.5 * math.sin(self.time * 6)
            for r, c in g.win_cells:
                pygame.draw.circle(
                    surface,
                    lerp_color(p.text, (255, 255, 255), pulse),
                    slot_center(r, c),
                    hole - 4,
                    4,
                )
        self._draw_side(surface, t)

    @staticmethod
    def _disc(surface: pygame.Surface, center: tuple[float, float], color: Color, r: float) -> None:
        pygame.draw.circle(surface, color, center, r)
        pygame.draw.circle(surface, lerp_color(color, (0, 0, 0), 0.18), center, r * 0.72, 3)

    def _draw_side(self, surface: pygame.Surface, t: Theme) -> None:
        p = t.palette
        draw.text(surface, "Four in a Row", t.font(t.size.heading, "bold"), p.text, (SIDE_X, 120))
        status, color = self._status()
        draw.text(surface, status, t.font(t.size.title, "semibold"), color, (SIDE_X, 170))
        for label, y in (("Computer", 214), ("Who starts", 300)):
            draw.text(
                surface,
                label.upper(),
                t.font(t.size.caption, "semibold"),
                p.text_muted,
                (SIDE_X, y),
            )
        self.level_picker.draw(surface)
        self.first_picker.draw(surface)
        wins, draws, losses = self.tally()
        for i, (label, value, color) in enumerate(
            (
                ("You", wins, DISC_COLORS[self.game.human]),
                ("Draws", draws, p.text_muted),
                ("CPU", losses, DISC_COLORS[self.game.cpu]),
            )
        ):
            box = pygame.Rect(SIDE_X + i * 116, 400, 108, 84)
            draw.rounded_rect(surface, box, p.surface_alt, t.radius.md)
            draw.text(
                surface,
                label.upper(),
                t.font(t.size.caption, "semibold"),
                p.text_muted,
                (box.centerx, box.y + 14),
                "midtop",
            )
            draw.text(
                surface,
                str(value),
                t.font(t.size.heading, "bold"),
                color,
                (box.centerx, box.y + 36),
                "midtop",
            )
        draw.text(
            surface,
            f"Record vs {self.level} computer",
            t.font(t.size.caption),
            p.text_muted,
            (SIDE_X, 496),
        )
        self.new_btn.draw(surface)
        draw.text(
            surface,
            "Click a column or press 1–7 · ←/→ + Enter · N new round",
            t.font(t.size.caption),
            p.text_muted,
            (SIDE_X, 632),
        )
