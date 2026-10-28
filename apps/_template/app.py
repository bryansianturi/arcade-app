"""Rendering and input for the template app."""

from __future__ import annotations

import pygame

from apps._template.logic import ClickCounter
from core import draw
from core.base_app import BaseApp
from core.canvas import Canvas
from core.input import is_action
from core.registry import register_app
from core.widgets import Button


@register_app
class TemplateApp(BaseApp):
    """A minimal working app: one button, a score, and a saved high score."""

    def on_enter(self) -> None:
        # Called on launch and after Restart: (re)build all state here.
        self.counter = ClickCounter()
        center = self.ctx.screen_rect.center
        self.button = Button(
            self.theme,
            (center[0] - 100, center[1], 200, 52),
            "Click me",
            self._on_click,
            "primary",
            accent=self.meta.accent,
        )

    def on_exit(self) -> None:
        # Called when leaving or restarting: save progress here.
        self.submit_score(self.counter.score)

    def _on_click(self) -> None:
        self.counter.hit()

    def handle_event(self, event: pygame.event.Event) -> None:
        self.button.handle_event(event)
        # React to the shared, remappable controls rather than to specific keys.
        if is_action(event, "action", repeat=False):
            self.counter.hit()

    def update(self, dt: float) -> None:
        self.button.update(dt)
        # Achievements are declared in app.toml; unlocking twice is harmless.
        self.unlock_milestones(self.counter.score, {"ten_clicks": 10})

    def draw(self, surface: Canvas) -> None:
        t = self.theme
        surface.fill(t.palette.bg)
        cx, cy = self.ctx.screen_rect.center
        draw.text(
            surface,
            f"Score: {self.counter.score}",
            t.font(t.size.display, "bold"),
            t.palette.text,
            (cx, cy - 60),
            "center",
        )
        best = self.best_score()
        pause_key = self.input.label("pause")
        hint = f"Best: {int(best.score)}" if best else f"Press {pause_key} for the pause menu"
        draw.text(
            surface, hint, t.font(t.size.label), t.palette.text_muted, (cx, cy + 90), "center"
        )
        self.button.draw(surface)
