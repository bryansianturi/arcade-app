"""Mandelbrot Explorer UI: a progressively rendered view you zoom and drag, plus controls."""

from __future__ import annotations

import math
import time
from collections.abc import Callable, Iterator

import pygame

from apps.mandelbrot.logic import (
    PALETTES,
    PLACES,
    View,
    colour,
    escape_time,
    progressive_samples,
    suggested_iterations,
)
from core import draw, gfx
from core.base_app import BaseApp
from core.canvas import Canvas, mouse_pos
from core.input import is_action
from core.registry import register_app
from core.theme import Color, Theme, lerp_color
from core.widgets import Button, Slider, Toggle, draw_panel

ACCENT: Color = (67, 56, 202)
VIEW = pygame.Rect(48, 92, 880, 580)
SIDE = pygame.Rect(952, 92, 280, 584)
W, H = VIEW.size
FRAME_BUDGET = 0.010  # seconds of rendering per frame
WHEEL_ZOOM = 1.4
CLICK_SLOP = 4  # pixels the mouse may move and still count as a click
MIN_ITER, MAX_ITER = 50, 3000


@register_app
class MandelbrotApp(BaseApp):
    """Explore the Mandelbrot set: wheel or click to zoom, drag to pan."""

    @classmethod
    def draw_icon(cls, surface: Canvas, rect: pygame.Rect, theme: Theme) -> None:
        draw.rounded_rect(surface, rect, ACCENT, theme.radius.md)
        # The main cardioid (cusp to the right), its period-2 bulb and a tiny third disc.
        r = rect.width * 0.17
        cx, cy = rect.centerx + r * 0.7, rect.centery
        white = (255, 255, 255)
        points = []
        for i in range(64):
            a = i * math.tau / 64
            x = r * (2 * math.cos(a) - math.cos(2 * a)) / 2
            y = r * (2 * math.sin(a) - math.sin(2 * a)) / 2
            points.append((cx + x, cy + y))
        gfx.polygon(surface, white, points)
        gfx.circle(surface, white, (cx - r * 2.0, cy), r * 0.5)
        gfx.circle(surface, white, (cx - r * 2.75, cy), r * 0.2)

    # ------------------------------------------------------------------ lifecycle
    def on_enter(self) -> None:
        t = self.theme
        saved = self.data.get("palette")
        self.palette_index = saved if isinstance(saved, int) and 0 <= saved < len(PALETTES) else 0
        self.auto_iter = self.data.get("auto_iterations") is not False
        iterations = self.data.get("iterations")
        self.iterations = (
            iterations
            if isinstance(iterations, int) and MIN_ITER <= iterations <= MAX_ITER
            else 200
        )
        self.view = View()
        self.buffer = pygame.Surface((W, H))
        self.buffer.fill(PALETTES[self.palette_index].inside)
        self.samples: Iterator[tuple[int, int, int]] | None = None
        self.done_samples = 0
        self.render_started = 0.0
        self.render_seconds = 0.0
        self.press: tuple[int, int] | None = None  # where the left button went down
        self.drag = (0, 0)
        x = SIDE.x + 24
        self.auto_toggle = Toggle(
            t,
            (SIDE.right - 24 - Toggle.WIDTH, SIDE.y + 140),
            self.auto_iter,
            self._set_auto,
            accent=ACCENT,
        )
        self.iter_slider = Slider(
            t,
            (x - 6, SIDE.y + 174, 244, 28),
            MIN_ITER,
            MAX_ITER,
            self.iterations,
            self._set_iterations,
            step=10,
            accent=ACCENT,
        )
        self.palette_buttons = [
            Button(
                t,
                (x + (i % 2) * 120, SIDE.y + 240 + (i // 2) * 40, 112, 34),
                p.name,
                self._palette_setter(i),
                font_size=t.size.caption,
            )
            for i, p in enumerate(PALETTES)
        ]
        self.place_buttons = [
            Button(
                t,
                (x, SIDE.y + 348 + i * 38, 232, 32),
                place.name,
                self._place_setter(i),
                "ghost",
                font_size=t.size.caption,
            )
            for i, place in enumerate(PLACES)
        ]
        self._restart_render()

    def on_exit(self) -> None:
        self.data["palette"] = self.palette_index
        self.data["iterations"] = self.iterations
        self.data["auto_iterations"] = self.auto_iter
        self.data.save()

    def restart(self) -> None:
        self._go(View())

    def _widgets(self) -> list[Button | Slider | Toggle]:
        return [self.auto_toggle, self.iter_slider, *self.palette_buttons, *self.place_buttons]

    # ------------------------------------------------------------------ rendering
    @property
    def max_iter(self) -> int:
        return suggested_iterations(self.view) if self.auto_iter else self.iterations

    def _restart_render(self) -> None:
        self.samples = progressive_samples(W, H)
        self.done_samples = 0
        self.render_started = time.perf_counter()
        if self.auto_iter:
            self.iterations = min(MAX_ITER, self.max_iter)
            self.iter_slider.value = self.iterations

    def _render(self, budget: float) -> None:
        if self.samples is None:
            return
        deadline = time.perf_counter() + budget
        view, max_iter, palette = self.view, self.max_iter, PALETTES[self.palette_index]
        fill, set_at = self.buffer.fill, self.buffer.set_at
        scale, left, top = view.scale, view.cx - W / 2 * view.scale, view.cy + H / 2 * view.scale
        n = 0
        for x, y, block in self.samples:
            value = escape_time(left + (x + 0.5) * scale, top - (y + 0.5) * scale, max_iter)
            rgb = colour(value, palette)
            if block == 1:
                set_at((x, y), rgb)
            else:
                fill(rgb, (x, y, block, block))
            n += 1
            if n % 64 == 0 and time.perf_counter() > deadline:
                break
        else:
            self.samples = None
            self.render_seconds = time.perf_counter() - self.render_started
        self.done_samples += n

    def _go(self, view: View) -> None:
        """Switch to ``view``, keeping a stretched copy of the old picture as a preview."""
        old = self.view
        preview = pygame.Surface((W, H))
        preview.fill(PALETTES[self.palette_index].inside)
        ratio = old.scale / view.scale  # new pixels per old pixel
        # Where the old picture lands in the new one, clipped to what's visible...
        dest = pygame.FRect(
            (old.cx - view.cx) / view.scale + W / 2 - W * ratio / 2,
            (view.cy - old.cy) / view.scale + H / 2 - H * ratio / 2,
            W * ratio,
            H * ratio,
        )
        visible = dest.clip(pygame.FRect(0, 0, W, H))
        # ...and the part of the old picture that covers it (so scaling stays small).
        src = pygame.Rect(
            round((visible.x - dest.x) / ratio),
            round((visible.y - dest.y) / ratio),
            round(visible.width / ratio),
            round(visible.height / ratio),
        ).clip(self.buffer.get_rect())
        if src.width >= 1 and src.height >= 1 and visible.width >= 1 and visible.height >= 1:
            size = (round(visible.width), round(visible.height))
            stretched = pygame.transform.scale(self.buffer.subsurface(src), size)
            preview.blit(stretched, (round(visible.x), round(visible.y)))
        self.buffer = preview
        self.view = view
        self._restart_render()

    def _zoom_at(self, factor: float, pos: tuple[float, float]) -> None:
        x, y = pos[0] - VIEW.x, pos[1] - VIEW.y
        self._go(self.view.zoom(factor, x, y, W, H))

    # ------------------------------------------------------------------ controls
    def _set_auto(self, on: bool) -> None:
        self.auto_iter = on
        self._restart_render()

    def _set_iterations(self, value: float) -> None:
        self.iterations = int(value)
        self.auto_iter = self.auto_toggle.value = False
        self._restart_render()

    def _palette_setter(self, index: int) -> Callable[[], None]:
        def choose() -> None:
            self.palette_index = index
            self._restart_render()

        return choose

    def _place_setter(self, index: int) -> Callable[[], None]:
        return lambda: self._go(PLACES[index].view)

    # ------------------------------------------------------------------ input
    def handle_event(self, event: pygame.event.Event) -> None:
        for widget in self._widgets():
            if widget.handle_event(event):
                return
        if event.type == pygame.MOUSEWHEEL:
            pos = mouse_pos()
            if VIEW.collidepoint(pos) and event.y:
                self._zoom_at(WHEEL_ZOOM**event.y, pos)
        elif event.type == pygame.MOUSEBUTTONDOWN and VIEW.collidepoint(event.pos):
            if event.button == 1:
                self.press = event.pos
                self.drag = (0, 0)
            elif event.button == 3:
                self._zoom_at(0.5, event.pos)
        elif event.type == pygame.MOUSEMOTION and self.press is not None:
            self.drag = (event.pos[0] - self.press[0], event.pos[1] - self.press[1])
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1 and self.press is not None:
            dx, dy = self.drag
            if abs(dx) <= CLICK_SLOP and abs(dy) <= CLICK_SLOP:
                self._zoom_at(2.0, self.press)
            else:
                self._go(self.view.pan(dx, dy))
            self.press = None
            self.drag = (0, 0)
        elif is_action(event, "left") or is_action(event, "right"):
            self._go(self.view.pan(120 if is_action(event, "left") else -120, 0))
        elif is_action(event, "up") or is_action(event, "down"):
            self._go(self.view.pan(0, 120 if is_action(event, "up") else -120))
        elif is_action(event, "action", repeat=False):
            self._zoom_at(2.0, VIEW.center)
        elif event.type == pygame.KEYDOWN:
            self._shortcut(event)

    def _shortcut(self, event: pygame.event.Event) -> None:
        if event.key in (pygame.K_EQUALS, pygame.K_PLUS, pygame.K_KP_PLUS):
            self._zoom_at(2.0, VIEW.center)
        elif event.key in (pygame.K_MINUS, pygame.K_KP_MINUS, pygame.K_BACKSPACE):
            self._zoom_at(0.5, VIEW.center)
        elif event.key in (pygame.K_r, pygame.K_HOME):
            self._go(View())
        elif event.key == pygame.K_p:
            self._palette_setter((self.palette_index + 1) % len(PALETTES))()
        elif event.key in (pygame.K_LEFTBRACKET, pygame.K_RIGHTBRACKET):
            step = 50 if event.key == pygame.K_RIGHTBRACKET else -50
            self.iter_slider.set_value(self.iterations + step)

    def update(self, dt: float) -> None:
        for widget in self._widgets():
            widget.update(dt)
        if self.press is not None and not pygame.mouse.get_pressed()[0]:
            self.press = None
            self.drag = (0, 0)
        if self.press is None or self.drag == (0, 0):
            self._render(FRAME_BUDGET)
        for i, button in enumerate(self.palette_buttons):
            button.variant = "primary" if i == self.palette_index else "secondary"
            button.accent = ACCENT

    # ------------------------------------------------------------------ drawing
    def draw(self, surface: Canvas) -> None:
        t = self.theme
        p = t.palette
        surface.fill(p.bg)
        draw.text(surface, "Mandelbrot Explorer", t.font(t.size.heading, "bold"), p.text, (48, 30))
        draw.shadow(surface, VIEW, t.radius.md, p.shadow, (0, 6), 14)
        image = pygame.transform.scale(self.buffer, surface.px_rect(VIEW).size)
        layer = Canvas(image, surface.scale)
        if self.drag != (0, 0):
            surface.fill(PALETTES[self.palette_index].inside, VIEW)
            surface.set_clip(VIEW)
            surface.blit(layer, (VIEW.x + self.drag[0], VIEW.y + self.drag[1]))
            surface.set_clip(None)
        else:
            surface.blit(layer, VIEW.topleft)
        if self.view.at_limit:
            draw.text(
                surface,
                "Deepest zoom: doubles run out of precision here",
                t.font(t.size.caption, "semibold"),
                (255, 255, 255),
                (VIEW.centerx, VIEW.bottom - 18),
                "center",
            )
        self._draw_side(surface, t)
        hint = (
            "Wheel or click to zoom in · right-click to zoom out · drag to pan · "
            "arrows pan · Space/+ zoom · − out · P palette · [ ] iterations · R reset"
        )
        draw.text(surface, hint, t.font(t.size.caption), p.text_muted, (640, 696), "center")

    def _draw_side(self, surface: Canvas, t: Theme) -> None:
        p = t.palette
        draw_panel(surface, SIDE, t)
        x, right = SIDE.x + 24, SIDE.right - 24
        zoom = self.view.magnification()
        rows = (
            ("Zoom", f"×{zoom:,.0f}" if zoom < 1e6 else f"×{zoom:.2e}"),
            ("Real", f"{self.view.cx:+.10f}"),
            ("Imaginary", f"{self.view.cy:+.10f}"),
        )
        for i, (name, value) in enumerate(rows):
            y = SIDE.y + 24 + i * 24
            draw.text(surface, name, t.font(t.size.label), p.text_muted, (x, y), "midleft")
            draw.text(
                surface, value, t.font(t.size.label, "semibold"), p.text, (right, y), "midright"
            )
        total = W * H
        frac = min(1.0, self.done_samples / total)
        bar = pygame.Rect(x, SIDE.y + 98, 232, 6)
        draw.rounded_rect(surface, bar, p.surface_alt, 3)
        if frac > 0:
            draw.rounded_rect(
                surface,
                pygame.Rect(bar.x, bar.y, max(6, round(232 * frac)), 6),
                lerp_color(ACCENT, p.text, 0.25 if t.mode == "dark" else 0),
                3,
            )
        status = (
            f"Rendering… {frac:.0%}"
            if self.samples is not None
            else f"Done in {self.render_seconds:.1f} s"
        )
        draw.text(surface, status, t.font(t.size.caption), p.text_muted, (x, SIDE.y + 116))

        caption = t.font(t.size.caption, "semibold")
        draw.text(
            surface,
            "ITERATIONS",
            caption,
            p.text_muted,
            (x, self.auto_toggle.rect.centery),
            "midleft",
        )
        draw.text(
            surface,
            f"{self.max_iter}  Auto",
            t.font(t.size.caption),
            p.text_muted,
            (self.auto_toggle.rect.x - 10, self.auto_toggle.rect.centery),
            "midright",
        )
        self.auto_toggle.draw(surface)
        self.iter_slider.draw(surface)
        draw.text(surface, "PALETTE", caption, p.text_muted, (x, SIDE.y + 224), "midleft")
        for button in self.palette_buttons:
            button.draw(surface)
        draw.text(surface, "PLACES", caption, p.text_muted, (x, SIDE.y + 332), "midleft")
        for button in self.place_buttons:
            button.draw(surface)
