"""The OS window: a fixed logical canvas scaled to the window by SDL.

Everything is drawn onto a 1280×720 canvas. ``pygame.SCALED`` lets SDL scale
it on the GPU with letterboxing, and mouse coordinates are mapped back to the
canvas automatically, so apps never deal with window sizes.
"""

from __future__ import annotations

import os
import warnings

import pygame

from core.settings import Settings

LOGICAL_SIZE = (1280, 720)
MIN_WINDOW_SIZE = (640, 360)
WINDOW_TITLE = "Arcade"


def configure_sdl() -> None:
    """Set SDL hints. Must run before ``pygame.init()``."""
    os.environ.setdefault("SDL_RENDER_SCALE_QUALITY", "linear")  # smooth scaling
    os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")


class Display:
    """Creates the window and applies window-size / fullscreen settings."""

    def __init__(self, settings: Settings) -> None:
        pygame.display.set_caption(WINDOW_TITLE)
        self.surface = pygame.display.set_mode(LOGICAL_SIZE, pygame.SCALED | pygame.RESIZABLE)
        self.rect = self.surface.get_rect()
        # pygame-ce marks this as deprecated in favour of the pure Window API, but it is
        # still the only way to resize a SCALED display window. Isolated here on purpose.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            self._window = pygame.Window.from_display_module()
        # SCALED defaults the minimum window size to the canvas size; allow smaller.
        self._window.minimum_size = MIN_WINDOW_SIZE
        self.fullscreen = False
        self.apply(settings)

    def apply(self, settings: Settings) -> None:
        """Apply ``settings.fullscreen`` and ``settings.window_size``."""
        self.fullscreen = settings.fullscreen
        if settings.fullscreen:
            self._window.set_fullscreen(desktop=True)
            return
        self._window.set_windowed()
        desktop_w, desktop_h = pygame.display.get_desktop_sizes()[0]
        w, h = settings.window_size
        # Never open a window bigger than the screen (keep 16:9).
        scale = min(1.0, (desktop_w * 0.95) / w, (desktop_h * 0.9) / h)
        self._window.size = (int(w * scale), int(h * scale))
        self._window.position = pygame.WINDOWPOS_CENTERED
