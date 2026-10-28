"""Five Letters UI: tile grid with flip reveals, on-screen keyboard and stats."""

from __future__ import annotations

import math
import random

import pygame

from apps.five_letters.logic import MAX_GUESSES, WORD_LENGTH, FiveLetters, Mark, Stats
from core import draw, gfx
from core.base_app import BaseApp
from core.canvas import Canvas, mouse_pos
from core.registry import register_app
from core.theme import Color, Theme, lerp_color
from core.widgets import Button, Toggle, draw_panel

ACCENT: Color = (20, 184, 166)
MARK_COLORS: dict[Mark, Color] = {
    "correct": (20, 184, 166),
    "present": (245, 158, 11),
    "absent": (71, 85, 105),
}
TILE, TILE_GAP = 60, 8
GRID_W = WORD_LENGTH * TILE + (WORD_LENGTH - 1) * TILE_GAP
GRID = pygame.Rect(400 - GRID_W // 2, 40, GRID_W, MAX_GUESSES * TILE + (MAX_GUESSES - 1) * TILE_GAP)
KEY_ROWS = ("qwertyuiop", "asdfghjkl", "+zxcvbnm-")  # + = Enter, - = Backspace
KEY_W, KEY_H, KEY_GAP = 50, 56, 7
KEYBOARD_Y = GRID.bottom + 30
SIDE_X = 790
FLIP_SECONDS = 0.28
FLIP_STAGGER = 0.2
SHAKE_SECONDS = 0.4
TOAST_SECONDS = 1.6


@register_app
class FiveLettersApp(BaseApp):
    """Guess the hidden five-letter word in six tries."""

    @classmethod
    def draw_icon(cls, surface: Canvas, rect: pygame.Rect, theme: Theme) -> None:
        draw.rounded_rect(surface, rect, (30, 41, 59), theme.radius.md)
        u = rect.width / 9
        colors = (MARK_COLORS["absent"], MARK_COLORS["present"], MARK_COLORS["correct"])
        for row in range(2):
            for col in range(3):
                color = colors[(row + col) % 3] if row else MARK_COLORS["absent"]
                r = pygame.Rect(
                    rect.x + u * (0.9 + col * 2.6), rect.y + u * (2 + row * 2.8), u * 2.2, u * 2.2
                )
                gfx.rect(surface, color, r, border_radius=3)

    # ------------------------------------------------------------------ lifecycle
    def on_enter(self) -> None:
        self.rng = random.Random()
        self.stats = Stats.from_dict(self.data.get("stats"))
        self.hard = bool(self.data.get("hard", False))
        self.hard_toggle = Toggle(
            self.theme, (SIDE_X + 340 - Toggle.WIDTH, 404), self.hard, self._set_hard
        )
        self.new_btn = Button(
            self.theme,
            (SIDE_X, 560, 340, 52),
            "New word",
            self._new_round,
            "primary",
            accent=ACCENT,
        )
        self.time = 0.0
        self._new_round()

    def _new_round(self) -> None:
        self.game = FiveLetters.random(self.rng, self.hard)
        self.revealed_at: dict[int, float] = {}  # row -> time its flip started
        self.shake_at = -10.0
        self.toast = ""
        self.toast_until = 0.0
        self.recorded = False

    def restart(self) -> None:
        self._new_round()

    def _set_hard(self, value: bool) -> None:
        self.hard = value
        self.data["hard"] = value
        self.data.save()
        if not self.game.history:
            self.game.hard = value  # can switch freely before the first guess
        else:
            self._show_toast("Applies from the next word")

    def _show_toast(self, text: str, seconds: float = TOAST_SECONDS) -> None:
        self.toast = text
        self.toast_until = self.time + seconds

    # ------------------------------------------------------------------ input
    def _press(self, key: str) -> None:
        if self.game.status != "playing" or self._animating():
            if self.game.status != "playing" and key == "+":
                self._new_round()
            return
        if key == "+":
            self._submit()
        elif key == "-":
            self.game.backspace()
        else:
            self.game.type_letter(key)

    def _submit(self) -> None:
        error = self.game.submit()
        if error:
            self.shake_at = self.time
            self._show_toast(error)
            return
        self.revealed_at[len(self.game.history) - 1] = self.time

    def _animating(self) -> bool:
        if not self.revealed_at:
            return False
        last = max(self.revealed_at.values())
        return self.time - last < FLIP_STAGGER * (WORD_LENGTH - 1) + FLIP_SECONDS

    def _key_rects(self) -> list[tuple[str, pygame.Rect]]:
        rects = []
        for r, row in enumerate(KEY_ROWS):
            widths = [KEY_W * 1.5 if k in "+-" else KEY_W for k in row]
            total = sum(widths) + KEY_GAP * (len(row) - 1)
            x = GRID.centerx - total / 2
            for key, w in zip(row, widths, strict=True):
                rects.append(
                    (
                        key,
                        pygame.Rect(round(x), KEYBOARD_Y + r * (KEY_H + KEY_GAP), round(w), KEY_H),
                    )
                )
                x += w + KEY_GAP
        return rects

    def handle_event(self, event: pygame.event.Event) -> None:
        if self.new_btn.handle_event(event) or self.hard_toggle.handle_event(event):
            return
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self._press("+")
            elif event.key == pygame.K_BACKSPACE:
                self._press("-")
            elif event.unicode and event.unicode.isalpha() and event.unicode.isascii():
                self._press(event.unicode.lower())
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for key, rect in self._key_rects():
                if rect.collidepoint(event.pos):
                    self._press(key)

    def update(self, dt: float) -> None:
        self.time += dt
        self.new_btn.update(dt)
        self.hard_toggle.update(dt)
        if self.game.status != "playing" and not self.recorded and not self._animating():
            self._finish()

    def _finish(self) -> None:
        self.recorded = True
        won = self.game.status == "won"
        self.stats.record(won, len(self.game.history))
        self.data["stats"] = self.stats.to_dict()
        self.data.save()
        if won:
            self.submit_score(self.stats.best_streak, "streak")
            praise = ("Genius!", "Brilliant!", "Great!", "Nice!", "Good!", "Phew!")
            self._show_toast(praise[len(self.game.history) - 1], 3)
        else:
            self._show_toast(f"The word was {self.game.answer.upper()}", 30)

    # ------------------------------------------------------------------ drawing
    def draw(self, surface: Canvas) -> None:
        t = self.theme
        surface.fill(t.palette.bg)
        self._draw_grid(surface, t)
        self._draw_keyboard(surface, t)
        self._draw_side(surface, t)
        if self.toast and self.time < self.toast_until:
            font = t.font(t.size.label, "bold")
            w = font.size(self.toast)[0] + 32
            rect = pygame.Rect(0, 0, w, 40)
            rect.center = (GRID.centerx, GRID.y + 2 * (TILE + TILE_GAP) - 4)
            draw.rounded_rect(surface, rect, t.palette.text, t.radius.md)
            draw.text(surface, self.toast, font, t.palette.bg, rect.center, "center")

    def _draw_grid(self, surface: Canvas, t: Theme) -> None:
        p = t.palette
        g = self.game
        font = t.font(32, "bold")
        shake_t = self.time - self.shake_at
        shake = (
            round(math.sin(shake_t * 60) * 8 * (1 - shake_t / SHAKE_SECONDS))
            if shake_t < SHAKE_SECONDS
            else 0
        )
        for row in range(MAX_GUESSES):
            if row < len(g.history):
                word, marks = g.history[row]
            else:
                word = g.current if row == len(g.history) else ""
                marks = None
            dx = shake if row == len(g.history) else 0
            for col in range(WORD_LENGTH):
                rect = pygame.Rect(
                    GRID.x + col * (TILE + TILE_GAP) + dx,
                    GRID.y + row * (TILE + TILE_GAP),
                    TILE,
                    TILE,
                )
                letter = word[col] if col < len(word) else ""
                fill, border, fg = p.bg, p.border, p.text
                height = 1.0
                if marks is not None:
                    start = self.revealed_at.get(row, -100.0) + col * FLIP_STAGGER
                    k = (self.time - start) / FLIP_SECONDS
                    if k >= 0.5:  # second half of the flip shows the colour
                        fill = border = MARK_COLORS[marks[col]]
                        fg = (255, 255, 255)
                    height = abs(math.cos(min(1.0, max(0.0, k)) * math.pi))
                elif letter:
                    border = p.text_muted
                tile = rect.inflate(0, -round(TILE * (1 - height)))
                if tile.height > 0:
                    gfx.rect(surface, fill, tile, border_radius=6)
                    if fill == p.bg:
                        gfx.rect(surface, border, tile, 2, border_radius=6)
                    if letter and height > 0.3:
                        draw.text(surface, letter.upper(), font, fg, tile.center, "center")

    def _draw_keyboard(self, surface: Canvas, t: Theme) -> None:
        p = t.palette
        # Only colour keys for rows whose flip has finished, so the keyboard doesn't spoil it.
        states = self.game.letter_states() if not self._animating() else self._settled_states()
        mouse = mouse_pos()
        for key, rect in self._key_rects():
            mark = states.get(key)
            fill = MARK_COLORS[mark] if mark else p.surface_hover
            fg = (255, 255, 255) if mark else p.text
            if rect.collidepoint(mouse):
                fill = lerp_color(fill, (255, 255, 255), 0.12)
            gfx.rect(surface, fill, rect, border_radius=6)
            label = {"+": "ENTER", "-": "⌫"}.get(key, key.upper())
            size = t.size.caption if key == "+" else t.size.label
            draw.text(surface, label, t.font(size, "bold"), fg, rect.center, "center")

    def _settled_states(self) -> dict[str, Mark]:
        settled = FiveLetters(self.game.answer, history=self.game.history[:-1])
        return settled.letter_states()

    def _draw_side(self, surface: Canvas, t: Theme) -> None:
        p = t.palette
        s = self.stats
        draw.text(surface, "Five Letters", t.font(t.size.heading, "bold"), p.text, (SIDE_X, 40))
        draw.text(
            surface,
            "Teal = right spot · amber = wrong spot",
            t.font(t.size.caption),
            p.text_muted,
            (SIDE_X, 82),
        )
        panel = pygame.Rect(SIDE_X, 116, 340, 270)
        draw_panel(surface, panel, t)
        for i, (label, value) in enumerate(
            (
                ("Played", s.played),
                ("Win %", s.win_rate),
                ("Streak", s.streak),
                ("Best", s.best_streak),
            )
        ):
            cx = panel.x + 42 + i * 85
            draw.text(
                surface,
                str(value),
                t.font(t.size.heading, "bold"),
                p.text,
                (cx, panel.y + 20),
                "midtop",
            )
            draw.text(
                surface, label, t.font(t.size.caption), p.text_muted, (cx, panel.y + 58), "midtop"
            )
        top = max(1, max(s.distribution))
        for i, count in enumerate(s.distribution):
            y = panel.y + 96 + i * 26
            draw.text(
                surface,
                str(i + 1),
                t.font(t.size.caption, "semibold"),
                p.text_muted,
                (panel.x + 20, y + 10),
                "midleft",
            )
            width = 26 + round(250 * count / top)
            bar = pygame.Rect(panel.x + 38, y, width, 20)
            won_with = (
                self.game.status == "won" and len(self.game.history) == i + 1 and self.recorded
            )
            gfx.rect(surface, ACCENT if won_with else p.surface_hover, bar, border_radius=4)
            draw.text(
                surface,
                str(count),
                t.font(t.size.caption, "bold"),
                (255, 255, 255) if won_with else p.text,
                (bar.right - 8, bar.centery),
                "midright",
            )

        draw.text(surface, "Hard mode", t.font(t.size.body, "semibold"), p.text, (SIDE_X, 406))
        draw.text(
            surface,
            "Revealed hints must be reused",
            t.font(t.size.caption),
            p.text_muted,
            (SIDE_X, 430),
        )
        self.hard_toggle.draw(surface)
        self.new_btn.draw(surface)
        draw.text(
            surface,
            "Type and press Enter · Enter after a round for a new word",
            t.font(t.size.caption),
            p.text_muted,
            (SIDE_X, 626),
        )
