"""2048 UI: animated board, swipe/keyboard input, score panel and dialogs."""

from __future__ import annotations

import math
import random
from typing import Any, Literal

import pygame

from apps.twenty48.logic import GOAL, SIZE, Direction, Game2048, MoveResult
from core import draw, gfx
from core.base_app import BaseApp
from core.canvas import Canvas
from core.input import Action, action_of
from core.registry import register_app
from core.theme import Color, Theme, lerp_color, readable_on
from core.widgets import Button, ButtonMenu, draw_panel

ACCENT: Color = (14, 165, 233)
CELL, GAP = 124, 14
BOARD = pygame.Rect(150, 92, SIZE * CELL + (SIZE + 1) * GAP, SIZE * CELL + (SIZE + 1) * GAP)
SIDE_X = BOARD.right + 64
SLIDE_SECONDS = 0.1
POP_SECONDS = 0.16
SWIPE_DISTANCE = 40
SAVE_KEY = "saved_game"

#: Tile colors from 2 up to 2048 (a cool-to-warm ramp); larger tiles use the last one.
TILE_COLORS: tuple[Color, ...] = (
    (226, 232, 240),
    (203, 213, 225),
    (125, 211, 252),
    (56, 189, 248),
    (96, 165, 250),
    (129, 140, 248),
    (167, 139, 250),
    (192, 132, 252),
    (232, 121, 249),
    (244, 114, 182),
    (251, 191, 36),
    (52, 211, 153),
)
DARK_TEXT: Color = (30, 41, 59)

SLIDES: dict[Action, Direction] = {"up": "up", "down": "down", "left": "left", "right": "right"}

Dialog = Literal["none", "won", "over"]


def tile_color(value: int) -> Color:
    index = max(0, min(len(TILE_COLORS) - 1, int(math.log2(value)) - 1))
    return TILE_COLORS[index]


def cell_rect(pos: tuple[float, float]) -> pygame.Rect:
    r, c = pos
    return pygame.Rect(
        round(BOARD.x + GAP + c * (CELL + GAP)), round(BOARD.y + GAP + r * (CELL + GAP)), CELL, CELL
    )


