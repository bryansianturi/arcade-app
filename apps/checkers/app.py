"""Checkers UI: a wooden board, animated jumps, capture hints and a computer opponent."""

from __future__ import annotations

import random
import threading
from typing import Literal

import pygame

from apps.checkers.logic import (
    Checkers,
    Move,
    Side,
    Square,
    choose_move,
    is_king,
    opponent,
    side_of,
)
from core import draw, gfx
from core.base_app import BaseApp
from core.canvas import Canvas
from core.input import DIRECTION_STEPS, action_of
from core.registry import register_app
from core.theme import Color, Theme, lerp_color
from core.widgets import Button, SegmentedControl, draw_panel

ACCENT: Color = (109, 40, 217)
LIGHT_SQ: Color = (236, 220, 193)
DARK_SQ: Color = (122, 86, 62)
RED: Color = (200, 40, 48)
WHITE: Color = (244, 244, 240)
HINT: Color = (250, 204, 21)
NAMES: dict[Side, str] = {"dark": "Red", "light": "White"}

SQ = 76
BOARD = pygame.Rect(72, 56, SQ * 8, SQ * 8)
PANEL = pygame.Rect(BOARD.right + 48, 56, 1280 - 48 - BOARD.right - 48, SQ * 8)
HOP_SECONDS = 0.16
CPU_MIN_SECONDS = 0.45

Level = Literal["easy", "medium", "hard"]
LEVELS: tuple[Level, ...] = ("easy", "medium", "hard")
#: (search depth, time limit, chance of a random move)
LEVEL_SETTINGS: dict[Level, tuple[int, float, float]] = {
    "easy": (2, 1.0, 0.3),
    "medium": (4, 2.0, 0.0),
    "hard": (8, 3.0, 0.0),
}


