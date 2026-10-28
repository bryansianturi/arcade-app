"""Chess UI: vector pieces, legal-move highlights, history, promotion picker and an AI."""

from __future__ import annotations

import random
from collections.abc import Callable
from typing import Literal

import pygame

from apps.chess.logic import FILES, PROMOTIONS, Move, Position, best_move, color_of
from core import draw, gfx
from core.background import run_in_background
from core.base_app import BaseApp
from core.canvas import Canvas
from core.input import DIRECTION_STEPS, action_of
from core.registry import register_app
from core.theme import Color, Theme, lerp_color
from core.web import think_limit
from core.widgets import Button, SegmentedControl, draw_panel

ACCENT: Color = (146, 64, 14)
LIGHT_SQ: Color = (226, 231, 239)
DARK_SQ: Color = (124, 143, 173)
WHITE_FILL: Color = (250, 250, 249)
WHITE_LINE: Color = (51, 65, 85)
BLACK_FILL: Color = (39, 45, 61)
BLACK_LINE: Color = (203, 213, 225)
SELECT: Color = (250, 204, 21)
CHECK: Color = (239, 68, 68)

SQ = 76
BOARD = pygame.Rect(72, 56, SQ * 8, SQ * 8)
PANEL = pygame.Rect(BOARD.right + 48, 56, 1280 - 48 - BOARD.right - 48, SQ * 8)

Level = Literal["easy", "medium", "hard"]
LEVELS: tuple[Level, ...] = ("easy", "medium", "hard")
#: (search depth, time limit in seconds, chance of a random move)
LEVEL_SETTINGS: dict[Level, tuple[int, float, float]] = {
    "easy": (1, 1.0, 0.3),
    "medium": (3, 2.5, 0.0),
    "hard": (5, 4.0, 0.0),
}
CPU_MIN_SECONDS = 0.45  # the computer never answers instantly (it feels better)


