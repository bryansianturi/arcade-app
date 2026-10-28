"""Rendering and input for the template app."""

from __future__ import annotations

import pygame

from apps._template.logic import ClickCounter
from core import draw
from core.base_app import BaseApp
from core.canvas import Canvas
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
        if event.type == pygame.KEYDOWN and event.key == pygame.K_SPACE:
            self.counter.hit()

    def update(self, dt: float) -> None:
        self.button.update(dt)

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
        hint = f"Best: {int(best.score)}" if best else "Press Esc for the pause menu"
        draw.text(
            surface, hint, t.font(t.size.label), t.palette.text_muted, (cx, cy + 90), "center"
        )
        self.button.draw(surface)