@register_app
class CheckersApp(BaseApp):
    """English draughts for two players or against the computer."""

    @classmethod
    def draw_icon(cls, surface: Canvas, rect: pygame.Rect, theme: Theme) -> None:
        draw.rounded_rect(surface, rect, DARK_SQ, theme.radius.md)
        half = rect.width // 2
        clip = surface.get_clip()
        surface.set_clip(rect)
        for dx, dy in ((0, 0), (half, half)):
            gfx.rect(surface, LIGHT_SQ, (rect.x + dx, rect.y + dy, half, half))
        surface.set_clip(clip)
        draw.rounded_rect(surface, rect, DARK_SQ, theme.radius.md, 2)
        draw_disc(
            surface, (rect.x + half * 0.55, rect.y + half * 1.45), rect.width * 0.2, RED, king=True
        )
        draw_disc(surface, (rect.x + half * 1.45, rect.y + half * 0.55), rect.width * 0.2, WHITE)

    # ------------------------------------------------------------------ lifecycle
    def on_enter(self) -> None:
        d = self.data
        self.vs_cpu = bool(d.get("vs_cpu", True))
        level = d.get("level", "medium")
        self.level: Level = level if level in LEVELS else "medium"
        self.human: Side = "light" if d.get("human") == "light" else "dark"
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
            ["Play Red (first)", "Play White"],
            int(self.human == "light"),
            self._set_side,
        )
        bw = (w - 12) // 2
        y = PANEL.bottom - 44
        self.buttons = [
            Button(t, (x, y, bw, 44), "Undo", self._undo),
            Button(
                t, (x + bw + 12, y, bw, 44), "New game", self._new_game, "primary", accent=ACCENT
            ),
        ]
        self.time = 0.0
        self.cursor: Square = (5, 0)
        self.keyboard = False
        self._generation = 0
        self._new_game(save=False)
        saved = d.get("board")
        if (
            isinstance(saved, list)
            and len(saved) == 8
            and all(isinstance(r, str) and len(r) == 8 for r in saved)
        ):
            self.game.board = [list(row) for row in saved]
            self.game.turn = "light" if d.get("turn") == "light" else "dark"
            quiet = d.get("quiet", 0)
            self.game.quiet_plies = quiet if isinstance(quiet, int) else 0
        self._maybe_think()

    def _new_game(self, save: bool = True) -> None:
        self.game = Checkers()
        self.selected: Square | None = None
        self.partial: tuple[Square, ...] = ()
        self.anim: tuple[Move, str, float] | None = None  # move, piece, hops done
        self.fading: list[tuple[Square, str]] = []
        self.thinking = False
        self._generation += 1
        self._cpu_move: Move | None = None
        self._think_started = 0.0
        self.recorded = False
        if save:
            self._save()
            self._maybe_think()

    def restart(self) -> None:
        self._new_game()

    def on_exit(self) -> None:
        self._generation += 1
        self._save()

    def _save(self) -> None:
        d = self.data
        finished = self.game.over
        d["board"] = None if finished else ["".join(row) for row in self.game.board]
        d["turn"], d["quiet"] = self.game.turn, self.game.quiet_plies
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
        self.human = "light" if index == 1 else "dark"
        self._new_game()

    @property
    def flipped(self) -> bool:
        return self.vs_cpu and self.human == "light"

    def _undo(self) -> None:
        if self.anim is not None:
            return
        self._generation += 1
        self.thinking = False
        steps = 2 if self.vs_cpu and self.game.turn == self.human else 1
        for _ in range(steps):
            self.game.undo()
        self.recorded = False
        self._deselect()
        self._save()
        self._maybe_think()

    # ------------------------------------------------------------------ moves
    @property
    def human_to_move(self) -> bool:
        return not self.game.over and (not self.vs_cpu or self.game.turn == self.human)

    def _deselect(self) -> None:
        self.selected = None
        self.partial = ()

    def _candidates(self) -> list[Move]:
        return [m for m in self.game.legal_moves() if m.path[: len(self.partial)] == self.partial]

    def next_steps(self) -> set[Square]:
        if not self.partial:
            return set()
        n = len(self.partial)
        return {m.path[n] for m in self._candidates() if len(m.path) > n}

    def movable(self) -> set[Square]:
        return {m.start for m in self.game.legal_moves()}

    def _click(self, sq: Square) -> None:
        if self.anim is not None or not self.human_to_move:
            return
        if self.partial and sq in self.next_steps():
            self.partial = (*self.partial, sq)
            remaining = self._candidates()
            done = [m for m in remaining if m.path == self.partial]
            if done and len(remaining) == len(done):
                self._play(done[0])
            return
        if sq in self.movable():
            self.selected = sq
            self.partial = (sq,)
        else:
            self._deselect()

    def _play(self, move: Move) -> None:
        mover = self.game.turn
        piece = self.game.piece(move.start)
        self.fading = [(sq, self.game.piece(sq)) for sq in move.captures]
        self.game.play(move)
        self.anim = (move, piece, 0.0)
        self._deselect()
        if (not self.vs_cpu or mover == self.human) and len(move.captures) >= 3:
            self.unlock("triple")

    def _after_move(self) -> None:
        if self.game.over and not self.recorded:
            self.recorded = True
            winner = self.game.winner()
            if self.vs_cpu and winner == self.human:
                self.unlock("win")
                if self.level == "hard":
                    self.unlock("win_hard")
        self._save()
        self._maybe_think()

    # ------------------------------------------------------------------ computer
    def _maybe_think(self) -> None:
        if not self.vs_cpu or self.game.over or self.game.turn == self.human or self.thinking:
            return
        self.thinking = True
        self._think_started = self.time
        generation = self._generation
        game = self.game.copy()
        depth, limit, randomness = LEVEL_SETTINGS[self.level]

        def run() -> None:
            move = choose_move(game, depth, limit, random.Random(), randomness)
            if generation == self._generation:
                self._cpu_move = move

        threading.Thread(target=run, daemon=True).start()

    # ------------------------------------------------------------------ geometry
    def square_rect(self, sq: Square) -> pygame.Rect:
        r, c = sq
        if self.flipped:
            r, c = 7 - r, 7 - c
        return pygame.Rect(BOARD.x + c * SQ, BOARD.y + r * SQ, SQ, SQ)

    def square_at(self, pos: tuple[int, int]) -> Square | None:
        if not BOARD.collidepoint(pos):
            return None
        r, c = (pos[1] - BOARD.y) // SQ, (pos[0] - BOARD.x) // SQ
        return (7 - r, 7 - c) if self.flipped else (r, c)

    # ------------------------------------------------------------------ events
    def handle_event(self, event: pygame.event.Event) -> None:
        for widget in (self.mode_picker, self.level_picker, self.side_picker, *self.buttons):
            if widget.handle_event(event):
                return
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self.keyboard = False
            sq = self.square_at(event.pos)
            if sq is not None:
                self._click(sq)
            else:
                self._deselect()
        elif event.type == pygame.KEYDOWN and event.key == pygame.K_u:
            self._undo()
        else:
            action = action_of(event)
            if action is None:
                return
            if not self.keyboard:
                self.keyboard = True
                return
            if action in DIRECTION_STEPS:
                dc, dr = DIRECTION_STEPS[action]
                if self.flipped:
                    dc, dr = -dc, -dr
                self.cursor = (
                    max(0, min(7, self.cursor[0] + dr)),
                    max(0, min(7, self.cursor[1] + dc)),
                )
            elif action == "action" and not event.repeat:
                self._click(self.cursor)

    # ------------------------------------------------------------------ frame
    def update(self, dt: float) -> None:
        self.time += dt
        for widget in (self.mode_picker, self.level_picker, self.side_picker, *self.buttons):
            widget.update(dt)
        self.level_picker.enabled = self.vs_cpu
        self.buttons[0].enabled = self.game.can_undo and self.anim is None
        if self.anim is not None:
            move, piece, hops = self.anim
            hops += dt / HOP_SECONDS
            if hops >= len(move.path) - 1:
                self.anim = None
                self.fading = []
                self._after_move()
            else:
                self.anim = (move, piece, hops)
            return
        reply = self._cpu_move
        if reply is not None and self.time - self._think_started >= CPU_MIN_SECONDS:
            self._cpu_move = None
            self.thinking = False
            if reply in self.game.legal_moves():
                self._play(reply)

    # ------------------------------------------------------------------ drawing
    def draw(self, surface: Canvas) -> None:
        t = self.theme
        surface.fill(t.palette.bg)
        self._draw_board(surface, t)
        self._draw_panel(surface, t)

    def _draw_board(self, surface: Canvas, t: Theme) -> None:
        draw.shadow(surface, BOARD, t.radius.md, t.palette.shadow, (0, 8), 16)
        g = self.game
        hint_starts = (
            self.movable()
            if self.human_to_move and g.must_capture() and self.anim is None
            else set()
        )
        steps = self.next_steps()
        for r in range(8):
            for c in range(8):
                rect = self.square_rect((r, c))
                dark = (r + c) % 2 == 1
                color = DARK_SQ if dark else LIGHT_SQ
                if (r, c) == self.selected or (r, c) in self.partial[1:]:
                    color = lerp_color(color, HINT, 0.45)
                gfx.rect(surface, color, rect)
                if (r, c) in steps:
                    gfx.circle(surface, lerp_color(color, HINT, 0.85), rect.center, SQ * 0.14)
        if self.keyboard:
            draw.rounded_rect(
                surface, self.square_rect(self.cursor).inflate(-4, -4), (59, 130, 246), 6, 4
            )
        moving_to = self.anim[0].end if self.anim is not None else None
        for r in range(8):
            for c in range(8):
                piece = g.board[r][c]
                if piece == "." or (r, c) == moving_to:
                    continue
                center = self.square_rect((r, c)).center
                if (r, c) in hint_starts:
                    gfx.circle(surface, HINT, center, SQ * 0.44, 4)
                draw_disc(
                    surface,
                    center,
                    SQ * 0.38,
                    RED if side_of(piece) == "dark" else WHITE,
                    is_king(piece),
                )
        if self.anim is not None:
            move, piece, hops = self.anim
            for sq, victim in self.fading:  # captured pieces vanish as the jumper passes
                passed = next(i for i, cap in enumerate(move.captures) if cap == sq) + 1
                if hops < passed:
                    color = RED if side_of(victim) == "dark" else WHITE
                    draw_disc(
                        surface, self.square_rect(sq).center, SQ * 0.38, color, is_king(victim)
                    )
            i = min(int(hops), len(move.path) - 2)
            k = hops - i
            a = pygame.Vector2(self.square_rect(move.path[i]).center)
            b = pygame.Vector2(self.square_rect(move.path[i + 1]).center)
            pos = a.lerp(b, k)
            lift = 1 + 0.12 * (1 - abs(2 * k - 1))  # a little hop
            color = RED if side_of(piece) == "dark" else WHITE
            draw_disc(surface, (pos.x, pos.y), SQ * 0.38 * lift, color, is_king(piece))

    def _status(self) -> tuple[str, str]:
        g = self.game
        if g.over:
            winner = g.winner()
            if winner is None:
                return "Draw", "40 moves without progress"
            if self.vs_cpu:
                return (
                    "You win!" if winner == self.human else "Computer wins"
                ), f"{NAMES[winner]} wins"
            return f"{NAMES[winner]} wins", f"{NAMES[opponent(winner)]} has no moves left"
        side = NAMES[g.turn]
        if self.thinking or (self.vs_cpu and g.turn != self.human):
            return "Thinking…", f"{side} (computer) to move"
        if g.must_capture():
            sub = "A capture is available, so you must take it"
        else:
            sub = f"You are {side}" if self.vs_cpu else "Pick a piece to move"
        return ("Your move" if self.vs_cpu else f"{side} to move"), sub

    def _draw_panel(self, surface: Canvas, t: Theme) -> None:
        p = t.palette
        x = PANEL.x
        draw.text(surface, "Checkers", t.font(t.size.heading, "bold"), p.text, (x, PANEL.y - 4))
        title, sub = self._status()
        color = p.success if title == "You win!" else p.text
        draw.text(surface, title, t.font(t.size.title, "semibold"), color, (x, PANEL.y + 44))
        draw.text(surface, sub, t.font(t.size.label), p.text_muted, (x, PANEL.y + 76))
        self.mode_picker.draw(surface)
        self.level_picker.draw(surface)
        self.side_picker.draw(surface)
        card = pygame.Rect(x, PANEL.y + 276, PANEL.width, 150)
        draw_panel(surface, card, t)
        sides: tuple[Side, Side] = ("dark", "light")
        for i, side in enumerate(sides):
            pieces = self.game.pieces(side)
            kings = sum(1 for sq in pieces if is_king(self.game.piece(sq)))
            cy = card.y + 46 + i * 58
            draw_disc(surface, (card.x + 40, cy), 18, RED if side == "dark" else WHITE)
            draw.text(
                surface,
                NAMES[side],
                t.font(t.size.body, "semibold"),
                p.text,
                (card.x + 74, cy),
                "midleft",
            )
            detail = f"{len(pieces)} pieces" + (
                f" · {kings} king{'s' if kings != 1 else ''}" if kings else ""
            )
            draw.text(
                surface,
                detail,
                t.font(t.size.label),
                p.text_muted,
                (card.right - 20, cy),
                "midright",
            )
        hint = "Click a piece, then where to go (one hop at a time for jumps) · U undo"
        draw.text(
            surface,
            draw.fit_text(hint, t.font(t.size.caption), PANEL.width),
            t.font(t.size.caption),
            p.text_muted,
            (x, card.bottom + 16),
        )
        for button in self.buttons:
            button.draw(surface)


def draw_disc(
    surface: Canvas, center: tuple[float, float], radius: float, color: Color, king: bool = False
) -> None:
    """A checker: a shadowed disc with a rim, and a crown for kings."""
    x, y = center
    rim = lerp_color(color, (0, 0, 0), 0.28)
    gfx.circle(surface, (38, 24, 18), (x, y + radius * 0.12), radius)  # shadow
    gfx.circle(surface, rim, (x, y), radius)
    gfx.circle(surface, color, (x, y - radius * 0.06), radius * 0.86)
    gfx.circle(
        surface,
        lerp_color(color, rim, 0.35),
        (x, y - radius * 0.06),
        radius * 0.62,
        max(1.5, radius * 0.07),
    )
    if king:
        s = radius * 0.5
        crown = [
            (x - s, y + s * 0.45),
            (x - s, y - s * 0.35),
            (x - s * 0.5, y + s * 0.05),
            (x, y - s * 0.6),
            (x + s * 0.5, y + s * 0.05),
            (x + s, y - s * 0.35),
            (x + s, y + s * 0.45),
        ]
        gfx.polygon(surface, (250, 204, 21), crown)
