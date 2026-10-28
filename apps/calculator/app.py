"""Calculator UI: display, keypad and history panel."""

from __future__ import annotations

import pygame

from apps.calculator.logic import Calculator
from core import draw, gfx
from core.base_app import BaseApp
from core.canvas import Canvas
from core.registry import register_app
from core.theme import Theme, lerp_color
from core.widgets import Button, Grid, draw_panel
from core.widgets.button import Variant

ACCENT = (255, 159, 67)

#: Keypad layout: (label shown, key sent to the model).
KEYPAD: list[list[tuple[str, str]]] = [
    [("C", "clear"), ("(", "("), (")", ")"), ("÷", "/")],
    [("7", "7"), ("8", "8"), ("9", "9"), ("×", "*")],
    [("4", "4"), ("5", "5"), ("6", "6"), ("−", "-")],
    [("1", "1"), ("2", "2"), ("3", "3"), ("+", "+")],
    [("0", "0"), (".", "."), ("⌫", "back"), ("=", "=")],
]
#: Typed characters that map to model keys (TEXTINPUT events).
TYPED = {c: c for c in "0123456789.+-*/^()="} | {
    ",": ".",
    "x": "*",
    "X": "*",
    "c": "clear",
    "C": "clear",
}

CALC_WIDTH = 420
HISTORY_WIDTH = 340


@register_app
class CalculatorApp(BaseApp):
    """Standard calculator with mouse and keyboard input."""

    @classmethod
    def draw_icon(cls, surface: Canvas, rect: pygame.Rect, theme: Theme) -> None:
        draw.rounded_rect(surface, rect, ACCENT, theme.radius.md)
        key = rect.width // 4
        gap = rect.width // 10
        x0 = rect.centerx - key - gap // 2
        y0 = rect.centery - key - gap // 2
        for i in range(4):
            r = pygame.Rect(x0 + (i % 2) * (key + gap), y0 + (i // 2) * (key + gap), key, key)
            color = (255, 255, 255) if i != 3 else (120, 60, 10)
            gfx.rect(surface, color, r, border_radius=3)

    def on_enter(self) -> None:
        self.calc = Calculator()
        screen = self.ctx.screen_rect
        gap = self.theme.space.lg
        left = (screen.width - CALC_WIDTH - gap - HISTORY_WIDTH) // 2
        self.panel = pygame.Rect(left, 60, CALC_WIDTH, 600)
        self.history_rect = pygame.Rect(self.panel.right + gap, 60, HISTORY_WIDTH, 600)
        self.display = pygame.Rect(self.panel.x + 20, self.panel.y + 20, CALC_WIDTH - 40, 150)
        keys_area = pygame.Rect(self.panel.x + 20, self.display.bottom + 20, CALC_WIDTH - 40, 390)
        grid = Grid(keys_area, columns=4, cell_height=66, gap=12)
        self.buttons: dict[str, Button] = {}
        index = 0
        for row in KEYPAD:
            for label, key in row:
                variant: Variant = "secondary"
                accent = None
                if key == "=":
                    variant, accent = "primary", ACCENT
                elif key in ("+", "-", "*", "/"):
                    variant, accent = "primary", lerp_color(ACCENT, (90, 90, 110), 0.55)
                elif key == "clear":
                    variant = "danger"
                self.buttons[key] = Button(
                    self.theme,
                    grid.cell(index),
                    label,
                    lambda key=key: self.calc.press(key),  # type: ignore[misc]
                    variant,
                    accent=accent,
                    font_size=24,
                )
                index += 1

    def _press(self, key: str) -> None:
        self.calc.press(key)
        button = self.buttons.get(key)
        if button is not None:
            button.flash()

    def uses_text_input(self) -> bool:
        return True

    def handle_event(self, event: pygame.event.Event) -> None:
        for button in self.buttons.values():
            if button.handle_event(event):
                return
        if event.type == pygame.TEXTINPUT:
            for ch in event.text:
                if ch in TYPED:
                    self._press(TYPED[ch])
        elif event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self._press("=")
            elif event.key == pygame.K_BACKSPACE:
                self._press("back")
            elif event.key == pygame.K_DELETE:
                self._press("clear")

    def update(self, dt: float) -> None:
        for button in self.buttons.values():
            button.update(dt)

    def draw(self, surface: Canvas) -> None:
        t = self.theme
        p = t.palette
        surface.fill(p.bg)
        draw_panel(surface, self.panel, t)
        self._draw_display(surface, t)
        for button in self.buttons.values():
            button.draw(surface)
        self._draw_history(surface, t)
        draw.text(
            surface,
            "Type to calculate · ^ for powers · Enter to evaluate · Del to clear",
            t.font(t.size.caption),
            p.text_muted,
            (self.ctx.screen_rect.centerx, self.ctx.screen_rect.bottom - 22),
            "center",
        )

    def _draw_display(self, surface: Canvas, t: Theme) -> None:
        p = t.palette
        draw.rounded_rect(surface, self.display, p.surface_alt, t.radius.md)
        right = self.display.right - 20
        width = self.display.width - 40
        calc = self.calc

        font = t.font(44 if len(calc.expression) < 14 else 30, "semibold")
        expr = calc.expression or "0"
        # Keep the end of a long expression visible.
        while font.size(expr)[0] > width and len(expr) > 1:
            expr = "…" + expr[2:]
        draw.text(surface, expr, font, p.text, (right, self.display.y + 72), "midright")

        if calc.error:
            line, color = calc.error, p.danger
        elif calc.preview is not None:
            line, color = f"= {calc.preview}", p.text_muted
        elif calc.just_evaluated and calc.history:
            line, color = f"{calc.history[0][0]} =", p.text_muted
        else:
            line, color = "", p.text_muted
        small = t.font(t.size.body)
        draw.text(
            surface,
            draw.fit_text(line, small, width),
            small,
            color,
            (right, self.display.y + 122),
            "midright",
        )

    def _draw_history(self, surface: Canvas, t: Theme) -> None:
        p = t.palette
        rect = self.history_rect
        draw_panel(surface, rect, t)
        draw.text(
            surface, "History", t.font(t.size.title, "semibold"), p.text, (rect.x + 24, rect.y + 24)
        )
        if not self.calc.history:
            draw.text(
                surface,
                "Results appear here",
                t.font(t.size.label),
                p.text_muted,
                (rect.x + 24, rect.y + 68),
            )
            return
        y = rect.y + 72
        expr_font, result_font = t.font(t.size.caption), t.font(t.size.title, "semibold")
        for expr, result in self.calc.history:
            draw.text(
                surface,
                draw.fit_text(expr + " =", expr_font, rect.width - 48),
                expr_font,
                p.text_muted,
                (rect.right - 24, y),
                "topright",
            )
            draw.text(
                surface,
                draw.fit_text(result, result_font, rect.width - 48),
                result_font,
                ACCENT,
                (rect.right - 24, y + 18),
                "topright",
            )
            y += 64
            if y > rect.bottom - 60:
                break
