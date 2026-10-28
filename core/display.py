"""The OS window, drawn at native resolution.

Everything is laid out on a 1280×720 *logical* canvas. Each frame the canvas is
mapped onto the largest 16:9 area that fits the window's real pixels (2× on a
Retina display), letterboxed if needed, and drawn there directly through a
:class:`~core.canvas.Canvas`, so nothing is stretched afterwards. Mouse events
are converted back to logical coordinates, so apps never deal with window sizes.
"""

from __future__ import annotations

import os

import pygame

from core.canvas import Canvas, Viewport, set_viewport, to_logical
from core.settings import Settings
from core.web import IS_BROWSER

LOGICAL_SIZE = (1280, 720)
MIN_WINDOW_SIZE = (640, 360)
WINDOW_TITLE = "Arcade"
LETTERBOX = (0, 0, 0)

_MOUSE_EVENTS = (pygame.MOUSEMOTION, pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP)


def configure_sdl() -> None:
    """Set SDL hints. Must run before ``pygame.init()``."""
    os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")


class Display:
    """Owns the window, applies window-size / fullscreen settings and maps input."""

    def __init__(self, settings: Settings) -> None:
        self.window = pygame.Window(WINDOW_TITLE, LOGICAL_SIZE, resizable=True, allow_high_dpi=True)
        self.window.minimum_size = MIN_WINDOW_SIZE
        self.fullscreen = False
        self.apply(settings)

    def apply(self, settings: Settings) -> None:
        """Apply ``settings.fullscreen`` and ``settings.window_size``."""
        self.fullscreen = settings.fullscreen
        if settings.fullscreen:
            self.window.set_fullscreen(desktop=True)
            return
        self.window.set_windowed()
        desktop_w, desktop_h = pygame.display.get_desktop_sizes()[0]
        w, h = settings.window_size
        # Never open a window bigger than the screen (keep 16:9).
        scale = min(1.0, (desktop_w * 0.95) / w, (desktop_h * 0.9) / h)
        self.window.size = (int(w * scale), int(h * scale))
        self.window.position = pygame.WINDOWPOS_CENTERED

    def begin_frame(self) -> Canvas:
        """Return this frame's logical canvas, sized to the window's current pixels."""
        target = self.window.get_surface()
        width, height = target.get_size()
        scale = min(width / LOGICAL_SIZE[0], height / LOGICAL_SIZE[1])
        area = pygame.Rect(0, 0, round(LOGICAL_SIZE[0] * scale), round(LOGICAL_SIZE[1] * scale))
        area.center = (width // 2, height // 2)
        area = area.clip(target.get_rect())
        if area.size != target.get_size():
            target.fill(LETTERBOX)
        ratio = width / max(1, self.window.size[0])
        set_viewport(Viewport(scale, area.topleft, ratio))
        return Canvas(target.subsurface(area), scale, LOGICAL_SIZE)

    def end_frame(self) -> None:
        self.window.flip()

    @staticmethod
    def to_logical(event: pygame.event.Event) -> pygame.event.Event:
        """Return ``event`` with mouse positions in logical canvas coordinates."""
        if event.type not in _MOUSE_EVENTS:
            return event
        attrs = dict(event.dict)
        attrs["pos"] = to_logical(event.pos)
        if event.type == pygame.MOUSEMOTION:
            x0, y0 = to_logical((event.pos[0] - event.rel[0], event.pos[1] - event.rel[1]))
            attrs["rel"] = (attrs["pos"][0] - x0, attrs["pos"][1] - y0)
        return pygame.event.Event(event.type, attrs)


class BrowserDisplay:
    """The page's canvas in a web browser (see :mod:`core.web`).

    The canvas is exactly the logical size; the page scales it to fit, so
    there is no window to resize and mouse positions are already logical.
    Fullscreen and window-size settings are left to the browser.
    """

    def __init__(self, settings: Settings) -> None:
        self.screen = pygame.display.set_mode(LOGICAL_SIZE)
        pygame.display.set_caption(WINDOW_TITLE)
        self.fullscreen = False

    def apply(self, settings: Settings) -> None:
        """Nothing to apply: the browser owns the window."""

    def begin_frame(self) -> Canvas:
        set_viewport(Viewport(1.0, (0, 0), 1.0))
        return Canvas(self.screen, 1.0, LOGICAL_SIZE)

    def end_frame(self) -> None:
        pygame.display.flip()

    @staticmethod
    def to_logical(event: pygame.event.Event) -> pygame.event.Event:
        return event


def create_display(settings: Settings) -> Display | BrowserDisplay:
    """The OS window on the desktop, or the page's canvas in a browser."""
    return BrowserDisplay(settings) if IS_BROWSER else Display(settings)
