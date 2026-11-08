"""Password Generator UI: the password card, a strength meter, options and recent passwords."""

from __future__ import annotations

from collections.abc import Callable

import pygame

from apps.password_generator.logic import (
    MAX_LENGTH,
    MIN_LENGTH,
    STRENGTH_LABELS,
    Options,
    char_kind,
    crack_time,
    entropy_bits,
    generate,
    strength,
)
from core import draw, gfx
from core.base_app import BaseApp
from core.canvas import Canvas, mouse_pos
from core.clipboard import copy_text
from core.input import is_action
from core.registry import register_app
from core.theme import Color, Theme, lerp_color
from core.widgets import Button, Slider, Toggle, draw_panel

ACCENT: Color = (124, 58, 237)
LEFT, WIDTH = 160, 960
CARD = pygame.Rect(LEFT, 92, WIDTH, 132)
OPTIONS = pygame.Rect(LEFT, 332, 580, 324)
RECENT = pygame.Rect(LEFT + 610, 332, WIDTH - 610, 324)
HISTORY_SIZE = 6
OPTION_ROWS: tuple[tuple[str, str, str], ...] = (
    ("lower", "Lowercase", "a–z"),
    ("upper", "Uppercase", "A–Z"),
    ("digits", "Digits", "0–9"),
    ("symbols", "Symbols", "!#$%&*+-=?@^_~"),
    ("avoid_ambiguous", "Avoid look-alikes", "no I, l, 1, |, O, 0, o"),
)


def strength_color(level: int, theme: Theme) -> Color:
    p = theme.palette
    return (p.danger, p.danger, p.warning, p.success, p.success)[level]


