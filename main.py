"""Arcade entry point: ``python main.py``."""

from __future__ import annotations

import logging

import pygame

from core import draw
from core.display import LOGICAL_SIZE, Display, configure_sdl
from core.logging_setup import setup_logging
from core.paths import user_data_dir
from core.registry import discover_apps, registry
from core.scene_manager import SceneManager
from core.services import Services
from core.settings import Settings
from core.storage import Storage
from core.theme import Theme
from screens.launcher import LauncherScreen

FPS = 60
MAX_DT = 0.1  # clamp long frames (window drag, breakpoint) so physics doesn't explode

log = logging.getLogger("arcade")


def main() -> None:
    storage = Storage(user_data_dir())
    log_path = setup_logging(storage.root)
    log.info("Data folder: %s (log: %s)", storage.root, log_path)

    configure_sdl()
    pygame.init()
    pygame.key.set_repeat(350, 35)

    settings = Settings.load(storage)
    theme = Theme(settings.theme)
    display = Display(settings)
    scenes = SceneManager(LOGICAL_SIZE, animations=settings.transitions)

    apps = discover_apps()
    log.info("Loaded %d app(s): %s", len(apps), ", ".join(a.meta.id for a in apps))
    services = Services(theme, storage, settings, scenes, apps, registry.failures)

    def on_settings_changed(s: Settings) -> None:
        theme.set_mode(s.theme)
        scenes.animations = s.transitions
        display.apply(s)

    settings.subscribe(on_settings_changed)
    scenes.push(LauncherScreen(services), transition="none")

    clock = pygame.time.Clock()
    running = True
    while running:
        dt = min(clock.tick(FPS) / 1000.0, MAX_DT)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_F11:
                settings.fullscreen = not settings.fullscreen
                services.save_settings()
            else:
                scenes.handle_event(event)
        scenes.update(dt)
        scenes.draw(display.surface)
        if settings.show_fps:
            _draw_fps(display.surface, theme, clock.get_fps())
        pygame.display.flip()

    scenes.shutdown()
    pygame.quit()


def _draw_fps(surface: pygame.Surface, theme: Theme, fps: float) -> None:
    font = theme.font(theme.size.caption, "semibold")
    label = f"{fps:4.0f} FPS"
    rect = pygame.Rect(0, 0, font.size(label)[0] + 16, 24)
    rect.bottomright = (surface.get_width() - 8, surface.get_height() - 8)
    draw.rounded_rect(surface, rect, theme.palette.overlay, theme.radius.sm)
    draw.text(surface, label, font, theme.palette.success, rect.center, "center")


if __name__ == "__main__":
    main()
