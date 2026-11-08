"""Color Picker UI: saturation/value square, hue strip, values to copy, and a palette."""

from __future__ import annotations

import random
from collections.abc import Callable

import pygame

from apps.color_picker.logic import (
    HARMONIES,
    HARMONY_NAMES,
    HSV,
    RGB,
    Harmony,
    contrast,
    hsl_text,
    palette,
    parse_hex,
    random_color,
    rgb_text,
    to_hex,
    wcag_grade,
)
from core import draw, gfx
from core.base_app import BaseApp
from core.canvas import Canvas, mouse_pos
from core.clipboard import copy_text
from core.input import is_action
from core.registry import register_app
from core.theme import Color, Theme, readable_on
from core.widgets import Button, SegmentedControl, Slider, TextInput, draw_panel

ACCENT: Color = (225, 29, 72)
SV = pygame.Rect(48, 92, 380, 320)
HUE = pygame.Rect(444, 92, 28, 320)
SWATCH = pygame.Rect(504, 92, 240, 150)
VALUES_X = 776
PALETTE = pygame.Rect(48, 440, 1184, 236)
GRADIENT_RES = 48  # the SV square is computed at this size, then smoothly scaled
WHITE: RGB = (255, 255, 255)
BLACK: RGB = (0, 0, 0)


def sv_gradient(hue: float, size: tuple[int, int]) -> pygame.Surface:
    """The saturation (→) / value (↓) square for ``hue``, ``size`` physical pixels."""
    small = pygame.Surface((GRADIENT_RES, GRADIENT_RES))
    top = HSV(hue, 1, 1).to_rgb()
    last = GRADIENT_RES - 1
    for x in range(GRADIENT_RES):
        s = x / last
        row = tuple(255 + (c - 255) * s for c in top)
        for y in range(GRADIENT_RES):
            v = 1 - y / last
            small.set_at((x, y), (round(row[0] * v), round(row[1] * v), round(row[2] * v)))
    return pygame.transform.smoothscale(small, size)


def hue_gradient(size: tuple[int, int]) -> pygame.Surface:
    small = pygame.Surface((1, 360))
    for y in range(360):
        small.set_at((0, y), HSV(y, 1, 1).to_rgb())
    return pygame.transform.smoothscale(small, size)


