"""Echo Pads UI: four glowing pads around a hub that shows the round and whose turn it is."""

from __future__ import annotations

import random

import pygame

from apps.echo_pads.logic import MODES, PADS, EchoGame, Mode
from core import draw, gfx
from core.base_app import BaseApp
from core.canvas import Canvas
from core.input import Action, is_action
from core.registry import register_app
from core.theme import Color, Theme, lerp_color, with_alpha
from core.widgets import ButtonMenu, SegmentedControl, draw_panel

ACCENT: Color = (45, 212, 191)
PAD_COLORS: tuple[Color, ...] = (
    (45, 212, 191),  # up: teal
    (250, 204, 21),  # right: amber
    (167, 139, 250),  # down: violet
    (251, 113, 133),  # left: rose
)
PAD_ACTIONS: tuple[Action, ...] = ("up", "right", "down", "left")
CENTER = (780, 372)
PAD_SIZE = 168
PAD_OFFSET = 190
HUB_R = 84
FLASH_SECONDS = 0.2
SIDE_X = 80


def pad_rect(pad: int) -> pygame.Rect:
    dx, dy = ((0, -1), (1, 0), (0, 1), (-1, 0))[pad]
    rect = pygame.Rect(0, 0, PAD_SIZE, PAD_SIZE)
    rect.center = (CENTER[0] + dx * PAD_OFFSET, CENTER[1] + dy * PAD_OFFSET)
    return rect