@register_app
class Twenty48App(BaseApp):
    """Slide tiles to merge equal numbers and reach 2048."""

    @classmethod
    def draw_icon(cls, surface: Canvas, rect: pygame.Rect, theme: Theme) -> None:
        draw.rounded_rect(surface, rect, (30, 41, 59), theme.radius.md)
        half = (rect.width - 9) // 2
        values = (2, 4, 8, 2048)
        for i, v in enumerate(values):
            r = pygame.Rect(
                rect.x + 3 + (i % 2) * (half + 3), rect.y + 3 + (i // 2) * (half + 3), half, half
            )
            gfx.rect(surface, tile_color(v), r, border_radius=4)

    # ------------------------------------------------------------------ lifecycle
    def on_enter(self) -> None:
        saved = self.data.get(SAVE_KEY)
        restored = _deserialize(saved) if isinstance(saved, dict) else None
        self.game = restored if restored is not None and not restored.over else Game2048.new()
        self.celebrated = self.game.won
        self.dialog: Dialog = "none"
        self.menu: ButtonMenu | None = None
        self.new_best = False
        self.last: MoveResult | None = None
        self.anim = 1.0  # seconds since the last move
        self.drag_start: tuple[int, int] | None = None
        self.new_btn = Button(
            self.theme, (SIDE_X, 330, 300, 52), "New game", self._new_game, "primary", accent=ACCENT
        )

    def on_exit(self) -> None:
        self._record()
        if self.game.over:
            self.data.pop(SAVE_KEY, None)
        else:
            self.data[SAVE_KEY] = _serialize(self.game)
        self.data.save()

    def restart(self) -> None:
        self._new_game()

    def _record(self) -> bool:
        return self.game.score > 0 and self.submit_score(self.game.score)

    def _new_game(self) -> None:
        self._record()
        self.game = Game2048.new()
        self.celebrated = False
        self._close_dialog()
        self.last = None
        self.anim = 1.0

    # ------------------------------------------------------------------ input
    def _move(self, direction: Direction) -> None:
        if self.dialog != "none":
            return
        result = self.game.move(direction)
        if not result.moved:
            return
        self.last = result
        self.anim = 0.0
        if self.game.over:
            self.new_best = self._record()
            self._open_dialog("over")
        elif self.game.won and not self.celebrated:
            self.celebrated = True
            self._open_dialog("won")

    def _open_dialog(self, kind: Dialog) -> None:
        self.dialog = kind
        items = (
            [("Keep going", self._close_dialog), ("New game", self._new_game)]
            if kind == "won"
            else [("Try again", self._new_game), ("Back to menu", self.exit_to_launcher)]
        )
        self.menu = ButtonMenu(
            self.theme, (BOARD.centerx, BOARD.centery + 60), items, accent=ACCENT
        )

    def _close_dialog(self) -> None:
        self.dialog = "none"
        self.menu = None

    def handle_event(self, event: pygame.event.Event) -> None:
        if self.menu is not None:
            self.menu.handle_event(event)
            return
        if self.new_btn.handle_event(event):
            return
        action = action_of(event)
        if action in SLIDES:
            self._move(SLIDES[action])
        elif event.type == pygame.KEYDOWN and event.key == pygame.K_n:
            self._new_game()
        elif (
            event.type == pygame.MOUSEBUTTONDOWN
            and event.button == 1
            and BOARD.collidepoint(event.pos)
        ):
            self.drag_start = event.pos
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1 and self.drag_start:
            dx = event.pos[0] - self.drag_start[0]
            dy = event.pos[1] - self.drag_start[1]
            self.drag_start = None
            if max(abs(dx), abs(dy)) >= SWIPE_DISTANCE:
                if abs(dx) > abs(dy):
                    self._move("right" if dx > 0 else "left")
                else:
                    self._move("down" if dy > 0 else "up")

    def _check_achievements(self) -> None:
        self.unlock_milestones(
            self.game.max_tile(), {"tile_512": 512, "tile_1024": 1024, "tile_2048": 2048}
        )

    def update(self, dt: float) -> None:
        self._check_achievements()
        self.anim += dt
        self.new_btn.update(dt)
        if self.menu is not None:
            self.menu.update(dt)

    # ------------------------------------------------------------------ drawing
    def draw(self, surface: Canvas) -> None:
        t = self.theme
        p = t.palette
        surface.fill(p.bg)
        self._draw_side(surface, t)
        board_color = p.surface_hover if t.mode == "light" else p.surface
        empty_color = p.surface if t.mode == "light" else p.surface_alt
        draw.shadow(surface, BOARD, t.radius.lg, p.shadow, (0, 8), 16)
        draw.rounded_rect(surface, BOARD, board_color, t.radius.lg)
        for r in range(SIZE):
            for c in range(SIZE):
                gfx.rect(surface, empty_color, cell_rect((r, c)), border_radius=t.radius.md)

        if self.last is not None and self.anim < SLIDE_SECONDS:
            k = self.anim / SLIDE_SECONDS
            k = 1 - (1 - k) ** 2
            for s in self.last.slides:
                pos = (
                    s.start[0] + (s.end[0] - s.start[0]) * k,
                    s.start[1] + (s.end[1] - s.start[1]) * k,
                )
                self._draw_tile(surface, t, s.value, cell_rect(pos), 1.0)
        else:
            pop_t = (self.anim - SLIDE_SECONDS) / POP_SECONDS
            for r in range(SIZE):
                for c in range(SIZE):
                    value = self.game.grid[r][c]
                    if not value:
                        continue
                    scale = 1.0
                    if self.last is not None and pop_t < 1:
                        if (r, c) in self.last.merged:
                            scale = 1 + 0.14 * math.sin(math.pi * pop_t)
                        elif (r, c) == self.last.spawned:
                            scale = max(0.0, pop_t)
                    self._draw_tile(surface, t, value, cell_rect((r, c)), scale)

        if self.menu is not None:
            self._draw_dialog(surface, t)

    def _draw_tile(
        self, surface: Canvas, t: Theme, value: int, rect: pygame.Rect, scale: float
    ) -> None:
        if scale <= 0.05:
            return
        r = rect.inflate(round(rect.width * (scale - 1)), round(rect.height * (scale - 1)))
        color = tile_color(value)
        gfx.rect(surface, color, r, border_radius=t.radius.md)
        if t.mode == "light":  # pale tiles need an edge against the light board
            outline = lerp_color(color, (15, 23, 42), 0.15)
            gfx.rect(surface, outline, r, 2, border_radius=t.radius.md)
        digits = len(str(value))
        size = {1: 56, 2: 52, 3: 44, 4: 36}.get(digits, 28)
        fg = DARK_TEXT if value <= 4 else readable_on(color)
        draw.text(surface, str(value), t.font(round(size * scale), "bold"), fg, r.center, "center")

    def _draw_side(self, surface: Canvas, t: Theme) -> None:
        p = t.palette
        draw.text(surface, "2048", t.font(64, "bold"), ACCENT, (SIDE_X, BOARD.y - 8))
        draw.text(
            surface,
            "Join the tiles, get to 2048!",
            t.font(t.size.label),
            p.text_muted,
            (SIDE_X, BOARD.y + 76),
        )
        best = self.best_score()
        best_value = max(self.game.score, int(best.score) if best else 0)
        for i, (label, value) in enumerate((("SCORE", self.game.score), ("BEST", best_value))):
            box = pygame.Rect(SIDE_X + i * 156, BOARD.y + 120, 144, 76)
            draw.rounded_rect(surface, box, p.surface_alt, t.radius.md)
            draw.text(
                surface,
                label,
                t.font(t.size.caption, "semibold"),
                p.text_muted,
                (box.centerx, box.y + 12),
                "midtop",
            )
            draw.text(
                surface,
                f"{value:,}",
                t.font(t.size.title, "bold"),
                p.text,
                (box.centerx, box.y + 34),
                "midtop",
            )
        self.new_btn.draw(surface)
        lines = [
            "Arrows / WASD, a gamepad or drag to slide.",
            "Tiles with the same number merge.",
            "N starts a new game.",
        ]
        for i, text in enumerate(lines):
            draw.text(surface, text, t.font(t.size.label), p.text_muted, (SIDE_X, 420 + i * 26))

    def _draw_dialog(self, surface: Canvas, t: Theme) -> None:
        assert self.menu is not None
        p = t.palette
        layer = Canvas.new(BOARD.size, alpha=True)
        gfx.rect(layer, (*p.bg, 200), layer.get_rect(), border_radius=t.radius.lg)
        surface.blit(layer, BOARD.topleft)
        if self.dialog == "won":
            title, sub, color = f"You made {GOAL}!", "Keep going for a higher score?", ACCENT
        else:
            title = "No more moves"
            sub = "New high score!" if self.new_best else f"Score {self.game.score:,}"
            color = p.success if self.new_best else p.text_muted
        panel = pygame.Rect(0, 0, 380, self.menu.rect.height + 150)
        panel.midbottom = (BOARD.centerx, self.menu.rect.bottom + 32)
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
            t.font(t.size.label, "semibold"),
            color,
            (panel.centerx, panel.y + 76),
            "midtop",
        )
        self.menu.draw(surface)


# ---------------------------------------------------------------------- persistence
def _serialize(game: Game2048) -> dict[str, Any]:
    return {"grid": game.grid, "score": game.score, "won": game.won}


def _deserialize(data: dict[str, Any]) -> Game2048 | None:
    try:
        grid = [[int(v) for v in row] for row in data["grid"]]
        if len(grid) != SIZE or any(len(row) != SIZE for row in grid):
            return None
        game = Game2048(random.Random(), grid, int(data["score"]), bool(data.get("won", False)))
    except (KeyError, TypeError, ValueError):
        return None
    game.over = not game.can_move()
    return game