@register_app
class ColorPickerApp(BaseApp):
    """Pick a color and copy it, or generate a palette around it."""

    @classmethod
    def draw_icon(cls, surface: Canvas, rect: pygame.Rect, theme: Theme) -> None:
        draw.rounded_rect(surface, rect, ACCENT, theme.radius.md)
        r = rect.width * 0.14
        cx, cy = rect.center
        for i, color in enumerate(((250, 204, 21), (56, 189, 248), (52, 211, 153), WHITE)):
            dx = (-1 if i % 2 == 0 else 1) * r * 1.15
            dy = (-1 if i < 2 else 1) * r * 1.15
            gfx.circle(surface, color, (cx + dx, cy + dy), r)

    # ------------------------------------------------------------------ lifecycle
    def on_enter(self) -> None:
        t = self.theme
        self.rng = random.Random()
        saved = self.data.get("color")
        loaded = parse_hex(saved) if isinstance(saved, str) else None
        hue = self.data.get("hue")
        self.color = (
            HSV.from_rgb(loaded, float(hue) if isinstance(hue, (int, float)) else 0.0)
            if loaded is not None
            else HSV(350, 0.87, 0.88)
        )
        harmony = self.data.get("harmony")
        self.harmony: Harmony = harmony if harmony in HARMONIES else "complementary"
        self.dragging: str | None = None  # "sv" or "hue"
        self.hex_input = TextInput(
            t, (SWATCH.x, 262, SWATCH.width, 44), "#RRGGBB", self._typed_hex, 7
        )
        self.copy_buttons = [
            Button(t, (1232 - 92, 92 + i * 52, 92, 40), "Copy", self._copier(fmt))
            for i, fmt in enumerate((to_hex, rgb_text, hsl_text))
        ]
        self.sliders = [
            Slider(
                t,
                (VALUES_X + 28, 268 + i * 48, 1232 - 64 - VALUES_X - 28, 28),
                0,
                255,
                0,
                self._channel_setter(i),
                accent=ACCENT,
            )
            for i in range(3)
        ]
        self.tabs = SegmentedControl(
            t,
            (PALETTE.x + 140, PALETTE.y + 20, 740, 40),
            [HARMONY_NAMES[h] for h in HARMONIES],
            HARMONIES.index(self.harmony),
            self._set_harmony,
            accent=ACCENT,
        )
        self.random_btn = Button(
            t,
            (PALETTE.right - 172, PALETTE.y + 20, 148, 40),
            "Random",
            self._random,
            "primary",
            accent=ACCENT,
        )
        self._sv_cache: tuple[tuple[float, tuple[int, int]], Canvas] | None = None
        self._hue_cache: tuple[tuple[int, int], Canvas] | None = None
        self._set_color(self.color)

    def on_exit(self) -> None:
        self.data["color"] = to_hex(self.rgb)
        self.data["hue"] = round(self.color.h, 2)
        self.data["harmony"] = self.harmony
        self.data.save()

    def restart(self) -> None:
        self._random()

    # ------------------------------------------------------------------ state
    @property
    def rgb(self) -> RGB:
        return self.color.to_rgb()

    def _set_color(self, color: HSV) -> None:
        self.color = color.clamped()
        rgb = self.rgb
        for slider, value in zip(self.sliders, rgb, strict=True):
            slider.value = value
        if not self.hex_input.focused:
            self.hex_input.text = to_hex(rgb)

    def _set_rgb(self, rgb: RGB) -> None:
        self._set_color(HSV.from_rgb(rgb, self.color.h))

    def _typed_hex(self, text: str) -> None:
        rgb = parse_hex(text)
        if rgb is not None and self.hex_input.focused and len(text.removeprefix("#")) == 6:
            self._set_rgb(rgb)

    def _channel_setter(self, index: int) -> Callable[[float], None]:
        def set_channel(value: float) -> None:
            rgb = list(self.rgb)
            rgb[index] = int(value)
            self._set_rgb((rgb[0], rgb[1], rgb[2]))

        return set_channel

    def _copier(self, fmt: Callable[[RGB], str]) -> Callable[[], None]:
        return lambda: self._copy(fmt(self.rgb))

    def _copy(self, text: str) -> None:
        if copy_text(text):
            self.ctx.toasts.show("Copied to clipboard", text, self.rgb)
        else:
            self.ctx.toasts.show("Couldn't copy", "The clipboard isn't available here.")

    def _set_harmony(self, index: int) -> None:
        self.tabs.index = index
        self.harmony = HARMONIES[index]

    def _random(self) -> None:
        self._set_color(random_color(self.rng))

    def _palette_rects(self) -> list[pygame.Rect]:
        gap, x0 = 16, PALETTE.x + 24
        w = (PALETTE.width - 48 - 4 * gap) // 5
        return [pygame.Rect(x0 + i * (w + gap), PALETTE.y + 84, w, 104) for i in range(5)]

    def _pick_at(self, pos: tuple[int, int]) -> None:
        if self.dragging == "sv":
            s = (pos[0] - SV.x) / SV.width
            v = 1 - (pos[1] - SV.y) / SV.height
            self._set_color(HSV(self.color.h, s, v))
        elif self.dragging == "hue":
            h = (pos[1] - HUE.y) / HUE.height * 360
            self._set_color(HSV(min(359.99, max(0.0, h)), self.color.s, self.color.v))

    # ------------------------------------------------------------------ input
    def uses_text_input(self) -> bool:
        return self.hex_input.focused

    def handle_event(self, event: pygame.event.Event) -> None:
        if self.hex_input.focused and is_action(event, "action", repeat=False):
            self.hex_input.focused = False
            self._set_color(self.color)  # show the normalised value
            return
        widgets = (self.hex_input, *self.copy_buttons, *self.sliders, self.tabs, self.random_btn)
        for widget in widgets:
            if widget.handle_event(event):
                return
        if event.type == pygame.MOUSEBUTTONDOWN and event.button in (1, 3):
            self._set_color(self.color)  # leaving the hex field: show the current value
            if event.button == 1 and SV.inflate(8, 8).collidepoint(event.pos):
                self.dragging = "sv"
            elif event.button == 1 and HUE.inflate(12, 8).collidepoint(event.pos):
                self.dragging = "hue"
            self._pick_at(event.pos)
            for rgb, rect in zip(self._palette(), self._palette_rects(), strict=True):
                if rect.collidepoint(event.pos):
                    if event.button == 1:
                        self._copy(to_hex(rgb))
                    else:
                        self._set_rgb(rgb)
        elif event.type == pygame.MOUSEMOTION and self.dragging:
            self._pick_at(event.pos)
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            self.dragging = None
        elif event.type == pygame.KEYDOWN:
            self._shortcut(event)
        else:
            self._nudge(event)

    def _shortcut(self, event: pygame.event.Event) -> None:
        if event.key == pygame.K_c:
            self._copy(to_hex(self.rgb))
        elif event.key in (pygame.K_h, pygame.K_TAB):
            self._set_harmony((HARMONIES.index(self.harmony) + 1) % len(HARMONIES))
        elif pygame.K_1 <= event.key <= pygame.K_5:
            self._copy(to_hex(self._palette()[event.key - pygame.K_1]))

    def _nudge(self, event: pygame.event.Event) -> None:
        c = self.color
        if is_action(event, "action", repeat=False):
            self._random()
        elif is_action(event, "left"):
            self._set_color(HSV(c.h - 3, c.s, c.v))
        elif is_action(event, "right"):
            self._set_color(HSV(c.h + 3, c.s, c.v))
        elif is_action(event, "up"):
            self._set_color(HSV(c.h, c.s, c.v + 0.03))
        elif is_action(event, "down"):
            self._set_color(HSV(c.h, c.s, c.v - 0.03))

    def update(self, dt: float) -> None:
        if self.dragging and not pygame.mouse.get_pressed()[0]:
            self.dragging = None
        for widget in (
            self.hex_input,
            *self.copy_buttons,
            *self.sliders,
            self.tabs,
            self.random_btn,
        ):
            widget.update(dt)

    def _palette(self) -> list[RGB]:
        return palette(self.color, self.harmony)

    # ------------------------------------------------------------------ drawing
    def draw(self, surface: Canvas) -> None:
        t = self.theme
        p = t.palette
        surface.fill(p.bg)
        draw.text(surface, "Color Picker", t.font(t.size.heading, "bold"), p.text, (48, 30))
        self._draw_picker(surface, t)
        self._draw_values(surface, t)
        self._draw_palette(surface, t)
        hint = (
            "Drag to pick · ←/→ hue · ↑/↓ brightness · Space random · C copy hex · "
            "H harmony · 1–5 copy a swatch · right-click a swatch to use it"
        )
        draw.text(surface, hint, t.font(t.size.caption), p.text_muted, (640, 700), "center")

    def _rounded(self, image: pygame.Surface, scale: float) -> Canvas:
        layer = pygame.Surface(image.get_size(), pygame.SRCALPHA)
        layer.blit(image, (0, 0))
        return draw.round_corners(Canvas(layer, scale), self.theme.radius.md)

    def _gradient(self, surface: Canvas) -> Canvas:
        size = surface.px_rect(SV).size
        key = (round(self.color.h, 1), size)
        if self._sv_cache is None or self._sv_cache[0] != key:
            self._sv_cache = (key, self._rounded(sv_gradient(self.color.h, size), surface.scale))
        return self._sv_cache[1]

    def _hue_strip(self, surface: Canvas) -> Canvas:
        size = surface.px_rect(HUE).size
        if self._hue_cache is None or self._hue_cache[0] != size:
            self._hue_cache = (size, self._rounded(hue_gradient(size), surface.scale))
        return self._hue_cache[1]

    def _draw_picker(self, surface: Canvas, t: Theme) -> None:
        p = t.palette
        surface.blit(self._gradient(surface), SV.topleft)
        surface.blit(self._hue_strip(surface), HUE.topleft)
        c = self.color
        knob = (SV.x + c.s * SV.width, SV.y + (1 - c.v) * SV.height)
        ring = BLACK if c.v > 0.6 and c.s < 0.4 else WHITE
        gfx.circle(surface, self.rgb, knob, 9)
        gfx.circle(surface, ring, knob, 10, 3)
        hy = HUE.y + c.h / 360 * HUE.height
        bar = pygame.Rect(HUE.x - 4, round(hy) - 5, HUE.width + 8, 10)
        draw.rounded_rect(surface, bar, HSV(c.h, 1, 1).to_rgb(), 5)
        draw.rounded_rect(surface, bar, WHITE, 5, 3)
        draw.rounded_rect(surface, bar.inflate(2, 2), p.border, 6, 1)

    def _draw_values(self, surface: Canvas, t: Theme) -> None:
        p = t.palette
        rgb = self.rgb
        draw.shadow(surface, SWATCH, t.radius.lg, p.shadow, (0, 6), 14)
        draw.rounded_rect(surface, SWATCH, rgb, t.radius.lg)
        draw.rounded_rect(surface, SWATCH, p.border, t.radius.lg, 1)
        draw.text(
            surface,
            to_hex(rgb),
            t.font(t.size.title, "bold"),
            readable_on(rgb),
            (SWATCH.x + 18, SWATCH.bottom - 18),
            "bottomleft",
        )
        self.hex_input.draw(surface)
        if self.hex_input.focused and parse_hex(self.hex_input.text) is None:
            draw.text(
                surface, "Type 6 hex digits", t.font(t.size.caption), p.danger, (SWATCH.x, 312)
            )

        label_font = t.font(t.size.caption, "semibold")
        value_font = t.font(t.size.body, "medium")
        for name, text, button in zip(
            ("HEX", "RGB", "HSL"),
            (to_hex(rgb), rgb_text(rgb), hsl_text(rgb)),
            self.copy_buttons,
            strict=True,
        ):
            row = pygame.Rect(VALUES_X, button.rect.y, button.rect.x - 12 - VALUES_X, 40)
            draw.rounded_rect(surface, row, p.surface, t.radius.md)
            draw.text(surface, name, label_font, p.text_muted, (row.x + 14, row.centery), "midleft")
            draw.text(surface, text, value_font, p.text, (row.x + 64, row.centery), "midleft")
            button.draw(surface)

        for name, slider, value in zip("RGB", self.sliders, rgb, strict=True):
            cy = slider.rect.centery
            draw.text(surface, name, label_font, p.text_muted, (VALUES_X, cy), "midleft")
            slider.draw(surface)
            draw.text(surface, str(value), value_font, p.text, (1232, cy), "midright")

        draw.text(surface, "TEXT CONTRAST", label_font, p.text_muted, (SWATCH.x, 324), "midleft")
        for i, fg in enumerate((WHITE, BLACK)):
            chip = pygame.Rect(SWATCH.x + i * 124, 340, 116, 72)
            draw.rounded_rect(surface, chip, rgb, t.radius.md)
            if contrast(rgb, p.bg) < 1.3:  # keep the chip's edge visible on the background
                draw.rounded_rect(surface, chip, p.border, t.radius.md, 1)
            ratio = contrast(rgb, fg)
            draw.text(surface, "Aa", t.font(t.size.title, "bold"), fg, (chip.x + 12, chip.y + 10))
            draw.text(
                surface,
                f"{ratio:.1f}:1",
                t.font(t.size.caption, "semibold"),
                fg,
                (chip.right - 10, chip.y + 16),
                "topright",
            )
            draw.text(
                surface,
                wcag_grade(ratio),
                t.font(t.size.caption),
                fg,
                (chip.x + 12, chip.bottom - 10),
                "bottomleft",
            )

    def _draw_palette(self, surface: Canvas, t: Theme) -> None:
        p = t.palette
        draw_panel(surface, PALETTE, t)
        draw.text(
            surface,
            "Palette",
            t.font(t.size.title, "bold"),
            p.text,
            (PALETTE.x + 24, PALETTE.y + 40),
            "midleft",
        )
        self.tabs.draw(surface)
        self.random_btn.draw(surface)
        mouse = mouse_pos()
        font = t.font(t.size.label, "semibold")
        for i, (rgb, rect) in enumerate(zip(self._palette(), self._palette_rects(), strict=True)):
            lift = 3 if rect.collidepoint(mouse) else 0
            shown = rect.move(0, -lift)
            draw.shadow(surface, shown, t.radius.md, p.shadow, (0, 2 + lift), 6 + lift * 2)
            draw.rounded_rect(surface, shown, rgb, t.radius.md)
            draw.rounded_rect(surface, shown, p.border, t.radius.md, 1)
            draw.text(
                surface,
                str(i + 1),
                t.font(t.size.caption, "semibold"),
                readable_on(rgb),
                (shown.x + 12, shown.y + 10),
            )
            draw.text(surface, to_hex(rgb), font, p.text, (rect.x + 2, rect.bottom + 12))
            draw.text(
                surface,
                "{}, {}, {}".format(*rgb),
                t.font(t.size.caption),
                p.text_muted,
                (rect.right - 2, rect.bottom + 14),
                "topright",
            )
