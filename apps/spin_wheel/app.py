"""Spin Wheel UI: the wheel with a ticking pointer, an options list and a winner card."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

import pygame

from apps.spin_wheel.logic import MAX_LABEL, MAX_OPTIONS, TAU, Wheel, clean_option
from core import draw, gfx
from core.base_app import BaseApp
from core.canvas import Canvas, mouse_pos
from core.input import is_action
from core.registry import register_app
from core.theme import Color, Theme, lerp_color, readable_on
from core.widgets import Button, TextInput, Toggle, draw_panel

ACCENT: Color = (219, 39, 119)
CENTER = (430, 396)
RADIUS = 262
HUB_R = 52
PANEL = pygame.Rect(780, 92, 452, 584)
LIST_TOP, ROW_H, VISIBLE_ROWS = PANEL.y + 140, 34, 9
SLICE_COLORS: tuple[Color, ...] = (
    (236, 72, 153),
    (249, 115, 22),
    (234, 179, 8),
    (34, 197, 94),
    (20, 184, 166),
    (59, 130, 246),
    (99, 102, 241),
    (168, 85, 247),
    (244, 63, 94),
    (14, 165, 233),
)


def slice_color(i: int, n: int) -> Color:
    """Cycle the palette, never giving the last slice the first slice's color."""
    k = len(SLICE_COLORS)
    if i == n - 1 and n > 1 and i % k == 0:
        return SLICE_COLORS[(i + 3) % k]
    return SLICE_COLORS[i % k]


def on_wheel(a: float, r: float) -> tuple[float, float]:
    """Screen point at angle ``a`` (clockwise from the top) and radius ``r``."""
    return CENTER[0] + r * math.sin(a), CENTER[1] - r * math.cos(a)


@dataclass
class Confetto:
    x: float
    y: float
    vx: float
    vy: float
    spin: float
    angle: float
    color: Color
    life: float


