"""Hangman UI: a chalk-style gallows sketch, letter slots and an on-screen keyboard."""

from __future__ import annotations

import random

import pygame

from apps.hangman.logic import MAX_MISSES, Hangman, load_words, pick_word
from core import draw, gfx
from core.base_app import BaseApp
from core.canvas import Canvas
from core.registry import register_app
from core.theme import Color, Theme, lerp_color
from core.widgets import Button

ACCENT: Color = (132, 204, 22)
BOARD = pygame.Rect(80, 100, 400, 500)
RIGHT_X = 540
RIGHT_W = 660
KEY_ROWS = ("qwertyuiop", "asdfghjkl", "zxcvbnm")
KEY = 52
KEY_GAP = 8
KEYS_Y = 360
RECENT = 40


def key_rect(letter: str) -> pygame.Rect:
    for r, row in enumerate(KEY_ROWS):
        if letter in row:
            width = len(row) * KEY + (len(row) - 1) * KEY_GAP
            x = RIGHT_X + (RIGHT_W - width) // 2 + row.index(letter) * (KEY + KEY_GAP)
            return pygame.Rect(x, KEYS_Y + r * (KEY + KEY_GAP), KEY, KEY)
    raise ValueError(letter)


@register_app
class HangmanApp(BaseApp):
    """Guess the word one letter at a time before the drawing is finished."""

    @classmethod
    def draw_icon(cls, surface: Canvas, rect: pygame.Rect, theme: Theme) -> None:
        draw.rounded_rect(surface, rect, (26, 46, 5), theme.radius.md)
        u = rect.width / 10
        chalk = (217, 249, 157)
        x0, y0 = rect.x, rect.y
        gfx.line(surface, chalk, (x0 + 2 * u, y0 + 8.4 * u), (x0 + 6 * u, y0 + 8.4 * u), 3)
        gfx.line(surface, chalk, (x0 + 3 * u, y0 + 8.4 * u), (x0 + 3 * u, y0 + 1.8 * u), 3)
        gfx.line(surface, chalk, (x0 + 3 * u, y0 + 1.8 * u), (x0 + 6.6 * u, y0 + 1.8 * u), 3)
        gfx.line(surface, chalk, (x0 + 6.6 * u, y0 + 1.8 * u), (x0 + 6.6 * u, y0 + 3 * u), 3)
        gfx.circle(surface, ACCENT, (x0 + 6.6 * u, y0 + 3.9 * u), 0.9 * u, 3)
        font = theme.font(round(u * 1.6), "bold")
        draw.text(surface, "A _ _", font, chalk, (x0 + 5.2 * u, y0 + 6.6 * u), "center")

    # ------------------------------------------------------------------ lifecycle
    def on_enter(self) -> None:
        self.categories = load_words()
        self.rng = random.Random()
        t = self.theme
        self.hint_button = Button(t, (RIGHT_X, 560, 160, 44), "Hint (costs 1)", self._hint)
        self.next_button = Button(
            t,
            (RIGHT_X + RIGHT_W - 180, 560, 180, 44),
            "Next word",
            self._next,
            "primary",
            accent=ACCENT,
        )
        self.time = 0.0
        self._next()

    def on_exit(self) -> None:
        self.data.save()

    def restart(self) -> None:
        self.data["streak"] = 0
        self._next()

    def uses_text_input(self) -> bool:
        return not self.game.over  # letters are guesses, never "WASD" actions

    @property
    def streak(self) -> int:
        return int(self.data.get("streak", 0))

    def _next(self) -> None:
        recent: list[str] = list(self.data.get("recent", []))
        category, word = pick_word(self.categories, self.rng, recent)
        self.data["recent"] = [*recent, word][-RECENT:]
        self.game = Hangman(word, category)
        self.shake = 0.0
        self.round_end_handled = False

    # ------------------------------------------------------------------ actions
    def _guess(self, letter: str) -> None:
        if self.game.guess(letter) == "miss":
            self.shake = 0.3
        self._after_move()

    def _hint(self) -> None:
        if self.game.hint(self.rng) is not None:
            self.shake = 0.3
        self._after_move()

    def _after_move(self) -> None:
        g = self.game
        if not g.over or self.round_end_handled:
            return
        self.round_end_handled = True
        if g.won:
            streak = self.streak + 1
            self.data["streak"] = streak
            self.submit_score(streak)
            self.unlock("first_win")
            if g.miss_count == 0:
                self.unlock("flawless")
            self.unlock_milestones(streak, {"streak_5": 5})
            won = set(self.data.get("won_categories", [])) | {g.category}
            self.data["won_categories"] = sorted(won)
            if won >= set(self.categories):
                self.unlock("all_categories")
        else:
            self.data["streak"] = 0
        self.data.save()

    # ------------------------------------------------------------------ events
    def handle_event(self, event: pygame.event.Event) -> None:
        g = self.game
        if g.over:
            if self.next_button.handle_event(event):
                return
            if event.type == pygame.KEYDOWN and event.key in (
                pygame.K_RETURN,
                pygame.K_KP_ENTER,
                pygame.K_SPACE,
            ):
                self._next()
            return
        if self.hint_button.handle_event(event):
            return
        if event.type == pygame.KEYDOWN:
            typed = getattr(event, "unicode", "")
            if typed == "?":
                self._hint()
            elif typed and typed.isascii() and typed.isalpha():
                self._guess(typed)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for row in KEY_ROWS:
                for letter in row:
                    if key_rect(letter).collidepoint(event.pos):
                        self._guess(letter)
                        return

    def update(self, dt: float) -> None:
        self.time += dt
        self.shake = max(0.0, self.shake - dt)
        self.hint_button.enabled = self.game.can_hint
        self.hint_button.update(dt)
        self.next_button.update(dt)

    # ------------------------------------------------------------------ drawing
    def draw(self, surface: Canvas) -> None:
        t = self.theme
        p = t.palette
        surface.fill(p.bg)
        self._draw_board(surface, t)
        self._draw_word(surface, t)
        self._draw_keys(surface, t)
        g = self.game
        if g.over:
            self.next_button.draw(surface)
            msg = "Solved!" if g.won else "Out of guesses"
            color = p.success if g.won else p.danger
            draw.text(surface, msg, t.font(t.size.title, "bold"), color, (RIGHT_X, 566))
        else:
            self.hint_button.draw(surface)
            left = MAX_MISSES - g.miss_count
            draw.text(
                surface,
                f"{left} miss{'es' if left != 1 else ''} left · type or click letters · ? hint",
                t.font(t.size.caption),
                p.text_muted,
                (RIGHT_X + RIGHT_W, 582),
                "midright",
            )

    def _draw_board(self, surface: Canvas, t: Theme) -> None:
        p = t.palette
        g = self.game
        board = (36, 52, 34) if t.mode == "dark" else (54, 83, 52)
        draw.shadow(surface, BOARD, t.radius.lg, p.shadow, (0, 8), 16)
        draw.rounded_rect(surface, BOARD, board, t.radius.lg)
        chalk: Color = (226, 232, 220)
        dim = lerp_color(board, chalk, 0.5)
        x, y = BOARD.x, BOARD.y
        for a, b in (
            ((60, 440), (260, 440)),
            ((110, 440), (110, 70)),
            ((110, 70), (270, 70)),
            ((110, 130), (170, 70)),
            ((270, 70), (270, 120)),
        ):
            gfx.line(surface, dim, (x + a[0], y + a[1]), (x + b[0], y + b[1]), 6)
        figure = (
            lerp_color(chalk, (34, 197, 94), 0.6)
            if g.won
            else lerp_color(chalk, (239, 68, 68), 0.6)
            if g.lost
            else chalk
        )
        dx = round(6 * self.shake / 0.3) * (1 if int(self.time * 40) % 2 else -1)
        hx, hy = x + 270 + dx, y + 152
        # One part per miss: the head, then body, arms and legs as (start, end) offsets.
        if g.miss_count:
            gfx.circle(surface, figure, (hx, hy), 32, 5)
        limbs = (
            ((0, 32), (0, 150)),
            ((0, 60), (-50, 110)),
            ((0, 60), (50, 110)),
            ((0, 150), (-44, 225)),
            ((0, 150), (44, 225)),
        )
        for (ax, ay), (bx, by) in limbs[: max(0, g.miss_count - 1)]:
            gfx.line(surface, figure, (hx + ax, hy + ay), (hx + bx, hy + by), 5)
        # Missed letters, chalked under the drawing.
        misses = " ".join(g.misses).upper() or "—"
        draw.text(
            surface,
            misses,
            t.font(t.size.title, "bold"),
            lerp_color(board, chalk, 0.75),
            (BOARD.centerx, BOARD.bottom - 24),
            "midbottom",
        )

    def _draw_word(self, surface: Canvas, t: Theme) -> None:
        p = t.palette
        g = self.game
        draw.text(surface, "Hangman", t.font(t.size.heading, "bold"), p.text, (RIGHT_X, 100))
        best = self.best_score()
        info = f"Streak {self.streak} · Best {best.score:.0f}" if best else f"Streak {self.streak}"
        draw.text(
            surface,
            info,
            t.font(t.size.label, "semibold"),
            p.text_muted,
            (RIGHT_X + RIGHT_W, 112),
            "topright",
        )
        chip_font = t.font(t.size.caption, "semibold")
        label = g.category.upper()
        chip = pygame.Rect(RIGHT_X, 152, chip_font.size(label)[0] + 24, 28)
        draw.rounded_rect(surface, chip, lerp_color(p.bg, ACCENT, 0.25), 14)
        draw.text(surface, label, chip_font, ACCENT, chip.center, "center")

        masked = g.masked()
        slot = min(56, RIGHT_W // max(1, len(masked)))
        font = t.font(min(44, slot - 8), "bold")
        x0 = RIGHT_X + (RIGHT_W - slot * len(masked)) / 2
        base_y = 286
        for i, (ch, shown) in enumerate(zip(g.word, masked, strict=True)):
            cx = x0 + i * slot + slot / 2
            if ch == " ":
                continue
            if ch != "-":
                gfx.line(
                    surface, p.border, (cx - slot * 0.36, base_y), (cx + slot * 0.36, base_y), 3
                )
            if shown is not None:
                color = ACCENT if ch in g.hinted else p.text
                draw.text(surface, ch.upper(), font, color, (cx, base_y - 6), "midbottom")
            elif g.lost:
                draw.text(surface, ch.upper(), font, p.danger, (cx, base_y - 6), "midbottom")

    def _draw_keys(self, surface: Canvas, t: Theme) -> None:
        p = t.palette
        g = self.game
        font = t.font(t.size.title, "bold")
        for row in KEY_ROWS:
            for letter in row:
                rect = key_rect(letter)
                if letter in g.misses:
                    fill, text = lerp_color(p.bg, p.surface_alt, 0.5), p.text_muted
                elif letter in g.hinted:
                    fill, text = lerp_color(p.surface_alt, ACCENT, 0.45), p.text
                elif letter in g.guessed:
                    fill, text = lerp_color(p.surface_alt, p.success, 0.55), p.text
                else:
                    fill, text = p.surface_alt, p.text
                draw.rounded_rect(surface, rect, fill, 10)
                draw.text(surface, letter.upper(), font, text, rect.center, "center")
        if g.over:
            panel = pygame.Rect(RIGHT_X, KEYS_Y - 8, RIGHT_W, 3 * (KEY + KEY_GAP) + 8)
            draw.rounded_rect(surface, panel, (*p.bg, 150), 12)