@register_app
class EchoPadsApp(BaseApp):
    """Watch the pads light up, then play the pattern back. It grows every round."""

    @classmethod
    def draw_icon(cls, surface: Canvas, rect: pygame.Rect, theme: Theme) -> None:
        draw.rounded_rect(surface, rect, (15, 23, 42), theme.radius.md)
        s = rect.width * 0.26
        offsets = ((0, -1), (1, 0), (0, 1), (-1, 0))
        for i, (dx, dy) in enumerate(offsets):
            box = pygame.Rect(0, 0, round(s), round(s))
            box.center = (round(rect.centerx + dx * s * 1.1), round(rect.centery + dy * s * 1.1))
            color = PAD_COLORS[i] if i == 1 else lerp_color(PAD_COLORS[i], (15, 23, 42), 0.45)
            draw.rounded_rect(surface, box, color, max(3, box.width // 4))

    # ------------------------------------------------------------------ lifecycle
    def on_enter(self) -> None:
        mode = self.data.get("mode", "classic")
        self.mode: Mode = mode if mode in MODES else "classic"
        self.picker = SegmentedControl(
            self.theme,
            (SIDE_X, 196, 300, 40),
            ["Classic", "Shuffle"],
            MODES.index(self.mode),
            self._set_mode,
            accent=ACCENT,
        )
        self.time = 0.0
        self._new_game()

    def on_exit(self) -> None:
        self.data["mode"] = self.mode
        self.data.save()

    def restart(self) -> None:
        self._new_game()

    def _set_mode(self, index: int) -> None:
        self.mode = MODES[index]
        self._new_game()

    def _new_game(self) -> None:
        self.game = EchoGame(self.mode, random.Random())
        self.flash: dict[int, float] = {}  # pad → seconds of press flash left
        self.menu: ButtonMenu | None = None
        self.new_best = False

    def _start(self) -> None:
        if self.menu is None:
            self.game.start()

    def _press(self, pad: int) -> None:
        if self.menu is not None:
            return
        if self.game.state == "ready":
            self.game.start()
            return
        result = self.game.press(pad)
        if result is None:
            return
        self.flash[pad] = FLASH_SECONDS
        if result:
            if self.game.state == "success":
                self._check_achievements()
        else:
            self._game_over()

    def _check_achievements(self) -> None:
        score = self.game.score
        self.unlock_milestones(score, {"round_5": 5, "round_12": 12, "round_20": 20})
        if self.mode == "shuffle" and score >= 8:
            self.unlock("shuffle_8")

    def _game_over(self) -> None:
        score = self.game.score
        self.new_best = score > 0 and self.submit_score(score, self.mode)
        self.menu = ButtonMenu(
            self.theme,
            (SIDE_X + 150, 560),
            [("Play again", self._new_game)],
            accent=ACCENT,
        )

    # ------------------------------------------------------------------ events
    def handle_event(self, event: pygame.event.Event) -> None:
        if self.menu is not None:
            self.menu.handle_event(event)
            return
        if self.picker.handle_event(event):
            return
        for pad, action in enumerate(PAD_ACTIONS):
            if is_action(event, action, repeat=False):
                self._press(pad)
                return
        if is_action(event, "action", repeat=False):
            self._start()
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for pad in range(PADS):
                if pad_rect(pad).collidepoint(event.pos):
                    self._press(pad)
                    return
            hub = pygame.Vector2(CENTER)
            if hub.distance_to(event.pos) <= HUB_R:
                self._start()

    def update(self, dt: float) -> None:
        self.time += dt
        self.picker.update(dt)
        self.flash = {p: left - dt for p, left in self.flash.items() if left > dt}
        if self.menu is not None:
            self.menu.update(dt)
            return
        self.game.update(dt)

    # ------------------------------------------------------------------ drawing
    def draw(self, surface: Canvas) -> None:
        t = self.theme
        p = t.palette
        surface.fill(p.bg)
        g = self.game
        for pad in range(PADS):
            self._draw_pad(surface, t, pad)
        self._draw_hub(surface, t)
        self._draw_side(surface, t)
        if self.menu is not None:
            panel = pygame.Rect(SIDE_X - 20, 400, 340, 210)
            draw_panel(surface, panel, t)
            draw.text(
                surface,
                f"Round {g.score}" if g.score else "Missed the first one",
                t.font(t.size.title, "bold"),
                p.text,
                (panel.centerx, panel.y + 24),
                "midtop",
            )
            draw.text(
                surface,
                "New best!" if self.new_best else "The ringed pad was next.",
                t.font(t.size.label, "semibold"),
                p.success if self.new_best else p.text_muted,
                (panel.centerx, panel.y + 62),
                "midtop",
            )
            self.menu.draw(surface)

    def _pad_glow(self, pad: int) -> float:
        """How lit a pad is, 0..1: playback, a press flash, or the end-of-game hint."""
        g = self.game
        if g.lit == pad:
            return 1.0
        if pad in self.flash:
            return 0.4 + 0.6 * self.flash[pad] / FLASH_SECONDS
        if g.state == "success":
            return 0.35 + 0.25 * abs(((g.timer * 4) % 2) - 1)
        return 0.0

    def _draw_pad(self, surface: Canvas, t: Theme, pad: int) -> None:
        p = t.palette
        g = self.game
        rect = pad_rect(pad)
        base = PAD_COLORS[pad]
        glow = self._pad_glow(pad)
        if glow:
            for i in range(4, 0, -1):
                halo = rect.inflate(i * 14, i * 14)
                draw.rounded_rect(surface, halo, with_alpha(base, round(22 * glow)), 36 + i * 7)
        color = lerp_color(lerp_color(base, p.bg, 0.72), base, glow)
        draw.shadow(surface, rect, 32, p.shadow, (0, 6), 12)
        draw.rounded_rect(surface, rect, color, 32)
        inner = rect.inflate(-22, -22)
        draw.rounded_rect(surface, inner, lerp_color(color, (255, 255, 255), 0.08 + 0.2 * glow), 24)
        if g.state == "over" and g.wrong is not None and g.wrong[1] == pad:
            pulse = 0.5 + 0.5 * abs(((self.time * 2) % 2) - 1)
            ring = rect.inflate(16, 16)
            draw.rounded_rect(surface, ring, lerp_color(p.bg, base, pulse), 40, 4)
        label = self.input.label(PAD_ACTIONS[pad])
        draw.text(
            surface,
            label,
            t.font(t.size.title, "bold"),
            lerp_color(color, (0, 0, 0) if glow > 0.5 else (255, 255, 255), 0.4),
            (rect.centerx, rect.bottom - 18),
            "midbottom",
        )

    def _draw_hub(self, surface: Canvas, t: Theme) -> None:
        p = t.palette
        g = self.game
        gfx.circle(surface, p.surface, CENTER, HUB_R)
        gfx.circle(surface, p.border, CENTER, HUB_R, 2)
        big, small = {
            "ready": ("Start", self.input.label("action")),
            "showing": (str(len(g.sequence)), "Watch"),
            "input": (f"{g.pos}/{len(g.sequence)}", "Your turn"),
            "success": (str(len(g.sequence)), "Nice!"),
            "over": (str(g.score), "Game over"),
        }[g.state]
        color = ACCENT if g.state in ("input", "success") else p.text
        draw.text(
            surface,
            big,
            t.font(t.size.heading, "bold"),
            color,
            (CENTER[0], CENTER[1] - 8),
            "center",
        )
        draw.text(
            surface,
            small,
            t.font(t.size.caption, "semibold"),
            p.text_muted,
            (CENTER[0], CENTER[1] + 26),
            "center",
        )

    def _draw_side(self, surface: Canvas, t: Theme) -> None:
        p = t.palette
        x = SIDE_X
        draw.text(surface, "Echo Pads", t.font(t.size.heading, "bold"), p.text, (x, 80))
        blurb = (
            "One more step every round."
            if self.mode == "classic"
            else "A brand-new pattern every round."
        )
        draw.text(surface, blurb, t.font(t.size.label), p.text_muted, (x, 126))
        self.picker.draw(surface)
        best = self.best_score(self.mode)
        stats = (("Round", str(self.game.score)), ("Best", f"{best.score:.0f}" if best else "—"))
        for i, (label, value) in enumerate(stats):
            sx = x + i * 130
            draw.text(
                surface, label.upper(), t.font(t.size.caption, "semibold"), p.text_muted, (sx, 272)
            )
            draw.text(surface, value, t.font(t.size.heading, "bold"), p.text, (sx, 294))
        if self.menu is None:
            hint = "Arrows or click the pads · Space to start"
            draw.text(surface, hint, t.font(t.size.caption), p.text_muted, (x, 360))