@register_app
class PasswordGeneratorApp(BaseApp):
    """Generate random passwords from the OS's secure random source."""

    @classmethod
    def draw_icon(cls, surface: Canvas, rect: pygame.Rect, theme: Theme) -> None:
        draw.rounded_rect(surface, rect, ACCENT, theme.radius.md)
        u = rect.width / 8
        white = (255, 255, 255)
        body = pygame.Rect(
            round(rect.x + 2 * u), round(rect.y + 3.6 * u), round(4 * u), round(3 * u)
        )
        shackle = pygame.Rect(
            round(rect.x + 2.8 * u), round(rect.y + 1.4 * u), round(2.4 * u), round(4 * u)
        )
        gfx.arc(surface, white, shackle, 0, 3.1416, 3)
        gfx.line(surface, white, (shackle.x + 1, shackle.centery), (shackle.x + 1, body.y), 3)
        gfx.line(
            surface, white, (shackle.right - 2, shackle.centery), (shackle.right - 2, body.y), 3
        )
        draw.rounded_rect(surface, body, white, max(2, round(u * 0.5)))
        for i in range(3):
            gfx.circle(surface, ACCENT, (body.x + (i + 1) * body.width / 4, body.centery), u * 0.32)

    # ------------------------------------------------------------------ lifecycle
    def on_enter(self) -> None:
        t = self.theme
        self.options = Options.from_dict(self.data.get("options"))
        self.history: list[str] = []  # kept in memory only, never saved
        self.generate_btn = Button(
            t,
            (LEFT + WIDTH - 200, 256, 200, 52),
            "Generate",
            self._generate,
            "primary",
            accent=ACCENT,
        )
        self.copy_btn = Button(t, (LEFT + WIDTH - 376, 256, 160, 52), "Copy", self._copy)
        self.length_slider = Slider(
            t,
            (OPTIONS.x + 24, OPTIONS.y + 64, OPTIONS.width - 48, 28),
            MIN_LENGTH,
            MAX_LENGTH,
            self.options.length,
            self._set_length,
            accent=ACCENT,
        )
        self.toggles = [
            Toggle(
                t,
                (OPTIONS.right - 24 - Toggle.WIDTH, OPTIONS.y + 116 + i * 40),
                bool(getattr(self.options, name)),
                self._option_setter(name),
                accent=ACCENT,
            )
            for i, (name, _, _) in enumerate(OPTION_ROWS)
        ]
        self.password = ""
        self.copied_t = 0.0  # seconds left on the "Copied" flash
        self._generate()

    def on_exit(self) -> None:
        self._save()

    def restart(self) -> None:
        self.history.clear()
        self._generate()

    def _save(self) -> None:
        self.data["options"] = self.options.to_dict()
        self.data.save()

    # ------------------------------------------------------------------ actions
    def _generate(self) -> None:
        if self.password:
            self.history = [self.password, *self.history][:HISTORY_SIZE]
        self.password = generate(self.options)
        self.copied_t = 0.0

    def _copy(self, text: str | None = None) -> None:
        text = self.password if text is None else text
        if copy_text(text):
            self.ctx.toasts.show("Copied to clipboard", f"{len(text)} characters", ACCENT)
            if text == self.password:
                self.copied_t = 1.5
        else:
            self.ctx.toasts.show("Couldn't copy", "The clipboard isn't available here.")

    def _set_length(self, value: float) -> None:
        self.options.set_length(int(value))
        self._generate()
        self._save()

    def _option_setter(self, name: str) -> Callable[[bool], None]:
        return lambda on: self._set_option(name, on)

    def _set_option(self, name: str, on: bool) -> None:
        setattr(self.options, name, on)
        if not self.options.sets():  # keep at least one character set
            setattr(self.options, name, True)
            for toggle, (row_name, _, _) in zip(self.toggles, OPTION_ROWS, strict=True):
                if row_name == name:
                    toggle.value = True
            return
        self._generate()
        self._save()

    def _history_rects(self) -> list[pygame.Rect]:
        return [
            pygame.Rect(RECENT.x + 12, RECENT.y + 80 + i * 38, RECENT.width - 24, 34)
            for i in range(len(self.history))
        ]

    # ------------------------------------------------------------------ input
    def handle_event(self, event: pygame.event.Event) -> None:
        for widget in (self.generate_btn, self.copy_btn, self.length_slider, *self.toggles):
            if widget.handle_event(event):
                return
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if CARD.collidepoint(event.pos):
                self._copy()
            for text, rect in zip(self.history, self._history_rects(), strict=True):
                if rect.collidepoint(event.pos):
                    self._copy(text)
        elif is_action(event, "action", repeat=False):
            self._generate()
        elif is_action(event, "left"):
            self.length_slider.set_value(self.options.length - 1)
        elif is_action(event, "right"):
            self.length_slider.set_value(self.options.length + 1)
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_c:
                self._copy()
            elif pygame.K_1 <= event.key < pygame.K_1 + len(self.toggles):
                self.toggles[event.key - pygame.K_1].toggle()

    def update(self, dt: float) -> None:
        self.copied_t = max(0.0, self.copied_t - dt)
        for widget in (self.generate_btn, self.copy_btn, self.length_slider, *self.toggles):
            widget.update(dt)
        self.copy_btn.text = "Copied" if self.copied_t > 0 else "Copy"

    # ------------------------------------------------------------------ drawing
    def draw(self, surface: Canvas) -> None:
        t = self.theme
        p = t.palette
        surface.fill(p.bg)
        draw.text(surface, "Password Generator", t.font(t.size.heading, "bold"), p.text, (LEFT, 30))
        self._draw_card(surface, t)
        self._draw_strength(surface, t)
        self.generate_btn.draw(surface)
        self.copy_btn.draw(surface)
        self._draw_options(surface, t)
        self._draw_recent(surface, t)
        hint = "Space new · C copy · ←/→ length · 1–5 options · click a password to copy it"
        draw.text(surface, hint, t.font(t.size.caption), p.text_muted, (640, 696), "center")

    def _draw_card(self, surface: Canvas, t: Theme) -> None:
        p = t.palette
        draw_panel(surface, CARD, t)
        if CARD.collidepoint(mouse_pos()):
            draw.rounded_rect(surface, CARD, lerp_color(p.surface, ACCENT, 0.5), t.radius.lg, 2)
        colors = {
            "letter": p.text,
            "digit": lerp_color(p.primary, p.text, 0.15),
            "symbol": lerp_color(ACCENT, p.text, 0.25 if t.mode == "dark" else 0.0),
        }
        room = CARD.width - 64
        size = t.size.display
        font = t.font(size, "semibold")
        while size > 26 and font.size(self.password)[0] > room:
            size -= 2
            font = t.font(size, "semibold")
        lines = [self.password]
        if font.size(self.password)[0] > room:
            half = (len(self.password) + 1) // 2
            lines = [self.password[:half], self.password[half:]]
        line_h = font.get_height()
        y = CARD.centery - line_h * len(lines) / 2
        for line in lines:
            x = CARD.centerx - font.size(line)[0] / 2
            for ch in line:
                draw.text(surface, ch, font, colors[char_kind(ch)], (x, y))
                x += font.size(ch)[0]
            y += line_h

    def _draw_strength(self, surface: Canvas, t: Theme) -> None:
        p = t.palette
        bits = entropy_bits(self.options)
        level = strength(bits)
        color = strength_color(level, t)
        seg_w = (WIDTH - 4 * 8) / 5
        for i in range(5):
            seg = pygame.Rect(round(LEFT + i * (seg_w + 8)), 240, round(seg_w), 8)
            draw.rounded_rect(surface, seg, color if i <= level else p.surface_alt, 4)
        label = draw.text(
            surface,
            STRENGTH_LABELS[level],
            t.font(t.size.body, "bold"),
            color,
            (LEFT, 270),
            "midleft",
        )
        draw.text(
            surface,
            f"{bits:.0f} bits · about {crack_time(bits)} to crack",
            t.font(t.size.label),
            p.text_muted,
            (label.right + 12, 270),
            "midleft",
        )
        draw.text(
            surface,
            "From your system's secure random source",
            t.font(t.size.caption),
            p.text_muted,
            (LEFT, 296),
            "midleft",
        )

    def _draw_options(self, surface: Canvas, t: Theme) -> None:
        p = t.palette
        draw_panel(surface, OPTIONS, t)
        x = OPTIONS.x + 24
        draw.text(surface, "Length", t.font(t.size.body, "semibold"), p.text, (x, OPTIONS.y + 22))
        draw.text(
            surface,
            str(self.options.length),
            t.font(t.size.title, "bold"),
            ACCENT if t.mode == "light" else lerp_color(ACCENT, p.text, 0.35),
            (OPTIONS.right - 24, OPTIONS.y + 32),
            "midright",
        )
        self.length_slider.draw(surface)
        for toggle, (_, name, detail) in zip(self.toggles, OPTION_ROWS, strict=True):
            cy = toggle.rect.centery
            name_rect = draw.text(surface, name, t.font(t.size.body), p.text, (x, cy), "midleft")
            draw.text(
                surface,
                detail,
                t.font(t.size.caption),
                p.text_muted,
                (name_rect.right + 12, cy),
                "midleft",
            )
            toggle.draw(surface)

    def _draw_recent(self, surface: Canvas, t: Theme) -> None:
        p = t.palette
        draw_panel(surface, RECENT, t)
        draw.text(
            surface,
            "Recent",
            t.font(t.size.body, "semibold"),
            p.text,
            (RECENT.x + 24, RECENT.y + 22),
        )
        draw.text(
            surface,
            "Click to copy. Never saved to disk.",
            t.font(t.size.caption),
            p.text_muted,
            (RECENT.x + 24, RECENT.y + 48),
        )
        if not self.history:
            draw.text(
                surface,
                "Earlier passwords show up here.",
                t.font(t.size.caption),
                p.text_muted,
                (RECENT.x + 24, RECENT.y + 92),
            )
            return
        mouse = mouse_pos()
        font = t.font(t.size.label, "medium")
        for text, rect in zip(self.history, self._history_rects(), strict=True):
            if rect.collidepoint(mouse):
                draw.rounded_rect(surface, rect, p.surface_hover, t.radius.sm)
            draw.text(
                surface,
                draw.fit_text(text, font, rect.width - 24),
                font,
                p.text_muted,
                (rect.x + 12, rect.centery),
                "midleft",
            )
