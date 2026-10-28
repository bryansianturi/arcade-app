"""Focus Timer UI: Pomodoro ring with session dots, and a stopwatch with laps."""

from __future__ import annotations

import math
import time
from collections.abc import Callable

import pygame

from apps.focus_timer.logic import PHASE_LABELS, PHASES, Phase, Pomodoro, Stopwatch
from core import draw
from core.base_app import AppMeta, BaseApp
from core.registry import register_app
from core.theme import Color, Theme, lerp_color
from core.widgets import Button, SegmentedControl, draw_panel

ACCENT: Color = (244, 63, 94)
PHASE_COLORS: dict[Phase, Color] = {
    "focus": (244, 63, 94),
    "short": (20, 184, 166),
    "long": (99, 102, 241),
}
RING_CENTER = (420, 380)
RING_R = 190
RIGHT_X = 760


def clock_text(seconds: float, hundredths: bool = False) -> str:
    """``mm:ss`` (or ``h:mm:ss``), optionally with ``.cc`` hundredths."""
    whole = int(seconds)
    h, rem = divmod(whole, 3600)
    m, s = divmod(rem, 60)
    text = f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"
    if hundredths:
        text += f".{int((seconds - whole) * 100):02d}"
    return text


@register_app
class FocusTimerApp(BaseApp):
    """A Pomodoro timer and a stopwatch. Keeps running while you use other apps."""

    meta = AppMeta(
        id="focus_timer",
        name="Focus Timer",
        description="Pomodoro sessions and a lap stopwatch.",
        category="tool",
        accent=ACCENT,
    )

    #: Injectable wall clock (tests replace it).
    now: Callable[[], float] = staticmethod(time.time)

    @classmethod
    def draw_icon(cls, surface: pygame.Surface, rect: pygame.Rect, theme: Theme) -> None:
        draw.rounded_rect(surface, rect, ACCENT, theme.radius.md)
        r = rect.width * 0.32
        pygame.draw.circle(surface, (255, 255, 255), rect.center, r, 3)
        draw.ring_arc(surface, (255, 255, 255), rect.center, r, 3, 0.7)
        pygame.draw.line(
            surface, (255, 255, 255), rect.center, (rect.centerx, rect.centery - r * 0.6), 3
        )
        pygame.draw.line(
            surface, (255, 255, 255), rect.center, (rect.centerx + r * 0.45, rect.centery), 3
        )

    # ------------------------------------------------------------------ lifecycle
    def on_enter(self) -> None:
        t = self.theme
        self.pomodoro = Pomodoro.from_dict(self.data.get("pomodoro"))
        self.stopwatch = Stopwatch()
        self.tab = int(self.data.get("tab", 0)) if self.data.get("tab") in (0, 1) else 0
        self.tabs = SegmentedControl(
            t,
            (640 - 170, 24, 340, 40),
            ["Pomodoro", "Stopwatch"],
            self.tab,
            self._set_tab,
            accent=ACCENT,
        )
        y = RING_CENTER[1] + RING_R + 40
        self.start_btn = Button(
            t, (RING_CENTER[0] - 160, y, 150, 52), "Start", self._toggle, "primary", accent=ACCENT
        )
        self.reset_btn = Button(t, (RING_CENTER[0] + 10, y, 150, 52), "Reset", self._reset)
        self.skip_btn = Button(t, (RIGHT_X, 520, 200, 44), "Skip phase", self._skip)
        self.lap_btn = Button(t, (RING_CENTER[0] + 10, y, 150, 52), "Lap", self._lap)
        self.adjusters: list[tuple[Phase, Button, Button]] = []
        for i, phase in enumerate(PHASES):
            row_y = 236 + i * 70
            minus = Button(t, (RIGHT_X + 250, row_y, 44, 44), "−", self._adjuster(phase, -1))
            plus = Button(t, (RIGHT_X + 370, row_y, 44, 44), "+", self._adjuster(phase, 1))
            self.adjusters.append((phase, minus, plus))
        self.alert_started = 0.0
        self.time = 0.0
        if self.pomodoro.update(self.now()):  # a phase may have finished while we were away
            self.alert_started = self.time

    def on_exit(self) -> None:
        self.data["pomodoro"] = self.pomodoro.to_dict()
        self.data["tab"] = self.tab
        self.data.save()

    def restart(self) -> None:
        self._reset()

    def _set_tab(self, index: int) -> None:
        self.tabs.index = index
        self.tab = index

    # ------------------------------------------------------------------ actions
    def _toggle(self) -> None:
        if self.tab == 0:
            self.pomodoro.toggle(self.now())
        else:
            self.stopwatch.toggle(self.now())

    def _reset(self) -> None:
        if self.tab == 0:
            self.pomodoro.reset()
        else:
            self.stopwatch.reset()

    def _skip(self) -> None:
        self.pomodoro.skip()

    def _lap(self) -> None:
        self.stopwatch.lap(self.now())

    def _adjuster(self, phase: Phase, delta: int) -> Callable[[], None]:
        return lambda: self._adjust(phase, delta)

    def _adjust(self, phase: Phase, delta: int) -> None:
        self.pomodoro.adjust(phase, delta)
        self.data["pomodoro"] = self.pomodoro.to_dict()
        self.data.save()

    def _widgets(self) -> list[Button]:
        common = [self.start_btn, self.reset_btn if self.tab == 0 else self.lap_btn]
        if self.tab == 0:
            common.append(self.skip_btn)
            for _, minus, plus in self.adjusters:
                common += [minus, plus]
        return common

    # ------------------------------------------------------------------ input
    def handle_event(self, event: pygame.event.Event) -> None:
        if self.tabs.handle_event(event):
            return
        for widget in self._widgets():
            if widget.handle_event(event):
                return
        if event.type != pygame.KEYDOWN:
            return
        if event.key == pygame.K_SPACE:
            self._toggle()
        elif event.key == pygame.K_r:
            self._reset()
        elif event.key == pygame.K_l and self.tab == 1:
            self._lap()
        elif event.key == pygame.K_s and self.tab == 0:
            self._skip()
        elif event.key == pygame.K_TAB:
            self._set_tab(1 - self.tab)

    def update(self, dt: float) -> None:
        self.time += dt
        if self.pomodoro.update(self.now()):
            self.alert_started = self.time
            self.data["pomodoro"] = self.pomodoro.to_dict()
            self.data.save()
        running = self.pomodoro.clock.running if self.tab == 0 else self.stopwatch.clock.running
        self.start_btn.text = (
            "Pause" if running else ("Resume" if self._paused_midway() else "Start")
        )
        self.start_btn.accent = PHASE_COLORS[self.pomodoro.phase] if self.tab == 0 else ACCENT
        self.tabs.update(dt)
        for widget in self._widgets():
            widget.update(dt)

    def _paused_midway(self) -> bool:
        clock = self.pomodoro.clock if self.tab == 0 else self.stopwatch.clock
        return clock.accumulated > 0

    # ------------------------------------------------------------------ drawing
    def draw(self, surface: pygame.Surface) -> None:
        t = self.theme
        surface.fill(t.palette.bg)
        self.tabs.draw(surface)
        if self.tab == 0:
            self._draw_pomodoro(surface, t)
        else:
            self._draw_stopwatch(surface, t)
        for widget in self._widgets():
            widget.draw(surface)

    def _draw_pomodoro(self, surface: pygame.Surface, t: Theme) -> None:
        p = t.palette
        pomo = self.pomodoro
        now = self.now()
        color = PHASE_COLORS[pomo.phase]
        # A finished phase pulses until the next one is started (there is no sound).
        alert = pomo.just_finished is not None
        pulse = 0.5 + 0.5 * math.sin((self.time - self.alert_started) * 6) if alert else 0.0
        track = lerp_color(p.surface_alt, color, 0.12 + 0.3 * pulse)
        pygame.draw.circle(surface, track, RING_CENTER, RING_R, 18)
        draw.ring_arc(surface, color, RING_CENTER, RING_R, 18, pomo.progress(now))
        draw.text(
            surface,
            PHASE_LABELS[pomo.phase].upper(),
            t.font(t.size.label, "bold"),
            color,
            (RING_CENTER[0], RING_CENTER[1] - 70),
            "center",
        )
        draw.text(
            surface,
            clock_text(pomo.remaining(now) + 0.999),
            t.font(84, "bold"),
            p.text,
            RING_CENTER,
            "center",
        )
        # Dots: progress towards the long break.
        n = pomo.long_every
        done = pomo.completed % n if pomo.phase != "long" else n
        for i in range(n):
            cx = RING_CENTER[0] + (i - (n - 1) / 2) * 26
            filled = i < done
            pygame.draw.circle(
                surface, color if filled else p.surface_hover, (cx, RING_CENTER[1] + 72), 7
            )
        draw.text(
            surface,
            f"{pomo.completed} session{'s' if pomo.completed != 1 else ''} completed",
            t.font(t.size.caption),
            p.text_muted,
            (RING_CENTER[0], RING_CENTER[1] + 100),
            "center",
        )

        if alert and pomo.just_finished is not None:
            msg = (
                "Focus session done. Take a break!"
                if pomo.just_finished == "focus"
                else "Break's over. Ready to focus?"
            )
            font = t.font(t.size.title, "bold")
            banner = pygame.Rect(0, 0, font.size(msg)[0] + 48, 52)
            banner.midtop = (640, 84)
            draw.rounded_rect(
                surface, banner, lerp_color(color, p.bg, 0.15 * (1 - pulse)), t.radius.lg
            )
            draw.text(surface, msg, font, (255, 255, 255), banner.center, "center")

        panel = pygame.Rect(RIGHT_X - 24, 170, 470, 420)
        draw_panel(surface, panel, t)
        draw.text(
            surface, "Session lengths", t.font(t.size.title, "semibold"), p.text, (RIGHT_X, 192)
        )
        for phase, minus, plus in self.adjusters:
            y = minus.rect.centery
            pygame.draw.circle(surface, PHASE_COLORS[phase], (RIGHT_X + 8, y), 6)
            draw.text(
                surface,
                PHASE_LABELS[phase],
                t.font(t.size.body, "medium"),
                p.text,
                (RIGHT_X + 24, y),
                "midleft",
            )
            draw.text(
                surface,
                f"{pomo.minutes[phase]} min",
                t.font(t.size.body, "bold"),
                p.text,
                ((minus.rect.right + plus.rect.x) // 2, y),
                "center",
            )
        draw.text(
            surface,
            f"Long break after every {pomo.long_every} focus sessions",
            t.font(t.size.caption),
            p.text_muted,
            (RIGHT_X, 430),
        )
        draw.text(
            surface,
            "Space start/pause · R reset · S skip · Tab stopwatch",
            t.font(t.size.caption),
            p.text_muted,
            (RIGHT_X, 470),
        )

    def _draw_stopwatch(self, surface: pygame.Surface, t: Theme) -> None:
        p = t.palette
        sw = self.stopwatch
        now = self.now()
        elapsed = sw.clock.elapsed(now)
        pygame.draw.circle(surface, p.surface_alt, RING_CENTER, RING_R, 18)
        draw.ring_arc(
            surface, ACCENT, RING_CENTER, RING_R, 18, (elapsed % 60) / 60
        )  # one lap per minute
        draw.text(
            surface,
            clock_text(elapsed, hundredths=True),
            t.font(64, "bold"),
            p.text,
            RING_CENTER,
            "center",
        )
        draw.text(
            surface,
            "STOPWATCH",
            t.font(t.size.label, "bold"),
            ACCENT,
            (RING_CENTER[0], RING_CENTER[1] - 70),
            "center",
        )

        panel = pygame.Rect(RIGHT_X - 24, 110, 470, 540)
        draw_panel(surface, panel, t)
        draw.text(surface, "Laps", t.font(t.size.title, "semibold"), p.text, (RIGHT_X, 130))
        laps = sw.lap_times()
        if not laps:
            draw.text(
                surface,
                "Press Lap (or L) while running",
                t.font(t.size.label),
                p.text_muted,
                (RIGHT_X, 176),
            )
        fastest = min(laps) if len(laps) > 1 else None
        slowest = max(laps) if len(laps) > 1 else None
        font = t.font(t.size.body, "medium")
        for row, i in enumerate(range(len(laps) - 1, -1, -1)):
            if row >= 12:
                break
            y = 176 + row * 36
            lap = laps[i]
            color = p.success if lap == fastest else p.danger if lap == slowest else p.text
            draw.text(surface, f"Lap {i + 1}", font, p.text_muted, (RIGHT_X, y))
            draw.text(surface, clock_text(lap, True), font, color, (RIGHT_X + 200, y), "topright")
            draw.text(
                surface,
                clock_text(sw.laps[i], True),
                font,
                p.text_muted,
                (RIGHT_X + 420, y),
                "topright",
            )
        draw.text(
            surface,
            "Space start/stop · L lap · R reset · Tab pomodoro",
            t.font(t.size.caption),
            p.text_muted,
            (RIGHT_X, 620),
        )
