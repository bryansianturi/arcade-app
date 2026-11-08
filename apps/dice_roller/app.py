"""Dice Roller UI: build a pool of dice and roll it, or flip a coin."""

from __future__ import annotations

import math
import random

import pygame

from apps.dice_roller.logic import (
    DIE_SIDES,
    MAX_DICE,
    CoinStats,
    Pool,
    Roll,
    Side,
    flip,
    parse_notation,
    roll,
)
from core import draw, gfx
from core.base_app import BaseApp
from core.canvas import Canvas, mouse_pos
from core.input import is_action
from core.registry import register_app
from core.theme import Color, Theme, lerp_color, readable_on
from core.widgets import Button, SegmentedControl, TextInput, draw_panel

ACCENT: Color = (180, 83, 9)
DIE_COLORS: dict[int, Color] = {
    4: (220, 38, 38),
    6: (217, 119, 6),
    8: (22, 163, 74),
    10: (2, 132, 199),
    12: (124, 58, 237),
    20: (219, 39, 119),
}
OTHER_DIE: Color = (71, 85, 105)
BUILDER = pygame.Rect(48, 92, 360, 584)
TRAY = pygame.Rect(432, 92, 500, 584)
HISTORY = pygame.Rect(956, 92, 276, 584)
ROLL_SECONDS = 0.7
FLIP_SECONDS = 1.0
HISTORY_SIZE = 12
GOLD: Color = (234, 179, 8)
SILVER: Color = (148, 163, 184)


def die_points(
    sides: int, center: tuple[float, float], r: float, angle: float = 0.0
) -> list[tuple[float, float]]:
    """Outline of a die seen from above; ``[]`` means draw a rounded square (d6) or a circle."""
    shapes: dict[int, list[tuple[float, float]]] = {
        4: [(0, -1), (0.95, 0.75), (-0.95, 0.75)],
        8: [(0, -1.05), (0.95, 0), (0, 1.05), (-0.95, 0)],
        10: [(0, -1.05), (1, 0.15), (0, 0.9), (-1, 0.15)],
        12: [(math.sin(a), -math.cos(a)) for a in (i * math.tau / 5 for i in range(5))],
        20: [(math.sin(a), -math.cos(a)) for a in (i * math.tau / 6 for i in range(6))],
    }
    unit = shapes.get(sides, [])
    cos, sin = math.cos(angle), math.sin(angle)
    return [
        (center[0] + r * (x * cos - y * sin), center[1] + r * (x * sin + y * cos)) for x, y in unit
    ]


def draw_die(
    surface: Canvas,
    theme: Theme,
    sides: int,
    value: int | str,
    center: tuple[float, float],
    r: float,
    angle: float = 0.0,
) -> None:
    color = DIE_COLORS.get(sides, OTHER_DIE)
    shade = lerp_color(color, (0, 0, 0), 0.25)
    points = die_points(sides, center, r, angle)
    shadow_at = (center[0], center[1] + r * 0.08)
    if sides == 6:
        side = round(r * 1.55)
        box = pygame.Rect(0, 0, side, side)
        box.center = (round(center[0]), round(center[1]))
        draw.rounded_rect(surface, box.move(0, round(r * 0.08)), shade, round(r * 0.3))
        draw.rounded_rect(surface, box, color, round(r * 0.3))
    elif points:
        gfx.polygon(surface, shade, die_points(sides, shadow_at, r, angle))
        gfx.polygon(surface, color, points)
        gfx.polygon(surface, lerp_color(color, (255, 255, 255), 0.25), points, 2)
    else:
        gfx.circle(surface, shade, shadow_at, r)
        gfx.circle(surface, color, center, r)
    size = max(12, round(r * (0.62 if sides != 4 else 0.5)))
    y = center[1] + (r * 0.22 if sides == 4 else 0)
    draw.text(
        surface, str(value), theme.font(size, "bold"), readable_on(color), (center[0], y), "center"
    )


