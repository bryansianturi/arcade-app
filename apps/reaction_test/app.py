"""Reaction Test UI: a signal panel for Classic, a target field for Targets, and a results card."""

from __future__ import annotations

import math
import random
import time
from collections.abc import Callable

import pygame

from apps.reaction_test.logic import ROUNDS, TARGET_R, TARGETS, ClassicTest, TargetRun
from core import draw, gfx
from core.base_app import BaseApp, format_score
from core.canvas import Canvas
from core.input import is_action
from core.registry import register_app
from core.theme import Color, Theme, lerp_color
from core.widgets import ButtonMenu, SegmentedControl, draw_panel

ACCENT: Color = (251, 113, 133)
WAIT: Color = (185, 28, 28)
GO: Color = (22, 163, 74)
EARLY: Color = (217, 119, 6)
RESULT: Color = (30, 64, 175)
ARENA = pygame.Rect(80, 110, 1120, 460)
MODES = ("classic", "targets")
RING_SECONDS = 0.35


@register_app
class ReactionTestApp(BaseApp):
    """How quickly can you react? Wait for the signal, or chase targets."""

    @classmethod
    def draw_icon(cls, surface: Canvas, rect: pygame.Rect, theme: Theme) -> None:
        draw.rounded_rect(surface, rect, (76, 5, 25), theme.radius.md)
        c = rect.center
        r = rect.width * 0.3
        gfx.circle(surface, ACCENT, c, r)
        gfx.circle(surface, (76, 5, 25), c, r * 0.68)
        gfx.circle(surface, ACCENT, c, r * 0.36)
        bolt = [(0.08, -0.5), (-0.22, 0.06), (0.0, 0.06), (-0.1, 0.5), (0.24, -0.08), (0.02, -0.08)]
        gfx.polygon(
            surface,
            (255, 255, 255),
            [(c[0] + x * rect.width * 0.5, c[1] + y * rect.width * 0.5) for x, y in bolt],
        )

    # ------------------------------------------------------------------ lifecycle
    def on_enter(self) -> None:
        #: Monotonic clock in seconds; tests replace it to control time.
        self.clock: Callable[[], float] = time.perf_counter
        mode = self.data.get("mode", "classic")
        self.mode = mode if mode in MODES else "classic"
        self.picker = SegmentedControl(
            self.theme,
            (900, 40, 300, 40),
            ["Classic", "Targets"],
            MODES.index(self.mode),
            self._set_mode,
            accent=ACCENT,
        )
        self._new_run()

    def on_exit(self) -> None:
        self.data["mode"] = self.mode
        self.data.save()

    def on_pause(self) -> None:
        self._paused_at = self.clock()

    def on_resume(self) -> None:
        # Time spent in the pause menu must not count.
        if self.classic.state in ("waiting", "go"):
            self.classic.state = "idle"
        if self.targets.target is not None:
            self.targets.shown_at += self.clock() - self._paused_at

    def restart(self) -> None:
        self._new_run()

    def _set_mode(self, index: int) -> None:
        self.mode = MODES[index]
        self._new_run()

    def _new_run(self) -> None:
        self.classic = ClassicTest(random.Random())
        self.targets = TargetRun(ARENA.width, ARENA.height, random.Random())
        self.rings: list[tuple[float, float, float, bool]] = []  # x, y, age, hit
        self.menu: ButtonMenu | None = None
        self.new_best = False
        self._paused_at = 0.0

    def _finish(self, score: float) -> None:
        self.new_best = self.submit_score(round(score), self.mode)
        if self.mode == "classic":
            self.unlock("first_finish")
            if score < 250:
                self.unlock("under_250")
            if score < 200:
                self.unlock("under_200")
        elif self.targets.misses == 0:
            self.unlock("sharpshooter")
        self.menu = ButtonMenu(
            self.theme,
            (ARENA.centerx, ARENA.centery + 110),
            [("Go again", self._new_run)],
            accent=ACCENT,
        )

    # ------------------------------------------------------------------ events
    def handle_event(self, event: pygame.event.Event) -> None:
        if self.menu is not None:
            self.menu.handle_event(event)
            return
        if self.picker.handle_event(event):
            return
        now = self.clock()
        clicked = (
            event.type == pygame.MOUSEBUTTONDOWN
            and event.button == 1
            and ARENA.collidepoint(event.pos)
        )
        if self.mode == "classic":
            if clicked or is_action(event, "action", repeat=False):
                self.classic.press(now)
                if self.classic.state == "done":
                    self._finish(self.classic.average)
        elif clicked:
            self._click_target(event.pos[0] - ARENA.x, event.pos[1] - ARENA.y, now)

    def _click_target(self, x: float, y: float, now: float) -> None:
        run = self.targets
        if not run.started:
            if math.dist((x, y), (ARENA.width / 2, ARENA.height / 2)) <= TARGET_R:
                run.start(now)
            return
        target = run.target
        hit = run.click(x, y, now)
        if target is not None:
            self.rings.append((*(target if hit else (x, y)), 0.0, hit))
        if run.done:
            self._finish(run.average)

    def update(self, dt: float) -> None:
        self.picker.update(dt)
        self.rings = [(x, y, age + dt, hit) for x, y, age, hit in self.rings if age < RING_SECONDS]
        if self.menu is not None:
            self.menu.update(dt)
            return
        self.classic.tick(self.clock())

    # ------------------------------------------------------------------ drawing
    def draw(self, surface: Canvas) -> None:
        t = self.theme
        p = t.palette
        surface.fill(p.bg)
        draw.text(surface, "Reaction Test", t.font(t.size.heading, "bold"), p.text, (80, 42))
        self.picker.draw(surface)
        draw.shadow(surface, ARENA, t.radius.lg, p.shadow, (0, 8), 16)
        if self.mode == "classic":
            self._draw_classic(surface, t)
        else:
            self._draw_targets(surface, t)
        if self.menu is not None:
            self._draw_results(surface, t)

    def _arena_text(self, surface: Canvas, t: Theme, big: str, small: str, color: Color) -> None:
        draw.text(surface, big, t.font(t.size.display + 16, "bold"), color, ARENA.center, "center")
        draw.text(
            surface,
            small,
            t.font(t.size.title, "medium"),
            lerp_color(color, (128, 128, 128), 0.3),
            (ARENA.centerx, ARENA.centery + 64),
            "center",
        )

    def _draw_classic(self, surface: Canvas, t: Theme) -> None:
        p = t.palette
        c = self.classic
        key = self.input.label("action")
        white: Color = (255, 255, 255)
        state = "done" if self.menu is not None else c.state
        fill, big, small = {
            "idle": (p.surface, "Ready?", f"Click or press {key} to start. Wait for green."),
            "waiting": (WAIT, "Wait for green…", ""),
            "go": (GO, "Now!", ""),
            "result": (RESULT, f"{c.last:.0f} ms", f"Click or press {key} to keep going"),
            "early": (EARLY, "Too soon!", f"Click or press {key} to try that round again"),
            "done": (RESULT, f"{c.average:.0f} ms", ""),
        }[state]
        draw.rounded_rect(surface, ARENA, fill, t.radius.lg)
        self._arena_text(surface, t, big, small, p.text if state == "idle" else white)
        # One slot per round underneath the arena.
        w, gap = 168, 16
        x0 = ARENA.centerx - (ROUNDS * w + (ROUNDS - 1) * gap) / 2
        label = t.font(t.size.caption, "semibold")
        value = t.font(t.size.title, "bold")
        for i in range(ROUNDS):
            slot = pygame.Rect(round(x0 + i * (w + gap)), ARENA.bottom + 24, w, 64)
            draw.rounded_rect(surface, slot, p.surface_alt, t.radius.md)
            draw.text(surface, f"ROUND {i + 1}", label, p.text_muted, (slot.x + 14, slot.y + 10))
            text = f"{c.times[i]:.0f} ms" if i < len(c.times) else "—"
            draw.text(surface, text, value, p.text, (slot.x + 14, slot.y + 28))
        if c.false_starts:
            s = "s" if c.false_starts > 1 else ""
            draw.text(
                surface,
                f"{c.false_starts} false start{s}",
                t.font(t.size.label, "semibold"),
                EARLY,
                (ARENA.x, ARENA.bottom + 112),
            )

    def _draw_targets(self, surface: Canvas, t: Theme) -> None:
        p = t.palette
        run = self.targets
        draw.rounded_rect(surface, ARENA, p.surface, t.radius.lg)
        if not run.started:
            self._draw_target(surface, (ARENA.width / 2, ARENA.height / 2))
            draw.text(
                surface,
                f"Hit the target to start. {TARGETS} targets, as fast as you can.",
                t.font(t.size.title, "medium"),
                p.text_muted,
                (ARENA.centerx, ARENA.centery + 80),
                "center",
            )
        elif run.target is not None:
            self._draw_target(surface, run.target)
        for x, y, age, hit in self.rings:
            k = age / RING_SECONDS
            color = lerp_color(ACCENT if hit else p.text_muted, p.surface, k)
            r = TARGET_R * (1 + k) if hit else 10 + 8 * k
            gfx.circle(surface, color, (ARENA.x + x, ARENA.y + y), r, 3)
        # Progress bar and running numbers.
        bar = pygame.Rect(ARENA.x, ARENA.bottom + 32, ARENA.width, 10)
        draw.rounded_rect(surface, bar, p.surface_alt, 5)
        done = len(run.times) / TARGETS
        if done:
            fill = pygame.Rect(bar.x, bar.y, max(10, round(bar.width * done)), bar.height)
            draw.rounded_rect(surface, fill, ACCENT, 5)
        font = t.font(t.size.label, "semibold")
        stats = f"{len(run.times)} / {TARGETS}   ·   Misses {run.misses}"
        if run.times:
            stats += f"   ·   Average {run.average:.0f} ms"
        draw.text(surface, stats, font, p.text_muted, (ARENA.x, bar.bottom + 18))
        draw.text(
            surface, "Mouse only", font, p.text_muted, (ARENA.right, bar.bottom + 18), "topright"
        )

    def _draw_target(self, surface: Canvas, pos: tuple[float, float]) -> None:
        center = (ARENA.x + pos[0], ARENA.y + pos[1])
        for k, color in ((1.0, ACCENT), (0.66, (255, 255, 255)), (0.33, ACCENT)):
            gfx.circle(surface, color, center, TARGET_R * k)

    def _draw_results(self, surface: Canvas, t: Theme) -> None:
        assert self.menu is not None
        p = t.palette
        draw.overlay(surface, p.overlay)
        panel = pygame.Rect(0, 0, 440, 230 + self.menu.rect.height)
        panel.midbottom = (ARENA.centerx, self.menu.rect.bottom + 32)
        draw_panel(surface, panel, t)
        if self.mode == "classic":
            fs = self.classic.false_starts
            average = self.classic.average
            detail = f"Best round {min(self.classic.times):.0f} ms · " + (
                "no false starts" if fs == 0 else f"{fs} false start{'s' if fs > 1 else ''}"
            )
        else:
            average = self.targets.average
            detail = f"{TARGETS} targets · {self.targets.misses} misses"
        draw.text(
            surface,
            "AVERAGE",
            t.font(t.size.caption, "semibold"),
            p.text_muted,
            (panel.centerx, panel.y + 26),
            "midtop",
        )
        draw.text(
            surface,
            f"{average:.0f} ms",
            t.font(t.size.display + 8, "bold"),
            ACCENT,
            (panel.centerx, panel.y + 46),
            "midtop",
        )
        best = self.best_score(self.mode)
        sub = (
            "New best!"
            if self.new_best
            else (f"Best {format_score(best.score, 'ms')}" if best else "")
        )
        draw.text(
            surface,
            sub,
            t.font(t.size.label, "semibold"),
            p.success if self.new_best else p.text_muted,
            (panel.centerx, panel.y + 118),
            "midtop",
        )
        draw.text(
            surface,
            detail,
            t.font(t.size.label),
            p.text_muted,
            (panel.centerx, panel.y + 146),
            "midtop",
        )
        self.menu.draw(surface)