@register_app
class SpinWheelApp(BaseApp):
    """Type some options, spin the wheel, get an answer."""

    @classmethod
    def draw_icon(cls, surface: Canvas, rect: pygame.Rect, theme: Theme) -> None:
        draw.rounded_rect(surface, rect, ACCENT, theme.radius.md)
        cx, cy = rect.centerx, rect.centery + rect.height * 0.04
        r = rect.width * 0.34
        for i in range(6):
            a0, a1 = i * TAU / 6, (i + 1) * TAU / 6
            points = [(cx, cy)] + [
                (cx + r * math.sin(a), cy - r * math.cos(a))
                for a in (a0 + (a1 - a0) * k / 6 for k in range(7))
            ]
            gfx.polygon(surface, (255, 255, 255) if i % 2 else (253, 186, 216), points)
        gfx.circle(surface, ACCENT, (cx, cy), r * 0.22)
        tip = rect.y + rect.height * 0.2
        gfx.polygon(surface, (255, 255, 255), [(cx - 6, tip - 8), (cx + 6, tip - 8), (cx, tip + 4)])

    # ------------------------------------------------------------------ lifecycle
    def on_enter(self) -> None:
        t = self.theme
        self.rng = random.Random()
        saved = self.data.get("options")
        self.wheel = Wheel()
        if isinstance(saved, list):
            options = [clean_option(o) for o in saved if isinstance(o, str)]
            self.wheel.options = [o for o in options if o][:MAX_OPTIONS]
        self.remove_winner = self.data.get("remove_winner") is True
        x = PANEL.x + 24
        self.option_input = TextInput(
            t, (x, PANEL.y + 72, PANEL.width - 48 - 96, 48), "Add an option", max_length=MAX_LABEL
        )
        self.add_btn = Button(
            t,
            (PANEL.right - 24 - 84, PANEL.y + 72, 84, 48),
            "Add",
            self._add,
            "primary",
            accent=ACCENT,
        )
        self.remove_toggle = Toggle(
            t,
            (PANEL.right - 24 - Toggle.WIDTH, PANEL.bottom - 108),
            self.remove_winner,
            self._set_remove,
            accent=ACCENT,
        )
        self.clear_btn = Button(
            t, (x, PANEL.bottom - 64, 120, 40), "Clear all", self._clear, "ghost"
        )
        self.spin_btn = Button(
            t,
            (PANEL.right - 24 - 160, PANEL.bottom - 64, 160, 40),
            "Spin",
            self._spin,
            "primary",
            accent=ACCENT,
        )
        self.scroll = 0
        self.showing_result = False
        self.pending_removal: int | None = None
        self.last_slice = self.wheel.under_pointer()
        self.kick = 0.0  # pointer flick when a slice boundary passes it
        self.confetti: list[Confetto] = []
        self.time = 0.0
        self.result_t = 0.0

    def on_exit(self) -> None:
        self._apply_removal()
        self.data["options"] = self.wheel.options
        self.data["remove_winner"] = self.remove_winner
        self.data.save()

    def restart(self) -> None:
        self.showing_result = False
        self.pending_removal = None
        self.confetti.clear()

    def _save(self) -> None:
        self.data["options"] = self.wheel.options
        self.data["remove_winner"] = self.remove_winner
        self.data.save()

    # ------------------------------------------------------------------ actions
    def _add(self) -> None:
        self._apply_removal()
        if self.wheel.add(self.option_input.text):
            self.option_input.set_text("")
            self.scroll = max(0, len(self.wheel.options) - VISIBLE_ROWS)
            self._save()
        self.option_input.focus()

    def _remove(self, index: int) -> None:
        self._apply_removal()
        if self.wheel.remove(index):
            self.scroll = max(0, min(self.scroll, len(self.wheel.options) - VISIBLE_ROWS))
            self._save()

    def _clear(self) -> None:
        self.wheel.clear()
        self.pending_removal = None
        self.showing_result = False
        self.scroll = 0
        self._save()

    def _set_remove(self, on: bool) -> None:
        self.remove_winner = on
        self._save()

    def _apply_removal(self) -> None:
        """In "remove the winner" mode, the last winner leaves before anything else happens."""
        if self.pending_removal is not None:
            index, self.pending_removal = self.pending_removal, None
            self.showing_result = False
            self.wheel.remove(index)
            self._save()

    def _spin(self) -> None:
        if self.wheel.spinning:
            return
        self._apply_removal()
        self.showing_result = False
        if self.wheel.spin(self.rng) is not None:
            self.option_input.focused = False
            self.confetti.clear()

    def _on_stop(self) -> None:
        self.showing_result = True
        self.result_t = 0.0
        if self.remove_winner:
            self.pending_removal = self.wheel.winner
        for _ in range(90):
            a = self.rng.uniform(0, TAU)
            speed = self.rng.uniform(180, 520)
            self.confetti.append(
                Confetto(
                    CENTER[0],
                    CENTER[1] - 40,
                    math.cos(a) * speed,
                    math.sin(a) * speed - 260,
                    self.rng.uniform(-8, 8),
                    self.rng.uniform(0, TAU),
                    self.rng.choice(SLICE_COLORS),
                    self.rng.uniform(1.4, 2.4),
                )
            )

    # ------------------------------------------------------------------ input
    def _row_rect(self, i: int) -> pygame.Rect:
        return pygame.Rect(
            PANEL.x + 16, LIST_TOP + (i - self.scroll) * ROW_H, PANEL.width - 32, ROW_H - 4
        )

    def _remove_rect(self, row: pygame.Rect) -> pygame.Rect:
        return pygame.Rect(row.right - 34, row.centery - 13, 26, 26)

    def uses_text_input(self) -> bool:
        return self.option_input.focused

    def handle_event(self, event: pygame.event.Event) -> None:
        if self.option_input.focused and is_action(event, "action", repeat=False):
            if self.option_input.text.strip():
                self._add()
            else:
                self.option_input.focused = False
            return
        for widget in (self.add_btn, self.remove_toggle, self.clear_btn, self.spin_btn):
            if widget.handle_event(event):
                return
        if self.option_input.handle_event(event):
            return
        if event.type == pygame.TEXTINPUT and event.text.strip() and not self.wheel.spinning:
            self.option_input.focus()  # start typing anywhere to add an option
            self.option_input.set_text(self.option_input.text + event.text)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if math.dist(event.pos, CENTER) <= RADIUS:
                self._spin()
                return
            for i in range(self.scroll, min(len(self.wheel.options), self.scroll + VISIBLE_ROWS)):
                row = self._row_rect(i)
                if self._remove_rect(row).collidepoint(event.pos):
                    self._remove(i)
                    return
        elif event.type == pygame.MOUSEWHEEL and PANEL.collidepoint(mouse_pos()):
            top = max(0, len(self.wheel.options) - VISIBLE_ROWS)
            self.scroll = max(0, min(top, self.scroll - event.y))
        elif is_action(event, "action", repeat=False):
            self._spin()
        elif event.type == pygame.KEYDOWN and event.key in (pygame.K_TAB, pygame.K_a):
            self.option_input.focus()

    def update(self, dt: float) -> None:
        self.time += dt
        self.result_t += dt
        if self.wheel.update(dt):
            self._on_stop()
        current = self.wheel.under_pointer()
        if current != self.last_slice:
            self.last_slice = current
            self.kick = 1.0
        self.kick = max(0.0, self.kick - dt * 7)
        for c in self.confetti:
            c.vy += 700 * dt
            c.vx *= 1 - 0.8 * dt
            c.x += c.vx * dt
            c.y += c.vy * dt
            c.angle += c.spin * dt
            c.life -= dt
        self.confetti = [c for c in self.confetti if c.life > 0 and c.y < 760]
        for widget in (
            self.option_input,
            self.add_btn,
            self.remove_toggle,
            self.clear_btn,
            self.spin_btn,
        ):
            widget.update(dt)
        idle = not self.wheel.spinning
        self.spin_btn.enabled = idle and len(self.wheel.options) >= 2
        self.add_btn.enabled = idle and len(self.wheel.options) < MAX_OPTIONS
        self.clear_btn.enabled = idle and bool(self.wheel.options)

    # ------------------------------------------------------------------ drawing
    def draw(self, surface: Canvas) -> None:
        t = self.theme
        p = t.palette
        surface.fill(p.bg)
        draw.text(surface, "Spin Wheel", t.font(t.size.heading, "bold"), p.text, (48, 30))
        self._draw_wheel(surface, t)
        self._draw_panel(surface, t)
        for c in self.confetti:
            w, h = 10, 5 * abs(math.cos(c.angle)) + 1
            corners = [(-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2)]
            sa, ca = math.sin(c.angle * 0.7), math.cos(c.angle * 0.7)
            gfx.polygon(
                surface,
                c.color,
                [(c.x + x * ca - y * sa, c.y + x * sa + y * ca) for x, y in corners],
            )
        if self.showing_result:
            self._draw_result(surface, t)
        hint = (
            "Space or click the wheel to spin · type to add an option · Enter add · "
            "hover an option to remove it"
        )
        draw.text(surface, hint, t.font(t.size.caption), p.text_muted, (640, 700), "center")

    def _draw_wheel(self, surface: Canvas, t: Theme) -> None:
        p = t.palette
        options = self.wheel.options
        n = len(options)
        draw.shadow(
            surface,
            pygame.Rect(CENTER[0] - RADIUS, CENTER[1] - RADIUS, 2 * RADIUS, 2 * RADIUS),
            RADIUS,
            p.shadow,
            (0, 10),
            24,
        )
        gfx.circle(surface, p.surface, CENTER, RADIUS + 10)
        if n == 0:
            gfx.circle(surface, p.surface_alt, CENTER, RADIUS)
            draw.text(
                surface,
                "Add some options →",
                t.font(t.size.title),
                p.text_muted,
                (CENTER[0], CENTER[1] + 110),
                "center",
            )
        elif n == 1:
            gfx.circle(surface, slice_color(0, 1), CENTER, RADIUS)
        width = TAU / n if n else TAU
        highlight = self.wheel.winner if self.showing_result else None
        for i in range(n):
            a0 = self.wheel.angle + i * width
            steps = max(2, int(width / 0.05))
            color = slice_color(i, n)
            if highlight is not None and i != highlight:
                color = lerp_color(color, p.bg, 0.55)
            if n > 1:
                points = [CENTER] + [
                    on_wheel(a0 + width * k / steps, RADIUS) for k in range(steps + 1)
                ]
                gfx.polygon(surface, color, points)
        for i in range(n if n > 1 else 0):
            a = self.wheel.angle + i * width
            gfx.line(surface, p.surface, CENTER, on_wheel(a, RADIUS), 2)
        for i, label in enumerate(options):
            mid = self.wheel.angle + (i + 0.5) * width
            self._draw_label(surface, t, label, mid, slice_color(i, n), n)
        gfx.circle(surface, p.surface, CENTER, RADIUS + 10, 10)
        for k in range(36):
            gfx.circle(
                surface,
                lerp_color(p.surface, p.text_muted, 0.5),
                on_wheel(k * TAU / 36 + self.wheel.angle, RADIUS + 5),
                2,
            )

        hub_hover = math.dist(mouse_pos(), CENTER) <= HUB_R and not self.wheel.spinning
        gfx.circle(
            surface, lerp_color(p.surface, (0, 0, 0), 0.2), (CENTER[0], CENTER[1] + 3), HUB_R
        )
        gfx.circle(
            surface, lerp_color(ACCENT, (255, 255, 255), 0.12 if hub_hover else 0), CENTER, HUB_R
        )
        gfx.circle(surface, p.surface, CENTER, HUB_R, 4)
        draw.text(
            surface, "SPIN", t.font(t.size.title, "bold"), readable_on(ACCENT), CENTER, "center"
        )

        # The pointer, flicking back as each slice edge passes under it.
        tilt = -0.45 * self.kick
        tip = (CENTER[0], CENTER[1] - RADIUS + 22)
        base_y = CENTER[1] - RADIUS - 26
        pts = [(-18, base_y - tip[1]), (18, base_y - tip[1]), (0, 0)]
        rotated = [
            (
                tip[0] + x * math.cos(tilt) - y * math.sin(tilt),
                tip[1] + x * math.sin(tilt) + y * math.cos(tilt),
            )
            for x, y in pts
        ]
        gfx.polygon(surface, lerp_color(p.text, p.bg, 0.1), [(x, y + 3) for x, y in rotated])
        gfx.polygon(surface, ACCENT, rotated)
        gfx.circle(surface, p.surface, (tip[0], base_y + 2), 6)

    def _draw_label(
        self, surface: Canvas, t: Theme, label: str, mid: float, color: Color, n: int
    ) -> None:
        size = 20 if n <= 8 else 16 if n <= 14 else 13
        font = t.font(size, "bold")
        # Keep text in the slice's outer part: it narrows towards the hub.
        room = min(RADIUS - HUB_R - 36, round(RADIUS * 0.72))
        text = draw.fit_text(label, font, room)
        image = font.render(text, True, readable_on(color))
        # Text runs along the radius, reading outwards on the right half of the wheel.
        degrees = 90 - math.degrees(mid)
        angle_mod = mid % TAU
        flipped = angle_mod > math.pi
        if flipped:
            degrees += 180
        rotated = pygame.transform.rotozoom(image.surface, degrees, 1)  # smooth edges
        label_canvas = Canvas(rotated, image.scale)
        r = RADIUS - 24 - image.width / 2
        x, y = on_wheel(mid, r)
        surface.blit(label_canvas, (x - label_canvas.width / 2, y - label_canvas.height / 2))

    def _draw_panel(self, surface: Canvas, t: Theme) -> None:
        p = t.palette
        draw_panel(surface, PANEL, t)
        x = PANEL.x + 24
        draw.text(surface, "Options", t.font(t.size.title, "bold"), p.text, (x, PANEL.y + 22))
        draw.text(
            surface,
            f"{len(self.wheel.options)}/{MAX_OPTIONS}",
            t.font(t.size.label),
            p.text_muted,
            (PANEL.right - 24, PANEL.y + 36),
            "midright",
        )
        self.option_input.draw(surface)
        self.add_btn.draw(surface)
        options = self.wheel.options
        if not options:
            draw.text(
                surface,
                "Nothing on the wheel yet.",
                t.font(t.size.body),
                p.text_muted,
                (PANEL.centerx, LIST_TOP + 60),
                "center",
            )
        mouse = mouse_pos()
        font = t.font(t.size.label, "medium")
        for i in range(self.scroll, min(len(options), self.scroll + VISIBLE_ROWS)):
            row = self._row_rect(i)
            hover = row.collidepoint(mouse) and not self.wheel.spinning
            winner = self.showing_result and i == self.wheel.winner
            if hover or winner:
                draw.rounded_rect(surface, row, p.surface_hover, t.radius.sm)
            gfx.circle(surface, slice_color(i, len(options)), (row.x + 16, row.centery), 7)
            draw.text(
                surface,
                draw.fit_text(options[i], font, row.width - 80),
                font,
                p.text,
                (row.x + 34, row.centery),
                "midleft",
            )
            if hover:
                cross = self._remove_rect(row)
                over = cross.collidepoint(mouse)
                color = p.danger if over else p.text_muted
                (cx, cy), r = cross.center, 5
                draw.thick_line(surface, color, (cx - r, cy - r), (cx + r, cy + r), 2)
                draw.thick_line(surface, color, (cx - r, cy + r), (cx + r, cy - r), 2)
        if len(options) > VISIBLE_ROWS:
            draw.text(
                surface,
                f"Scroll for {len(options) - VISIBLE_ROWS} more",
                t.font(t.size.caption),
                p.text_muted,
                (PANEL.centerx, LIST_TOP + VISIBLE_ROWS * ROW_H + 6),
                "center",
            )
        toggle_y = self.remove_toggle.rect.centery
        draw.text(
            surface,
            "Remove the winner after each spin",
            t.font(t.size.label),
            p.text,
            (x, toggle_y),
            "midleft",
        )
        self.remove_toggle.draw(surface)
        self.clear_btn.draw(surface)
        self.spin_btn.draw(surface)

    def _draw_result(self, surface: Canvas, t: Theme) -> None:
        p = t.palette
        winner = self.wheel.winner
        if winner is None or winner >= len(self.wheel.options):
            return
        pop = min(1.0, self.result_t / 0.25)
        scale = 0.85 + 0.15 * (1 - (1 - pop) ** 3)
        label = self.wheel.options[winner]
        font = t.font(t.size.display, "bold")
        w = max(300, min(640, font.size(label)[0] + 80))
        card = pygame.Rect(0, 0, round(w * scale), round(132 * scale))
        card.center = CENTER
        color = slice_color(winner, len(self.wheel.options))
        draw.shadow(surface, card, t.radius.lg, p.shadow, (0, 8), 18)
        draw.rounded_rect(surface, card, color, t.radius.lg)
        fg = readable_on(color)
        draw.text(
            surface,
            "THE WHEEL SAYS",
            t.font(t.size.caption, "bold"),
            fg,
            (card.centerx, card.y + 26),
            "center",
        )
        draw.text(
            surface,
            draw.fit_text(label, font, card.width - 40),
            font,
            fg,
            (card.centerx, card.centery + 12),
            "center",
        )