@register_app
class DiceRollerApp(BaseApp):
    """Roll a pool of dice with a modifier, or flip coins and watch the streaks."""

    @classmethod
    def draw_icon(cls, surface: Canvas, rect: pygame.Rect, theme: Theme) -> None:
        draw.rounded_rect(surface, rect, ACCENT, theme.radius.md)
        side = round(rect.width * 0.46)
        for dx, dy, pips in ((-0.12, -0.1, (0, 4, 8)), (0.14, 0.12, (0, 2, 4, 6, 8))):
            box = pygame.Rect(0, 0, side, side)
            box.center = (
                round(rect.centerx + dx * rect.width),
                round(rect.centery + dy * rect.height),
            )
            draw.rounded_rect(surface, box, (255, 255, 255), max(2, side // 5))
            draw.rounded_rect(
                surface, box, lerp_color(ACCENT, (0, 0, 0), 0.2), max(2, side // 5), 1
            )
            for pip in pips:
                px = box.x + side * (0.25 + 0.25 * (pip % 3))
                py = box.y + side * (0.25 + 0.25 * (pip // 3))
                gfx.circle(surface, ACCENT, (px, py), side * 0.08)

    # ------------------------------------------------------------------ lifecycle
    def on_enter(self) -> None:
        t = self.theme
        self.rng = random.Random()
        self.pool = Pool.from_dict(self.data.get("pool"))
        if not self.pool.size:
            self.pool.add(6, 2)
        raw = self.data.get("history")
        loaded = [Roll.from_dict(r) for r in raw] if isinstance(raw, list) else []
        self.history: list[Roll] = [r for r in loaded if r is not None][:HISTORY_SIZE]
        self.coins = CoinStats()
        self.tab = 1 if self.data.get("tab") == 1 else 0
        self.tabs = SegmentedControl(
            t, (1232 - 240, 30, 240, 40), ["Dice", "Coin"], self.tab, self._set_tab, accent=ACCENT
        )
        self.die_buttons: list[tuple[int, pygame.Rect]] = []
        for i, sides in enumerate(DIE_SIDES):
            x = BUILDER.x + 24 + (i % 3) * 108
            y = BUILDER.y + 64 + (i // 3) * 112
            self.die_buttons.append((sides, pygame.Rect(x, y, 96, 100)))
        mod_y = BUILDER.y + 316
        self.minus_btn = Button(
            t, (BUILDER.right - 24 - 132, mod_y, 44, 40), "−", lambda: self._nudge_modifier(-1)
        )
        self.plus_btn = Button(
            t, (BUILDER.right - 24 - 44, mod_y, 44, 40), "+", lambda: self._nudge_modifier(1)
        )
        self.notation_input = TextInput(
            t,
            (BUILDER.x + 24, BUILDER.y + 432, BUILDER.width - 48, 48),
            "Or type: 3d6+2, d20+d4…",
            max_length=40,
        )
        self.clear_btn = Button(
            t, (BUILDER.x + 24, BUILDER.bottom - 76, 120, 52), "Clear", self._clear
        )
        self.roll_btn = Button(
            t,
            (BUILDER.x + 156, BUILDER.bottom - 76, BUILDER.width - 180, 52),
            "Roll",
            self._roll,
            "primary",
            accent=ACCENT,
        )
        self.flip_btn = Button(
            t,
            (TRAY.centerx - 100, TRAY.bottom - 76, 200, 52),
            "Flip",
            self._flip,
            "primary",
            accent=ACCENT,
        )
        self.reset_coins_btn = Button(
            t,
            (HISTORY.x + 24, HISTORY.bottom - 68, HISTORY.width - 48, 44),
            "Reset tally",
            self._reset_coins,
            "ghost",
        )
        self.last: Roll | None = self.history[0] if self.history else None
        self.anim = 0.0  # seconds left of the current roll/flip animation
        self.spin_faces: list[int] = []
        self.face_timer = 0.0
        self.coin_side: Side = "heads"
        self.error = ""

    def on_exit(self) -> None:
        self.data["pool"] = self.pool.to_dict()
        self.data["history"] = [r.to_dict() for r in self.history]
        self.data["tab"] = self.tab
        self.data.save()

    def restart(self) -> None:
        self.history.clear()
        self.last = None
        self._reset_coins()

    def _set_tab(self, index: int) -> None:
        self.tabs.index = index
        self.tab = index
        self.anim = 0.0

    # ------------------------------------------------------------------ actions
    def _roll(self) -> None:
        if not self.pool.size:
            self.error = "Add some dice first."
            return
        self.error = ""
        self.last = roll(self.pool, self.rng)
        self.history = [self.last, *self.history][:HISTORY_SIZE]
        self.anim = ROLL_SECONDS
        self._shuffle_faces()

    def _roll_typed(self) -> None:
        pool = parse_notation(self.notation_input.text)
        if pool is None:
            self.error = f"Try something like 3d6+2 (up to {MAX_DICE} dice)."
            return
        self.pool = pool
        self.notation_input.set_text("")
        self.notation_input.focused = False
        self._roll()

    def _clear(self) -> None:
        self.pool.clear()
        self.error = ""

    def _nudge_modifier(self, delta: int) -> None:
        self.pool.set_modifier(self.pool.modifier + delta)

    def _flip(self) -> None:
        if self.anim > 0:
            self.coins.record(self.coin_side)  # finish the flip in progress first
        self.coin_side = flip(self.rng)
        self.anim = FLIP_SECONDS

    def _reset_coins(self) -> None:
        self.coins = CoinStats()

    def _shuffle_faces(self) -> None:
        if self.last is not None:
            self.spin_faces = [self.rng.randint(1, sides) for sides, _ in self.last.dice]
        self.face_timer = 0.06

    def _widgets(self) -> list[Button | TextInput]:
        if self.tab == 0:
            return [
                self.minus_btn,
                self.plus_btn,
                self.notation_input,
                self.clear_btn,
                self.roll_btn,
            ]
        return [self.flip_btn, self.reset_coins_btn]

    # ------------------------------------------------------------------ input
    def uses_text_input(self) -> bool:
        return self.tab == 0 and self.notation_input.focused

    def handle_event(self, event: pygame.event.Event) -> None:
        if self.uses_text_input() and is_action(event, "action", repeat=False):
            self._roll_typed()
            return
        if self.tabs.handle_event(event):
            return
        for widget in self._widgets():
            if widget.handle_event(event):
                return
        if self.tab == 0 and event.type == pygame.MOUSEBUTTONDOWN:
            for sides, rect in self.die_buttons:
                if rect.collidepoint(event.pos):
                    if event.button == 1:
                        self.error = "" if self.pool.add(sides) else f"Up to {MAX_DICE} dice."
                    elif event.button == 3:
                        self.pool.remove(sides)
                    return
        if is_action(event, "action", repeat=False):
            if self.tab == 0:
                self._roll()
            else:
                self._flip()
        elif is_action(event, "left") or is_action(event, "right"):
            self._set_tab(1 - self.tab)
        elif self.tab == 0 and (is_action(event, "up") or is_action(event, "down")):
            self._nudge_modifier(1 if is_action(event, "up") else -1)
        elif event.type == pygame.KEYDOWN and self.tab == 0:
            if pygame.K_1 <= event.key < pygame.K_1 + len(DIE_SIDES):
                sides = DIE_SIDES[event.key - pygame.K_1]
                if event.mod & pygame.KMOD_SHIFT:
                    self.pool.remove(sides)
                else:
                    self.pool.add(sides)
            elif event.key in (pygame.K_BACKSPACE, pygame.K_DELETE):
                self._clear()

    def update(self, dt: float) -> None:
        self.tabs.update(dt)
        for widget in self._widgets():
            widget.update(dt)
        if self.anim > 0:
            self.anim = max(0.0, self.anim - dt)
            self.face_timer -= dt
            if self.face_timer <= 0:
                self._shuffle_faces()
            if self.anim == 0 and self.tab == 1:
                self.coins.record(self.coin_side)
        self.roll_btn.enabled = self.pool.size > 0

    # ------------------------------------------------------------------ drawing
    def draw(self, surface: Canvas) -> None:
        t = self.theme
        p = t.palette
        surface.fill(p.bg)
        draw.text(surface, "Dice Roller", t.font(t.size.heading, "bold"), p.text, (48, 30))
        self.tabs.draw(surface)
        if self.tab == 0:
            self._draw_builder(surface, t)
            self._draw_tray(surface, t)
            self._draw_history(surface, t)
            hint = (
                "Click a die to add · right-click (or Shift+1–6) to remove · 1–6 add · "
                "↑/↓ modifier · Space roll · Backspace clear"
            )
        else:
            self._draw_coin(surface, t)
            self._draw_coin_stats(surface, t)
            hint = "Space or click Flip · ←/→ switch to dice"
        draw.text(surface, hint, t.font(t.size.caption), p.text_muted, (640, 700), "center")

    def _draw_builder(self, surface: Canvas, t: Theme) -> None:
        p = t.palette
        draw_panel(surface, BUILDER, t)
        x = BUILDER.x + 24
        draw.text(surface, "Dice", t.font(t.size.title, "bold"), p.text, (x, BUILDER.y + 20))
        draw.text(
            surface,
            f"{self.pool.size}/{MAX_DICE}",
            t.font(t.size.label),
            p.text_muted,
            (BUILDER.right - 24, BUILDER.y + 34),
            "midright",
        )
        mouse = mouse_pos()
        for sides, rect in self.die_buttons:
            hover = rect.collidepoint(mouse)
            draw.rounded_rect(
                surface, rect, p.surface_hover if hover else p.surface_alt, t.radius.md
            )
            draw_die(surface, t, sides, sides, (rect.centerx, rect.y + 40), 24)
            draw.text(
                surface,
                f"d{sides}",
                t.font(t.size.label, "semibold"),
                p.text,
                (rect.centerx, rect.bottom - 16),
                "center",
            )
            count = self.pool.counts.get(sides, 0)
            if count:
                badge = pygame.Rect(rect.right - 30, rect.y - 8, 34, 26)
                draw.rounded_rect(surface, badge, ACCENT, 13)
                draw.text(
                    surface,
                    f"×{count}",
                    t.font(t.size.caption, "bold"),
                    readable_on(ACCENT),
                    badge.center,
                    "center",
                )

        mod_y = self.minus_btn.rect.centery
        draw.text(surface, "Modifier", t.font(t.size.body), p.text, (x, mod_y), "midleft")
        m = self.pool.modifier
        draw.text(
            surface,
            f"{m:+d}" if m else "0",
            t.font(t.size.title, "bold"),
            p.text,
            (self.minus_btn.rect.right + 22, mod_y),
            "center",
        )
        self.minus_btn.draw(surface)
        self.plus_btn.draw(surface)

        font = t.font(t.size.body, "semibold")
        lines = draw.wrap_text(self.pool.notation() or "No dice", font, BUILDER.width - 48)[:2]
        y = BUILDER.y + 372
        for line in lines:
            draw.text(surface, line, font, p.text, (x, y), "midleft")
            y += 22
        if self.pool.size:
            low, high = self.pool.bounds()
            draw.text(
                surface,
                f"Range {low}–{high} · average {self.pool.average():g}",
                t.font(t.size.caption),
                p.text_muted,
                (x, y + 2),
                "midleft",
            )
        self.notation_input.draw(surface)
        if self.error:
            draw.text(
                surface,
                self.error,
                t.font(t.size.caption),
                p.danger,
                (x, self.notation_input.rect.bottom + 14),
                "midleft",
            )
        self.clear_btn.draw(surface)
        self.roll_btn.draw(surface)

    def _tray_layout(self, n: int) -> tuple[list[tuple[float, float]], float]:
        cols = min(4, n) if n != 5 and n != 6 else 3
        rows = math.ceil(n / cols)
        cell = min(112.0, (TRAY.width - 48) / cols, 360 / rows)
        top = TRAY.y + 64 + (380 - rows * cell) / 2
        centers = []
        for i in range(n):
            row, col = divmod(i, cols)
            in_row = min(cols, n - row * cols)
            left = TRAY.centerx - in_row * cell / 2
            centers.append((left + (col + 0.5) * cell, top + (row + 0.5) * cell))
        return centers, cell * 0.38

    def _draw_tray(self, surface: Canvas, t: Theme) -> None:
        p = t.palette
        draw_panel(surface, TRAY, t)
        if self.last is None:
            draw.text(
                surface,
                "Press Space or Roll",
                t.font(t.size.title),
                p.text_muted,
                TRAY.center,
                "center",
            )
            return
        rolling = self.anim > 0
        centers, r = self._tray_layout(len(self.last.dice))
        progress = 1 - self.anim / ROLL_SECONDS
        for i, ((sides, value), center) in enumerate(zip(self.last.dice, centers, strict=True)):
            shown: int | str = value
            angle = 0.0
            offset = 0.0
            if rolling:
                shown = self.spin_faces[i] if i < len(self.spin_faces) else value
                wobble = (1 - progress) ** 2
                angle = math.sin(progress * 18 + i * 1.7) * 0.5 * wobble
                offset = -abs(math.sin(progress * math.pi * 3 + i)) * 26 * wobble
            draw_die(surface, t, sides, shown, (center[0], center[1] + offset), r, angle)

        total_y = TRAY.bottom - 110
        if rolling:
            draw.text(
                surface,
                "…",
                t.font(t.size.display, "bold"),
                p.text_muted,
                (TRAY.centerx, total_y),
                "center",
            )
            return
        draw.text(
            surface,
            str(self.last.total),
            t.font(64, "bold"),
            p.text,
            (TRAY.centerx, total_y),
            "center",
        )
        parts = " + ".join(str(v) for _, v in self.last.dice)
        if self.last.modifier:
            parts += f" {'-' if self.last.modifier < 0 else '+'} {abs(self.last.modifier)}"
        font = t.font(t.size.label)
        draw.text(
            surface,
            draw.fit_text(parts, font, TRAY.width - 48),
            font,
            p.text_muted,
            (TRAY.centerx, total_y + 52),
            "center",
        )

    def _draw_history(self, surface: Canvas, t: Theme) -> None:
        p = t.palette
        draw_panel(surface, HISTORY, t)
        draw.text(
            surface,
            "History",
            t.font(t.size.title, "bold"),
            p.text,
            (HISTORY.x + 24, HISTORY.y + 20),
        )
        if not self.history:
            draw.text(
                surface,
                "Your rolls show up here.",
                t.font(t.size.caption),
                p.text_muted,
                (HISTORY.x + 24, HISTORY.y + 64),
            )
            return
        start = 1 if self.anim > 0 else 0  # don't spoil the roll in progress
        font = t.font(t.size.label)
        for i, item in enumerate(self.history[start : start + 11]):
            y = HISTORY.y + 76 + i * 44
            draw.text(
                surface,
                draw.fit_text(item.notation, font, HISTORY.width - 110),
                font,
                p.text_muted,
                (HISTORY.x + 24, y),
                "midleft",
            )
            draw.text(
                surface,
                str(item.total),
                t.font(t.size.body, "bold"),
                p.text if i or start else ACCENT,
                (HISTORY.right - 24, y),
                "midright",
            )

    def _draw_coin(self, surface: Canvas, t: Theme) -> None:
        p = t.palette
        area = pygame.Rect(48, 92, HISTORY.x - 24 - 48, 584)
        draw_panel(surface, area, t)
        cx, cy, r = area.centerx, area.y + 220, 130
        # Spin: the coin's width follows |cos| of its turning angle; it lands on coin_side.
        progress = 1 - self.anim / FLIP_SECONDS if self.anim > 0 else 1.0
        turns = 6 + (1 if self.coin_side == "tails" else 0)
        angle = (1 - (1 - progress) ** 3) * turns * math.pi
        width = abs(math.cos(angle))
        face: Side = "heads" if round(angle / math.pi) % 2 == 0 else "tails"
        lift = math.sin(progress * math.pi) * 90 if self.anim > 0 else 0
        coin_y = cy - lift
        shadow_w = r * 2 * (1 - lift / 300)
        gfx.ellipse(
            surface,
            lerp_color(p.surface, (0, 0, 0), 0.25),
            pygame.Rect(cx - shadow_w / 2, cy + r + 18, shadow_w, 18),
        )
        if self.coins.total == 0 and self.anim == 0:
            face = "heads"
        base = GOLD if face == "heads" else SILVER
        rim = lerp_color(base, (0, 0, 0), 0.25)
        w = max(4.0, r * 2 * width)
        gfx.ellipse(surface, rim, pygame.Rect(cx - w / 2, coin_y - r + 6, w, r * 2))
        gfx.ellipse(surface, base, pygame.Rect(cx - w / 2, coin_y - r, w, r * 2))
        inner = max(2.0, (r - 14) * 2 * width)
        gfx.ellipse(
            surface,
            lerp_color(base, (255, 255, 255), 0.25),
            pygame.Rect(cx - inner / 2, coin_y - r + 14, inner, (r - 14) * 2),
            3,
        )
        if width > 0.35:
            label = "H" if face == "heads" else "T"
            draw.text(
                surface, label, t.font(round(96 * width) or 1, "bold"), rim, (cx, coin_y), "center"
            )
        if self.anim == 0 and self.coins.total:
            draw.text(
                surface,
                self.coin_side.capitalize(),
                t.font(t.size.display, "bold"),
                p.text,
                (cx, area.bottom - 128),
                "center",
            )
        self.flip_btn.rect.centerx = cx
        self.flip_btn.draw(surface)

    def _draw_coin_stats(self, surface: Canvas, t: Theme) -> None:
        p = t.palette
        draw_panel(surface, HISTORY, t)
        x = HISTORY.x + 24
        draw.text(surface, "Tally", t.font(t.size.title, "bold"), p.text, (x, HISTORY.y + 20))
        c = self.coins
        rows: list[tuple[str, str]] = [
            ("Heads", f"{c.heads}  ({c.share('heads'):.0%})"),
            ("Tails", f"{c.tails}  ({c.share('tails'):.0%})"),
            ("Flips", str(c.total)),
            ("Streak", f"{c.streak} {c.streak_side or ''}".strip() if c.streak else "—"),
            ("Longest", str(c.best_streak) if c.best_streak else "—"),
        ]
        for i, (name, value) in enumerate(rows):
            y = HISTORY.y + 80 + i * 40
            draw.text(surface, name, t.font(t.size.label), p.text_muted, (x, y), "midleft")
            draw.text(
                surface,
                value,
                t.font(t.size.body, "semibold"),
                p.text,
                (HISTORY.right - 24, y),
                "midright",
            )
        bar = pygame.Rect(x, HISTORY.y + 290, HISTORY.width - 48, 10)
        draw.rounded_rect(surface, bar, SILVER if c.total else p.surface_alt, 5)
        if c.heads:
            draw.rounded_rect(
                surface,
                pygame.Rect(bar.x, bar.y, round(bar.width * c.share("heads")), bar.height),
                GOLD,
                5,
            )
        draw.text(
            surface,
            "Recent",
            t.font(t.size.caption, "semibold"),
            p.text_muted,
            (x, HISTORY.y + 330),
        )
        for i, side in enumerate(c.recent):
            col, row = i % 8, i // 8
            center = (x + 12 + col * 28, HISTORY.y + 368 + row * 28)
            gfx.circle(surface, GOLD if side == "heads" else SILVER, center, 11)
            draw.text(
                surface,
                side[0].upper(),
                t.font(t.size.caption, "bold"),
                lerp_color(GOLD if side == "heads" else SILVER, (0, 0, 0), 0.45),
                center,
                "center",
            )
        self.reset_coins_btn.draw(surface)