@register_app
class ChessApp(BaseApp):
    """Chess for two players or against the computer."""

    @classmethod
    def draw_icon(cls, surface: Canvas, rect: pygame.Rect, theme: Theme) -> None:
        draw.rounded_rect(surface, rect, ACCENT, theme.radius.md)
        draw_piece(
            surface, "N", (rect.centerx, rect.centery + rect.height * 0.04), rect.height * 0.9
        )

    # ------------------------------------------------------------------ lifecycle
    def on_enter(self) -> None:
        d = self.data
        self.vs_cpu = bool(d.get("vs_cpu", True))
        level = d.get("level", "medium")
        self.level: Level = level if level in LEVELS else "medium"
        self.human: Literal["w", "b"] = "b" if d.get("human") == "b" else "w"
        self.flipped = self.human == "b"
        t = self.theme
        x, w = PANEL.x, PANEL.width
        self.mode_picker = SegmentedControl(
            t,
            (x, PANEL.y + 120, w, 38),
            ["2 players", "vs Computer"],
            int(self.vs_cpu),
            self._set_mode,
        )
        self.level_picker = SegmentedControl(
            t,
            (x, PANEL.y + 168, w, 38),
            ["Easy", "Medium", "Hard"],
            LEVELS.index(self.level),
            self._set_level,
        )
        self.side_picker = SegmentedControl(
            t,
            (x, PANEL.y + 216, w, 38),
            ["Play White", "Play Black"],
            int(self.human == "b"),
            self._set_side,
        )
        bw = (w - 24) // 3
        y = PANEL.bottom - 44
        self.buttons = [
            Button(t, (x, y, bw, 44), "Undo", self._undo),
            Button(t, (x + bw + 12, y, bw, 44), "Flip", self._flip),
            Button(
                t,
                (x + 2 * (bw + 12), y, bw, 44),
                "New game",
                self._new_game,
                "primary",
                accent=ACCENT,
            ),
        ]
        self.time = 0.0
        self.cursor = 12  # e2
        self.keyboard = False
        self._resume_or_new()

    def _resume_or_new(self) -> None:
        saved = self.data.get("moves")
        self._new_game(save=False)
        if isinstance(saved, list) and all(isinstance(u, str) for u in saved):
            try:
                for uci in saved:
                    self._apply(Move.from_uci(uci), think=False)
            except (ValueError, IndexError):
                self._new_game()
        self._maybe_think()

    def _new_game(self, save: bool = True) -> None:
        self.pos = Position.from_fen()
        self.sans: list[str] = []
        self.selected: int | None = None
        self.targets: list[Move] = []
        self.drag: tuple[int, pygame.Vector2] | None = None
        self.promotion: list[Move] = []  # choices while the picker is open
        self.result: tuple[str, str | None] | None = None
        self.thinking = False
        self._generation = getattr(self, "_generation", 0) + 1  # invalidates running searches
        self._cpu_move: Move | None = None
        self._think_started = 0.0
        if save:
            self._save()
            self._maybe_think()

    def on_exit(self) -> None:
        self._generation += 1
        self._save()

    def restart(self) -> None:
        self._new_game()

    def _save(self) -> None:
        d = self.data
        d["moves"] = [m.uci for m in self.pos.history] if self.result is None else []
        d["vs_cpu"], d["level"], d["human"] = self.vs_cpu, self.level, self.human
        d.save()

    # ------------------------------------------------------------------ settings
    def _set_mode(self, index: int) -> None:
        self.vs_cpu = index == 1
        self._save()
        self._maybe_think()

    def _set_level(self, index: int) -> None:
        self.level = LEVELS[index]
        self._save()

    def _set_side(self, index: int) -> None:
        self.human = "b" if index == 1 else "w"
        self.flipped = self.human == "b"
        self._new_game()

    def _flip(self) -> None:
        self.flipped = not self.flipped

    def _undo(self) -> None:
        if not self.pos.history:
            return
        self._generation += 1
        self.thinking = False
        # Against the computer, take back its reply as well as your move.
        plies = (
            2 if self.vs_cpu and self.pos.turn == self.human and len(self.pos.history) >= 2 else 1
        )
        for _ in range(plies):
            self.pos.pop()
            self.sans.pop()
        self.result = None
        self._deselect()
        self._save()
        self._maybe_think()

    # ------------------------------------------------------------------ moves
    @property
    def human_to_move(self) -> bool:
        return self.result is None and (not self.vs_cpu or self.pos.turn == self.human)

    def _apply(self, move: Move, think: bool = True) -> None:
        if move not in self.pos.legal_moves():
            raise ValueError(f"illegal move {move.uci}")
        self.sans.append(self.pos.san(move))
        mover = self.pos.turn
        self.pos.push(move)
        if move.promotion and (not self.vs_cpu or mover == self.human):
            self.unlock("promote")
        self._deselect()
        outcome = self.pos.outcome()
        if outcome is not None:
            self.result = outcome
            self._on_game_over()
        if think:
            self._save()
            self._maybe_think()

    def _on_game_over(self) -> None:
        assert self.result is not None
        winner = self.result[1]
        if self.vs_cpu and winner == self.human:
            self.unlock("win")
            if self.level == "hard":
                self.unlock("win_hard")

    def _deselect(self) -> None:
        self.selected = None
        self.targets = []
        self.promotion = []

    def _select(self, sq: int) -> None:
        piece = self.pos.board[sq]
        if piece != "." and color_of(piece) == self.pos.turn and self.human_to_move:
            self.selected = sq
            self.targets = self.pos.legal_from(sq)
        else:
            self._deselect()

    def _click_square(self, sq: int) -> None:
        """Select a piece, or move the selected piece to ``sq``."""
        if self.promotion or not self.human_to_move:
            return
        if self.selected is not None:
            options = [m for m in self.targets if m.end == sq]
            if len(options) == 1:
                self._apply(options[0])
                return
            if len(options) > 1:  # promotion: let the player choose the piece
                self.promotion = sorted(options, key=lambda m: PROMOTIONS.index(m.promotion))
                return
        self._select(sq)

    # ------------------------------------------------------------------ computer
    def _maybe_think(self) -> None:
        if (
            not self.vs_cpu
            or self.result is not None
            or self.pos.turn == self.human
            or self.thinking
        ):
            return
        self.thinking = True
        self._think_started = self.time
        generation = self._generation
        position = self.pos.copy()
        position._keys = list(self.pos._keys)
        depth, limit, blunder = LEVEL_SETTINGS[self.level]
        limit = think_limit(limit)
        rng = random.Random()

        def run() -> None:
            moves = position.legal_moves()
            if moves and rng.random() < blunder:
                move: Move | None = rng.choice(moves)
            else:
                move = best_move(position, depth, limit)
            if generation == self._generation:
                self._cpu_move = move

        run_in_background(run)

    # ------------------------------------------------------------------ geometry
    def square_rect(self, sq: int) -> pygame.Rect:
        f, r = sq % 8, sq // 8
        col, row = (7 - f, r) if self.flipped else (f, 7 - r)
        return pygame.Rect(BOARD.x + col * SQ, BOARD.y + row * SQ, SQ, SQ)

    def square_at(self, pos: tuple[int, int]) -> int | None:
        if not BOARD.collidepoint(pos):
            return None
        col, row = (pos[0] - BOARD.x) // SQ, (pos[1] - BOARD.y) // SQ
        f, r = (7 - col, row) if self.flipped else (col, 7 - row)
        return r * 8 + f

    def _promotion_rects(self) -> list[pygame.Rect]:
        if not self.promotion:
            return []
        target = self.square_rect(self.promotion[0].end)
        down = target.y < BOARD.centery
        return [target.move(0, (i if down else -i) * SQ) for i in range(len(self.promotion))]

    # ------------------------------------------------------------------ events
    def captures_pause(self) -> bool:
        return bool(self.promotion)  # Esc closes the promotion picker

    def handle_event(self, event: pygame.event.Event) -> None:
        for widget in (self.mode_picker, self.level_picker, self.side_picker, *self.buttons):
            if widget.handle_event(event):
                return
        if self.promotion:
            self._handle_promotion(event)
            return
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self.keyboard = False
            sq = self.square_at(event.pos)
            if sq is None:
                self._deselect()
                return
            before = self.selected
            self._click_square(sq)
            if self.selected == sq and self.selected is not None:
                self.drag = (sq, pygame.Vector2(event.pos))
            elif before == sq:
                self._deselect()
        elif event.type == pygame.MOUSEMOTION and self.drag is not None:
            self.drag = (self.drag[0], pygame.Vector2(event.pos))
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1 and self.drag is not None:
            start, _ = self.drag
            self.drag = None
            sq = self.square_at(event.pos)
            if sq is not None and sq != start:
                self._click_square(sq)
        elif event.type == pygame.KEYDOWN and event.key == pygame.K_u:
            self._undo()
        elif event.type == pygame.KEYDOWN and event.key == pygame.K_f:
            self._flip()
        else:
            self._handle_action(event)

    def _handle_action(self, event: pygame.event.Event) -> None:
        action = action_of(event)
        if action is None:
            return
        if not self.keyboard:
            self.keyboard = True
            return
        if action in DIRECTION_STEPS:
            dx, dy = DIRECTION_STEPS[action]
            if self.flipped:
                dx, dy = -dx, -dy
            f = max(0, min(7, self.cursor % 8 + dx))
            r = max(0, min(7, self.cursor // 8 - dy))
            self.cursor = r * 8 + f
        elif action == "action" and not event.repeat:
            self._click_square(self.cursor)

    def _handle_promotion(self, event: pygame.event.Event) -> None:
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for move, rect in zip(self.promotion, self._promotion_rects(), strict=True):
                if rect.collidepoint(event.pos):
                    self._apply(move)
                    return
            self.promotion = []
        elif event.type == pygame.KEYDOWN and event.key in (
            pygame.K_q,
            pygame.K_r,
            pygame.K_b,
            pygame.K_n,
        ):
            letter = pygame.key.name(event.key)
            self._apply(next(m for m in self.promotion if m.promotion == letter))
        elif action_of(event) in ("pause", "action"):
            if action_of(event) == "action":
                self._apply(self.promotion[0])  # queen
            else:
                self.promotion = []

    # ------------------------------------------------------------------ frame
    def update(self, dt: float) -> None:
        self.time += dt
        for widget in (self.mode_picker, self.level_picker, self.side_picker, *self.buttons):
            widget.update(dt)
        self.level_picker.enabled = self.vs_cpu
        self.buttons[0].enabled = bool(self.pos.history)
        move = self._cpu_move
        if move is not None and self.time - self._think_started >= CPU_MIN_SECONDS:
            self._cpu_move = None
            self.thinking = False
            if move in self.pos.legal_moves():
                self._apply(move)

    # ------------------------------------------------------------------ drawing
    def draw(self, surface: Canvas) -> None:
        t = self.theme
        surface.fill(t.palette.bg)
        self._draw_board(surface, t)
        self._draw_panel(surface, t)

    def _draw_board(self, surface: Canvas, t: Theme) -> None:
        draw.shadow(surface, BOARD, t.radius.md, t.palette.shadow, (0, 8), 16)
        clip = surface.get_clip()
        board = pygame.Rect(BOARD)
        draw.rounded_rect(surface, board, DARK_SQ, t.radius.md)
        surface.set_clip(board)
        last = self.pos.history[-1] if self.pos.history else None
        check = self.pos.king_square(self.pos.turn) if self.pos.in_check() else None
        coord_font = t.font(t.size.caption, "semibold")
        for sq in range(64):
            rect = self.square_rect(sq)
            light = (sq % 8 + sq // 8) % 2 == 1
            color = LIGHT_SQ if light else DARK_SQ
            if last is not None and sq in (last.start, last.end):
                color = lerp_color(color, SELECT, 0.38)
            if sq == self.selected:
                color = lerp_color(color, SELECT, 0.6)
            gfx.rect(surface, color, rect)
            if sq == check:
                gfx.circle(surface, lerp_color(color, CHECK, 0.75), rect.center, SQ * 0.48)
            ink = DARK_SQ if light else LIGHT_SQ
            if rect.left == BOARD.left:
                draw.text(surface, str(sq // 8 + 1), coord_font, ink, (rect.x + 4, rect.y + 3))
            if rect.bottom == BOARD.bottom:
                draw.text(
                    surface,
                    FILES[sq % 8],
                    coord_font,
                    ink,
                    (rect.right - 4, rect.bottom - 2),
                    "bottomright",
                )
        for move in self.targets:
            rect = self.square_rect(move.end)
            light = (move.end % 8 + move.end // 8) % 2 == 1
            mark = lerp_color(LIGHT_SQ if light else DARK_SQ, (30, 41, 59), 0.35)
            capture = self.pos.board[move.end] != "." or (
                self.pos.board[move.start] in "Pp" and move.end == self.pos.ep
            )
            if capture:  # a ring around the piece that can be taken
                gfx.circle(surface, mark, rect.center, SQ * 0.47, 5)
            else:
                gfx.circle(surface, mark, rect.center, SQ * 0.15)
        if self.keyboard:
            draw.rounded_rect(
                surface, self.square_rect(self.cursor).inflate(-4, -4), (59, 130, 246), 6, 4
            )
        dragged = self.drag[0] if self.drag is not None else None
        for sq, piece in enumerate(self.pos.board):
            if piece != "." and sq != dragged:
                draw_piece(surface, piece, self.square_rect(sq).center, SQ)
        surface.set_clip(clip)
        if self.drag is not None:
            sq, pos = self.drag
            draw_piece(surface, self.pos.board[sq], (pos.x, pos.y), SQ * 1.1)
        if self.promotion:
            self._draw_promotion(surface, t)

    def _draw_promotion(self, surface: Canvas, t: Theme) -> None:
        draw.overlay(surface, t.palette.overlay)
        rects = self._promotion_rects()
        frame = rects[0].unionall(rects[1:]).inflate(10, 10)
        draw_panel(surface, frame, t)
        for move, rect in zip(self.promotion, rects, strict=True):
            piece = move.promotion.upper() if self.pos.turn == "w" else move.promotion
            draw_piece(surface, piece, rect.center, SQ)

    def _status(self) -> tuple[str, str]:
        if self.result is not None:
            reason, winner = self.result
            if winner is None:
                return "Draw", reason.capitalize()
            name = "White" if winner == "w" else "Black"
            if self.vs_cpu:
                return (
                    "You win!" if winner == self.human else "Computer wins"
                ), f"{reason.capitalize()} · {name}"
            return f"{name} wins", reason.capitalize()
        side = "White" if self.pos.turn == "w" else "Black"
        if self.thinking:
            return "Thinking…", f"{side} (computer) to move"
        check = " · check!" if self.pos.in_check() else ""
        who = "Your move" if self.vs_cpu else f"{side} to move"
        return who, f"{side} to move{check}" if self.vs_cpu else f"Move {self.pos.fullmove}{check}"

    def _draw_panel(self, surface: Canvas, t: Theme) -> None:
        p = t.palette
        x = PANEL.x
        draw.text(surface, "Chess", t.font(t.size.heading, "bold"), p.text, (x, PANEL.y - 4))
        title, sub = self._status()
        color = p.success if title == "You win!" else ACCENT if self.result else p.text
        draw.text(surface, title, t.font(t.size.title, "semibold"), color, (x, PANEL.y + 44))
        draw.text(surface, sub, t.font(t.size.label), p.text_muted, (x, PANEL.y + 76))
        self.mode_picker.draw(surface)
        self.level_picker.draw(surface)
        self.side_picker.draw(surface)
        history = pygame.Rect(x, PANEL.y + 270, PANEL.width, PANEL.bottom - 60 - (PANEL.y + 270))
        draw_panel(surface, history, t)
        font = t.font(t.size.label, "medium")
        rows = [(i // 2 + 1, self.sans[i : i + 2]) for i in range(0, len(self.sans), 2)]
        visible = max(1, (history.height - 24) // 26)
        cols = 2 if len(rows) > visible else 1
        per_col = visible
        shown = rows[-visible * cols :]
        for k, (number, pair) in enumerate(shown):
            col, row = divmod(k, per_col)
            cx = history.x + 16 + col * (history.width // 2)
            y = history.y + 12 + row * 26
            draw.text(surface, f"{number}.", font, p.text_muted, (cx, y))
            for j, san in enumerate(pair):
                draw.text(surface, san, font, p.text, (cx + 44 + j * 76, y))
        if not rows:
            draw.text(
                surface,
                "Moves appear here",
                t.font(t.size.label),
                p.text_muted,
                history.center,
                "center",
            )
        for button in self.buttons:
            button.draw(surface)


# ---------------------------------------------------------------------- pieces
def draw_piece(surface: Canvas, piece: str, center: tuple[float, float], size: float) -> None:
    """Vector chess pieces drawn in a ``size`` × ``size`` box."""
    white = piece.isupper()
    fill, line = (WHITE_FILL, WHITE_LINE) if white else (BLACK_FILL, BLACK_LINE)
    cx, cy = center
    u = size / 100
    w = max(1.5, size / 38)

    def pt(x: float, y: float) -> tuple[float, float]:
        return cx + x * u, cy + y * u

    def poly(points: list[tuple[float, float]]) -> None:
        pts = [pt(x, y) for x, y in points]
        gfx.polygon(surface, fill, pts)
        gfx.polygon(surface, line, pts, w)

    def circle(x: float, y: float, r: float) -> None:
        gfx.circle(surface, fill, pt(x, y), r * u)
        gfx.circle(surface, line, pt(x, y), r * u, w)

    def rect(x0: float, y0: float, x1: float, y1: float, radius: float = 0) -> None:
        r = pygame.FRect(cx + x0 * u, cy + y0 * u, (x1 - x0) * u, (y1 - y0) * u)
        gfx.rect(surface, fill, r, border_radius=radius * u)
        gfx.rect(surface, line, r, w, border_radius=radius * u)

    kind = piece.upper()
    shapes: dict[str, Callable[[], None]] = {}

    def pawn() -> None:
        poly([(-20, 30), (20, 30), (9, 2), (-9, 2)])
        rect(-15, -2, 15, 6, 3)
        circle(0, -14, 14)

    def rook() -> None:
        poly([(-19, 30), (19, 30), (15, -14), (-15, -14)])
        poly(
            [
                (-25, -14),
                (25, -14),
                (25, -34),
                (15, -34),
                (15, -26),
                (5, -26),
                (5, -34),
                (-5, -34),
                (-5, -26),
                (-15, -26),
                (-15, -34),
                (-25, -34),
            ]
        )

    def knight() -> None:
        poly(
            [
                (24, 30),
                (-18, 30),
                (-12, 14),
                (2, 0),
                (-12, -4),
                (-26, -10),
                (-30, -18),
                (-20, -28),
                (-4, -34),
                (2, -44),
                (8, -34),
                (20, -22),
                (26, 0),
            ]
        )
        gfx.circle(surface, line, pt(-8, -20), max(1.5, 3.5 * u))

    def bishop() -> None:
        poly([(-17, 30), (17, 30), (8, 0), (-8, 0)])
        rect(-14, -4, 14, 4, 3)
        poly([(0, -42), (13, -24), (12, -10), (0, -4), (-12, -10), (-13, -24)])
        gfx.line(surface, line, pt(-3, -26), pt(6, -16), w)
        circle(0, -44, 4)

    def queen() -> None:
        poly([(-20, 30), (20, 30), (12, -4), (-12, -4)])
        poly([(-22, -4), (22, -4), (28, -32), (13, -16), (0, -38), (-13, -16), (-28, -32)])
        for x, y in ((-28, -34), (0, -40), (28, -34)):
            circle(x, y, 5)

    def king() -> None:
        poly([(-20, 30), (20, 30), (13, -6), (-13, -6)])
        rect(-19, -24, 19, -6, 8)
        rect(-3.5, -46, 3.5, -24, 1)
        rect(-11, -40, 11, -33, 1)

    shapes.update(P=pawn, R=rook, N=knight, B=bishop, Q=queen, K=king)
    rect(-28, 30, 28, 40, 4)  # base
    shapes[kind]()
