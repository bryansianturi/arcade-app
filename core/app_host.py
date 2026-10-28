"""Runs one app inside the scene stack and provides framework-level behaviour.

Responsibilities:

* Creating the app with its :class:`~core.base_app.AppContext`.
* The pause menu (Resume / Restart / Back to menu) on the ``pause`` action (Esc,
  P or a gamepad's Start button by default), and auto-pausing games
  when the window loses focus.
* Crash isolation: any exception raised by the app is logged and replaced by a
  friendly dialog instead of taking the whole arcade down.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from enum import Enum, auto
from typing import TYPE_CHECKING

import pygame

from core import draw
from core.base_app import AppContext, BaseApp
from core.canvas import Canvas
from core.input import is_action
from core.scene_manager import Scene
from core.widgets import ButtonMenu, draw_panel

if TYPE_CHECKING:
    from core.services import Services

log = logging.getLogger(__name__)


class HostState(Enum):
    RUNNING = auto()
    PAUSED = auto()
    CRASHED = auto()


class AppHost(Scene):
    """Scene that hosts a :class:`BaseApp` subclass."""

    def __init__(self, services: Services, app_cls: type[BaseApp]) -> None:
        super().__init__(services)
        self.app_cls = app_cls
        self.app: BaseApp | None = None
        self.state = HostState.RUNNING
        self.error: str = ""
        self._menu: ButtonMenu | None = None

    # ------------------------------------------------------------------ guard
    def _guard(self, label: str, fn: Callable[[], object]) -> bool:
        """Run ``fn``; on any exception switch to the crash dialog. Returns success."""
        try:
            fn()
        except Exception as exc:
            self._crash(label, exc)
            return False
        return True

    def _crash(self, label: str, exc: Exception) -> None:
        name = self.app_cls.meta.name
        log.exception("App %r crashed during %s", self.app_cls.meta.id, label)
        self.error = f"{type(exc).__name__}: {exc}"
        self.state = HostState.CRASHED
        if self.app is not None:
            # Best effort: let the app save/clean up, but never crash again because of it.
            try:
                self.app.on_exit()
            except Exception:
                log.exception("App %r also failed in on_exit", self.app_cls.meta.id)
            self.app = None
        self._menu = self._build_menu([("Back to menu", self._exit)])
        log.info("Showing crash dialog for %s", name)

    # ------------------------------------------------------------------ lifecycle
    def on_enter(self) -> None:
        ctx = AppContext(
            theme=self.services.theme,
            storage=self.services.storage,
            settings=self.services.settings,
            screen_rect=pygame.Rect((0, 0), self.manager.size),
            request_exit=self._exit,
            request_pause=self.pause,
            input=self.services.input,
            achievements=self.services.achievements,
            toasts=self.services.toasts,
        )

        def start() -> None:
            self.app = self.app_cls(ctx)
            self.app.on_enter()

        self._guard("startup", start)

    def on_exit(self) -> None:
        if self.app is not None:
            app = self.app
            self._guard("on_exit", app.on_exit)
            self.app = None

    # ------------------------------------------------------------------ actions
    def pause(self) -> None:
        if self.state is not HostState.RUNNING or self.app is None:
            return
        app = self.app
        if self._guard("on_pause", app.on_pause):
            self.state = HostState.PAUSED
            self._menu = self._build_menu(
                [("Resume", self.resume), ("Restart", self.restart), ("Back to menu", self._exit)]
            )

    def resume(self) -> None:
        if self.state is HostState.PAUSED and self.app is not None:
            self.state = HostState.RUNNING
            self._menu = None
            self._guard("on_resume", self.app.on_resume)

    def restart(self) -> None:
        if self.app is None:
            return
        self.state = HostState.RUNNING
        self._menu = None
        self._guard("restart", self.app.restart)

    def _exit(self) -> None:
        if self.manager.current is self:
            self.manager.pop()

    def _build_menu(self, items: list[tuple[str, Callable[[], None]]]) -> ButtonMenu:
        rect = self.manager.size
        return ButtonMenu(
            self.services.theme,
            (rect[0] // 2, rect[1] // 2 + 36),
            items,
            accent=self.app_cls.meta.accent,
        )

    # ------------------------------------------------------------------ loop
    def handle_event(self, event: pygame.event.Event) -> None:
        if self.state is HostState.RUNNING and self.app is not None:
            app = self.app
            if event.type == pygame.WINDOWFOCUSLOST and app.meta.category == "game":
                self.pause()
                return
            if not app.captures_pause():
                if is_action(event, "pause", repeat=False):
                    self.pause()
                    return
                if self._is_pause_key(event):
                    return  # the matching ACTIONDOWN follows; don't also deliver the key
            self._guard("handle_event", lambda: app.handle_event(event))
            return

        if self._menu is not None:
            if is_action(event, "pause", repeat=False):
                if self.state is HostState.PAUSED:
                    self.resume()
                else:
                    self._exit()
                return
            self._menu.handle_event(event)

    def _is_pause_key(self, event: pygame.event.Event) -> bool:
        if event.type != pygame.KEYDOWN:
            return False
        typed = getattr(event, "unicode", "")
        if self.wants_text() and typed and typed.isprintable():
            return False
        return self.services.input.action_for_key(event.key) == "pause"

    def wants_text(self) -> bool:
        app = self.app
        if app is None or self.state is not HostState.RUNNING:
            return False
        try:
            return app.uses_text_input()
        except Exception:
            log.exception("uses_text_input failed")
            return False

    def update(self, dt: float) -> None:
        if self.state is HostState.RUNNING and self.app is not None:
            app = self.app
            self._guard("update", lambda: app.update(dt))
        if self._menu is not None:
            self._menu.update(dt)

    def draw(self, surface: Canvas) -> None:
        theme = self.services.theme
        if self.app is not None:
            app = self.app
            if not self._guard("draw", lambda: app.draw(surface)):
                surface.fill(theme.palette.bg)
            elif self.state is HostState.RUNNING:
                return
        else:
            surface.fill(theme.palette.bg)
        draw.overlay(surface, theme.palette.overlay)
        if self._menu is not None:
            self._draw_dialog(surface)

    def _draw_dialog(self, surface: Canvas) -> None:
        assert self._menu is not None
        t = self.services.theme
        p = t.palette
        crashed = self.state is HostState.CRASHED
        menu_rect = self._menu.rect
        extra = 190 if crashed else 150
        panel = pygame.Rect(0, 0, 460 if crashed else 360, menu_rect.height + extra)
        panel.centerx = menu_rect.centerx
        panel.bottom = menu_rect.bottom + t.space.xl
        draw_panel(surface, panel, t)

        title = "Something went wrong" if crashed else "Paused"
        draw.text(
            surface,
            title,
            t.font(t.size.heading, "bold"),
            p.text,
            (panel.centerx, panel.y + t.space.xl),
            "midtop",
        )
        if crashed:
            msg = f"{self.app_cls.meta.name} hit an error and was closed."
            sub = draw.fit_text(self.error, t.font(t.size.caption), panel.width - 48)
            y = panel.y + 80
            draw.text(
                surface, msg, t.font(t.size.label), p.text_muted, (panel.centerx, y), "midtop"
            )
            draw.text(
                surface, sub, t.font(t.size.caption), p.danger, (panel.centerx, y + 28), "midtop"
            )
        else:
            draw.text(
                surface,
                self.app_cls.meta.name,
                t.font(t.size.label),
                p.text_muted,
                (panel.centerx, panel.y + 74),
                "midtop",
            )
        self._menu.draw(surface)
