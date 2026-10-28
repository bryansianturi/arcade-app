"""Unit Converter UI: category list, value input with unit chips, and a results table."""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal

import pygame

from apps.unit_converter.logic import CATEGORIES, Category, convert, format_value, parse_number
from core import draw, gfx
from core.base_app import BaseApp
from core.canvas import Canvas, mouse_pos
from core.input import direction
from core.registry import register_app
from core.theme import Color, Theme, lerp_color
from core.widgets import Button, Grid, TextInput, draw_panel

ACCENT: Color = (5, 150, 105)
SIDEBAR_X, SIDEBAR_W = 48, 210
MIDDLE_X, MIDDLE_W = 290, 420
RESULTS = pygame.Rect(740, 96, 492, 580)
ROW_H = 54


@register_app
class UnitConverterApp(BaseApp):
    """Convert between common units, showing every unit in the category at once."""

    @classmethod
    def draw_icon(cls, surface: Canvas, rect: pygame.Rect, theme: Theme) -> None:
        draw.rounded_rect(surface, rect, ACCENT, theme.radius.md)
        u = rect.width / 8
        white = (255, 255, 255)
        for y, arrow in ((3, 1), (5, -1)):
            start, end = (rect.x + 2 * u, rect.y + y * u), (rect.x + 6 * u, rect.y + y * u)
            if arrow < 0:
                start, end = end, start
            draw.thick_line(surface, white, start, end, 3)
            tip = pygame.Vector2(end)
            back = pygame.Vector2(-arrow * u, 0)
            gfx.polygon(
                surface,
                white,
                [
                    tip + pygame.Vector2(arrow * 2, 0),
                    tip + back + (0, -u * 0.7),
                    tip + back + (0, u * 0.7),
                ],
            )

    # ------------------------------------------------------------------ lifecycle
    def on_enter(self) -> None:
        t = self.theme
        names = [c.name for c in CATEGORIES]
        saved_cat = self.data.get("category")
        self.cat_index = names.index(saved_cat) if saved_cat in names else 0
        self.cat_buttons = [
            Button(
                t,
                (SIDEBAR_X, 96 + i * 54, SIDEBAR_W, 46),
                c.name,
                self._category_setter(i),
                "ghost",
            )
            for i, c in enumerate(CATEGORIES)
        ]
        self.value_input = TextInput(
            t, (MIDDLE_X, 128, MIDDLE_W, 56), "Enter a value", max_length=24
        )
        self.value_input.set_text(str(self.data.get("value", "1")))
        self.value_input.focus()
        self.from_symbol = ""
        self._load_category(self.data.get("unit"))

    def on_exit(self) -> None:
        self.data["category"] = self.category.name
        self.data["unit"] = self.from_symbol
        self.data["value"] = self.value_input.text
        self.data.save()

    def restart(self) -> None:
        self.value_input.set_text("1")

    @property
    def category(self) -> Category:
        return CATEGORIES[self.cat_index]

    def _category_setter(self, index: int) -> Callable[[], None]:
        return lambda: self._set_category(index)

    def _set_category(self, index: int) -> None:
        self.cat_index = index % len(CATEGORIES)
        self._load_category(None)

    def _load_category(self, preferred_unit: object) -> None:
        cat = self.category
        symbols = [u.symbol for u in cat.units]
        if isinstance(preferred_unit, str) and preferred_unit in symbols:
            self.from_symbol = preferred_unit
        else:
            self.from_symbol = symbols[min(2, len(symbols) - 1)]  # a sensible middle unit
        grid = Grid(pygame.Rect(MIDDLE_X, 248, MIDDLE_W, 400), 3, 46, 10)
        self.unit_buttons = [
            Button(self.theme, grid.cell(i), u.symbol, self._unit_setter(u.symbol))
            for i, u in enumerate(cat.units)
        ]
        for i, button in enumerate(self.cat_buttons):
            button.variant = "primary" if i == self.cat_index else "ghost"
            button.accent = ACCENT

    def _unit_setter(self, symbol: str) -> Callable[[], None]:
        return lambda: self._set_unit(symbol)

    def _set_unit(self, symbol: str) -> None:
        self.from_symbol = symbol

    def value(self) -> Decimal | None:
        return parse_number(self.value_input.text)

    # ------------------------------------------------------------------ input
    def _row_rects(self) -> list[pygame.Rect]:
        return [
            pygame.Rect(RESULTS.x + 12, RESULTS.y + 64 + i * ROW_H, RESULTS.width - 24, ROW_H - 6)
            for i in range(len(self.category.units))
        ]

    def uses_text_input(self) -> bool:
        return True

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.TEXTINPUT and not self.value_input.focused:
            self.value_input.focus()
        if self.value_input.handle_event(event):
            return
        for button in (*self.cat_buttons, *self.unit_buttons):
            if button.handle_event(event):
                self.value_input.focus()
                return
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            value = self.value()
            for unit, rect in zip(self.category.units, self._row_rects(), strict=True):
                if rect.collidepoint(event.pos) and value is not None:
                    # Click a result to continue converting from it.
                    converted = convert(value, self.category, self.from_symbol, unit.symbol)
                    self.value_input.set_text(
                        format_value(converted).replace(",", "").replace("×10^", "e")
                    )
                    self.from_symbol = unit.symbol
            self.value_input.focus()
        elif (step := direction(event)) is not None:
            dx, dy = step
            if dy:
                self._set_category(self.cat_index + dy)
            else:
                symbols = [u.symbol for u in self.category.units]
                self.from_symbol = symbols[(symbols.index(self.from_symbol) + dx) % len(symbols)]

    def update(self, dt: float) -> None:
        self.value_input.update(dt)
        for button in (*self.cat_buttons, *self.unit_buttons):
            button.update(dt)
        for button in self.unit_buttons:
            button.variant = "primary" if button.text == self.from_symbol else "secondary"
            button.accent = ACCENT

    # ------------------------------------------------------------------ drawing
    def draw(self, surface: Canvas) -> None:
        t = self.theme
        p = t.palette
        surface.fill(p.bg)
        draw.text(
            surface, "Unit Converter", t.font(t.size.heading, "bold"), p.text, (SIDEBAR_X, 30)
        )
        for button in self.cat_buttons:
            button.draw(surface)

        draw.text(
            surface, "VALUE", t.font(t.size.caption, "semibold"), p.text_muted, (MIDDLE_X, 104)
        )
        self.value_input.draw(surface)
        value = self.value()
        if self.value_input.text and value is None:
            draw.text(
                surface,
                "Enter a number like 12.5, -3 or 2e6",
                t.font(t.size.caption),
                p.danger,
                (MIDDLE_X, 192),
            )
        draw.text(
            surface, "FROM UNIT", t.font(t.size.caption, "semibold"), p.text_muted, (MIDDLE_X, 224)
        )
        for button in self.unit_buttons:
            button.draw(surface)
        hint = "Type a value · ↑/↓ category · ←/→ unit · click a result to convert from it"
        draw.text(surface, hint, t.font(t.size.caption), p.text_muted, (SIDEBAR_X, 690), "midleft")
        self._draw_results(surface, t, value)

    def _draw_results(self, surface: Canvas, t: Theme, value: Decimal | None) -> None:
        p = t.palette
        cat = self.category
        panel = RESULTS.copy()
        panel.height = 76 + len(cat.units) * ROW_H
        draw_panel(surface, panel, t)
        source = cat.unit(self.from_symbol)
        title = f"{format_value(value)} {source.symbol}" if value is not None else "—"
        draw.text(
            surface,
            f"{title} =",
            t.font(t.size.title, "semibold"),
            p.text,
            (panel.x + 24, panel.y + 22),
        )
        mouse = mouse_pos()
        for unit, rect in zip(cat.units, self._row_rects(), strict=True):
            is_source = unit.symbol == self.from_symbol
            if is_source:
                draw.rounded_rect(surface, rect, lerp_color(p.surface, ACCENT, 0.16), t.radius.md)
            elif rect.collidepoint(mouse):
                draw.rounded_rect(surface, rect, p.surface_alt, t.radius.md)
            result = (
                format_value(convert(value, cat, self.from_symbol, unit.symbol))
                if value is not None
                else "—"
            )
            draw.text(
                surface,
                unit.name,
                t.font(t.size.caption),
                p.text_muted,
                (rect.x + 12, rect.centery),
                "midleft",
            )
            value_font = t.font(t.size.body, "bold")
            symbol_font = t.font(t.size.body, "medium")
            sym_rect = draw.text(
                surface,
                unit.symbol,
                symbol_font,
                ACCENT if is_source else p.text_muted,
                (rect.right - 12, rect.centery),
                "midright",
            )
            room = rect.width - 200 - sym_rect.width
            draw.text(
                surface,
                draw.fit_text(result, value_font, room),
                value_font,
                p.text,
                (sym_rect.x - 8, rect.centery),
                "midright",
            )
