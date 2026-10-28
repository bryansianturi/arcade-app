"""Typing Test UI: a scrolling word stream, live WPM, and a results card with a speed chart."""

from __future__ import annotations

import random

import pygame

from apps.typing_test.logic import DURATIONS, CharState, TypingTest, load_words
from core import draw, gfx
from core.base_app import BaseApp
from core.canvas import Canvas, Font
from core.registry import register_app
from core.theme import Color, Theme, lerp_color, with_alpha
from core.widgets import ButtonMenu, SegmentedControl, draw_panel

ACCENT: Color = (125, 211, 252)
BOX = pygame.Rect(80, 250, 1120, 182)
PAD = 28
TEXT_TOP = 22  # first line's offset inside BOX
LINE_H = 50
VISIBLE_LINES = 3
CARET_SPEED = 30.0  # fraction of the gap closed per second (exponential glide)
SCROLL_SPEED = 14.0


@register_app
class TypingTestApp(BaseApp):
    """Type the words as fast and accurately as you can before the clock runs out."""

    @classmethod
    def draw_icon(cls, surface: Canvas, rect: pygame.Rect, theme: Theme) -> None:
        draw.rounded_rect(surface, rect, (12, 46, 66), theme.radius.md)
        key = rect.width / 5.2
        gap = key * 0.22
        rows = ((4, 0.0), (4, 0.45), (3, 0.9))
        top = rect.centery - (3 * key + 2 * gap) / 2
        for r, (count, shift) in enumerate(rows):
            for c in range(count):
                x = rect.x + key * 0.55 + shift * key + c * (key + gap)
                box = pygame.Rect(round(x), round(top + r * (key + gap)), round(key), round(key))
                draw.rounded_rect(surface, box, ACCENT if (r, c) == (1, 1) else (56, 116, 150), 3)
        bar = pygame.Rect(0, 0, round(key * 2.6), round(key * 0.5))
        bar.midtop = (rect.centerx, round(top + 3 * (key + gap)))
        draw.rounded_rect(surface, bar, (56, 116, 150), 3)

    # ------------------------------------------------------------------ lifecycle
    def on_enter(self) -> None:
        self.vocabulary = load_words()
        duration = self.data.get("duration", 30)
        self.duration = duration if duration in DURATIONS else 30
        self.picker = SegmentedControl(
            self.theme,
            (900, 64, 300, 40),
            [f"{d} s" for d in DURATIONS],
            DURATIONS.index(self.duration),
            self._set_duration,
            accent=ACCENT,
        )
        self.time = 0.0
        self._new_test()

    def on_exit(self) -> None:
        self.data["duration"] = self.duration
        self.data.save()

    def restart(self) -> None:
        self._new_test()

    def uses_text_input(self) -> bool:
        return self.menu is None

    @property
    def variant(self) -> str:
        return f"{self.duration}s"

    def _set_duration(self, index: int) -> None:
        self.duration = DURATIONS[index]
        self._new_test()

    def _new_test(self) -> None:
        self.test = TypingTest(self.vocabulary, self.duration, random.Random())
        self.menu: ButtonMenu | None = None
        self.new_best = False
        self.caret_x = float(BOX.x + PAD)
        self.scroll = 0.0
        self._layout_key: tuple[int, int, int] | None = None
        self._positions: list[tuple[int, int]] = []

    def _finish(self) -> None:
        test = self.test
        score = round(test.wpm)
        self.new_best = score > 0 and self.submit_score(score, self.variant)
        self.unlock("first_test")
        self.unlock_milestones(score, {"wpm_40": 40, "wpm_80": 80})
        if self.duration >= 30 and test.accuracy == 1.0 and score >= 20:
            self.unlock("flawless")
        self.menu = ButtonMenu(
            self.theme, (640, 552), [("Try again", self._new_test)], accent=ACCENT
        )

    # ------------------------------------------------------------------ events
    def handle_event(self, event: pygame.event.Event) -> None:
        if self.menu is not None:
            if event.type == pygame.KEYDOWN and event.key == pygame.K_TAB:
                self._new_test()
                return
            self.menu.handle_event(event)
            return
        if self.picker.handle_event(event):
            return
        if event.type == pygame.TEXTINPUT:
            for ch in event.text:
                if ch.isprintable():
                    self.test.type_char(ch)
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_TAB:
                self._new_test()
            elif event.key == pygame.K_BACKSPACE:
                mods = getattr(event, "mod", 0)
                whole = bool(mods & (pygame.KMOD_CTRL | pygame.KMOD_ALT | pygame.KMOD_META))
                self.test.backspace(whole)

    def update(self, dt: float) -> None:
        self.time += dt
        self.picker.update(dt)
        if self.menu is not None:
            self.menu.update(dt)
            return
        self.test.tick(dt)
        if self.test.finished:
            self._finish()
            return
        font = self._font()
        self._layout(font)
        line, x = self._caret_target(font)
        glide = min(1.0, dt * CARET_SPEED)
        self.caret_x += (x - self.caret_x) * glide
        target_scroll = max(0, line - 1) * LINE_H
        self.scroll += (target_scroll - self.scroll) * min(1.0, dt * SCROLL_SPEED)

    # ------------------------------------------------------------------ layout
    def _font(self) -> Font:
        return self.theme.font(30, "medium")

    def _display(self, i: int) -> str:
        return "".join(ch for ch, _ in self.test.char_states(i))

    def _layout(self, font: Font) -> None:
        """Wrap words into lines; positions are (line, x). Recomputed only on change."""
        test = self.test
        key = (len(test.typed), len(test.current), len(test.words))
        if key == self._layout_key:
            return
        self._layout_key = key
        space = font.size(" ")[0]
        width = BOX.width - 2 * PAD
        positions: list[tuple[int, int]] = []
        line, x = 0, 0
        for i in range(len(test.words)):
            w = font.size(self._display(i))[0]
            if x and x + w > width:
                line, x = line + 1, 0
            positions.append((line, x))
            x += w + space
            if i > test.index and line > positions[test.index][0] + VISIBLE_LINES:
                break  # nothing further down can be on screen
        self._positions = positions

    def _caret_target(self, font: Font) -> tuple[int, float]:
        test = self.test
        line, x = self._positions[test.index]
        typed = self._display(test.index)[: len(test.current)]
        return line, BOX.x + PAD + x + (font.size(typed)[0] if typed else 0)

    # ------------------------------------------------------------------ drawing
    def draw(self, surface: Canvas) -> None:
        t = self.theme
        p = t.palette
        surface.fill(p.bg)
        self._draw_header(surface, t)
        draw.shadow(surface, BOX, t.radius.lg, p.shadow, (0, 8), 16)
        draw.rounded_rect(surface, BOX, p.surface, t.radius.lg)
        font = self._font()
        self._layout(font)
        self._draw_words(surface, t, font)
        hint = "Tab restart · Esc pause · Ctrl+Backspace clears a word"
        draw.text(surface, hint, t.font(t.size.caption), p.text_muted, (BOX.centerx, 462), "midtop")
        if self.menu is not None:
            self._draw_results(surface, t)

    def _draw_header(self, surface: Canvas, t: Theme) -> None:
        p = t.palette
        draw.text(surface, "Typing Test", t.font(t.size.heading, "bold"), p.text, (80, 60))
        sub = "Type the words below. The clock starts on your first key."
        draw.text(surface, sub, t.font(t.size.label), p.text_muted, (80, 104))
        self.picker.draw(surface)
        test = self.test
        best = self.best_score(self.variant)
        stats = (
            ("Time", f"{test.remaining:.0f}" if test.started else str(self.duration)),
            ("WPM", f"{test.wpm:.0f}" if test.elapsed >= 1 else "—"),
            ("Accuracy", f"{test.accuracy:.0%}" if test.started else "—"),
            ("Best", f"{best.score:.0f}" if best else "—"),
        )
        for i, (label, value) in enumerate(stats):
            x = 80 + i * 160
            draw.text(
                surface, label.upper(), t.font(t.size.caption, "semibold"), p.text_muted, (x, 150)
            )
            color = ACCENT if label == "Time" and test.started else p.text
            draw.text(surface, value, t.font(t.size.heading, "bold"), color, (x, 172))

    def _draw_words(self, surface: Canvas, t: Theme, font: Font) -> None:
        p = t.palette
        test = self.test
        colors: dict[CharState, Color] = {
            "correct": p.text,
            "wrong": p.danger,
            "extra": lerp_color(p.danger, p.surface, 0.4),
            "pending": lerp_color(p.text_muted, p.surface, 0.25),
            "missed": lerp_color(p.text_muted, p.surface, 0.25),
        }
        # Exactly VISIBLE_LINES rows show; the rest of the stream is clipped away.
        clip = pygame.Rect(BOX.x, BOX.y + TEXT_TOP - 6, BOX.width, VISIBLE_LINES * LINE_H - 4)
        prev_clip = surface.get_clip()
        surface.set_clip(clip)
        top = BOX.y + TEXT_TOP - self.scroll
        for i, (line, x) in enumerate(self._positions):
            y = top + line * LINE_H
            if y + LINE_H < clip.top or y > clip.bottom:
                continue
            states = test.char_states(i)
            wx = BOX.x + PAD + x
            if i == test.index:
                word_w = font.size(self._display(i))[0]
                band = pygame.Rect(round(wx) - 6, round(y) - 2, word_w + 12, LINE_H - 8)
                draw.rounded_rect(surface, band, with_alpha(ACCENT, 26), 8)
            # Draw runs of characters that share a state, positioned by their prefix width.
            run_start = 0
            for j in range(1, len(states) + 1):
                if j == len(states) or states[j][1] != states[run_start][1]:
                    prefix = "".join(ch for ch, _ in states[:run_start])
                    run = "".join(ch for ch, _ in states[run_start:j])
                    state = states[run_start][1]
                    rx = wx + (font.size(prefix)[0] if prefix else 0)
                    draw.text(surface, run, font, colors[state], (rx, y))
                    run_start = j
            if i < test.index and test.typed[i] != test.words[i]:
                w = font.size(self._display(i))[0]
                uy = y + LINE_H - 14
                gfx.line(surface, p.danger, (wx, uy), (wx + w, uy), 2)
        if self.menu is None:
            line = self._positions[test.index][0]
            cy = top + line * LINE_H
            blink = test.started or int(self.time * 2) % 2 == 0
            if blink:
                gfx.rect(surface, ACCENT, (self.caret_x - 1, cy + 2, 3, LINE_H - 14), 0, 1.5)
        surface.set_clip(prev_clip)
        if not test.started:
            draw.text(
                surface,
                "Start typing to begin",
                t.font(t.size.label, "semibold"),
                ACCENT,
                (BOX.right - PAD, BOX.y - 30),
                "topright",
            )

    def _draw_results(self, surface: Canvas, t: Theme) -> None:
        p = t.palette
        test = self.test
        assert self.menu is not None
        draw.overlay(surface, p.overlay)
        box = pygame.Rect(0, 0, 720, 440)
        box.center = (640, 380)
        draw_panel(surface, box, t)
        draw.text(
            surface,
            f"{test.wpm:.0f}",
            t.font(72, "bold"),
            ACCENT,
            (box.x + 48, box.y + 30),
        )
        draw.text(
            surface,
            f"WPM · {self.duration} s test",
            t.font(t.size.label, "semibold"),
            p.text_muted,
            (box.x + 52, box.y + 120),
        )
        if self.new_best:
            draw.text(
                surface,
                "New best!",
                t.font(t.size.label, "semibold"),
                p.success,
                (box.x + 52, box.y + 142),
            )
        counts = test.char_counts()
        stats = (
            ("Accuracy", f"{test.accuracy:.0%}"),
            ("Raw", f"{test.raw_wpm:.0f}"),
            ("Characters", f"{counts['correct']}/{counts['wrong']}/{counts['extra']}"),
        )
        for i, (label, value) in enumerate(stats):
            x = box.x + 280 + i * 140
            draw.text(
                surface,
                label.upper(),
                t.font(t.size.caption, "semibold"),
                p.text_muted,
                (x, box.y + 50),
            )
            draw.text(surface, value, t.font(t.size.title, "bold"), p.text, (x, box.y + 72))
        draw.text(
            surface,
            "correct / wrong / extra",
            t.font(t.size.caption),
            p.text_muted,
            (box.x + 560, box.y + 104),
        )
        chart = pygame.Rect(box.x + 48, box.y + 170, box.width - 96, 180)
        self._draw_chart(surface, t, chart)
        self.menu.draw(surface)

    def _draw_chart(self, surface: Canvas, t: Theme, rect: pygame.Rect) -> None:
        """WPM over time: a filled line with a few gridlines."""
        p = t.palette
        samples = self.test.samples
        draw.rounded_rect(surface, rect, p.surface_alt, t.radius.md)
        inner = rect.inflate(-48, -36)
        inner.x += 12
        top = max(20, int(max(samples, default=0) / 20 + 1) * 20)
        small = t.font(t.size.caption)
        for k in range(3):
            value = top * k / 2
            y = inner.bottom - inner.height * k / 2
            gfx.line(
                surface, lerp_color(p.surface_alt, p.border, 0.6), (inner.x, y), (inner.right, y)
            )
            draw.text(surface, f"{value:.0f}", small, p.text_muted, (inner.x - 8, y), "midright")
        if len(samples) < 2:
            return
        step = inner.width / (len(samples) - 1)
        points = [
            (inner.x + i * step, inner.bottom - inner.height * min(1.0, s / top))
            for i, s in enumerate(samples)
        ]
        fill = [(inner.x, inner.bottom), *points, (inner.right, inner.bottom)]
        gfx.polygon(surface, lerp_color(p.surface_alt, ACCENT, 0.22), fill)
        gfx.lines(surface, ACCENT, False, points, 3)
        draw.text(
            surface, "WPM over time", small, p.text_muted, (rect.right - 14, rect.y + 8), "topright"
        )
