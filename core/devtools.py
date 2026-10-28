"""Developer mode (Settings → Developer mode): a debug overlay and hot reload.

* The overlay shows FPS and frame time, the render scale, the scene stack, the
  running app and which shared actions are held.
* **F5** re-imports the current app's package (code *and* ``app.toml``) and
  restarts it in place, without restarting the arcade. The old instance's
  ``on_exit`` runs first, so apps that save their state resume where they were.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import pygame

from core import draw
from core import registry as registry_module
from core.app_host import AppHost
from core.canvas import Canvas, render_scale
from core.input import ACTIONS
from core.registry import RegistrationError

if TYPE_CHECKING:
    from core.services import Services

log = logging.getLogger(__name__)

RELOAD_KEY = pygame.K_F5


def hot_reload(services: Services) -> bool:
    """Reload the app in the current scene. Shows a toast either way; returns success."""
    host = services.scenes.current
    if not isinstance(host, AppHost):
        services.toasts.show("Nothing to reload", "Open an app first, then press F5")
        return False
    old = host.app_cls
    try:
        new = registry_module.registry.reload(old.meta.id)
    except RegistrationError as exc:
        log.warning("Hot reload of %s failed: %s", old.meta.id, exc)
        services.toasts.show(f"Reload failed: {old.meta.name}", str(exc), accent=(222, 60, 72))
        return False
    services.apps = [new if a is old else a for a in services.apps]
    services.define_achievements()
    host.swap_app(new)
    log.info("Hot-reloaded %s", new.meta.id)
    services.toasts.show(
        f"Reloaded {new.meta.name}", f"v{new.meta.version}", accent=new.meta.accent
    )
    return True


def overlay_lines(services: Services, fps: float, frame_ms: float) -> list[str]:
    scenes = services.scenes
    stack = " > ".join(type(s).__name__ for s in scenes.stack) or "—"
    lines = [
        f"{fps:5.1f} FPS · {frame_ms:4.1f} ms",
        f"Scale {render_scale():.2f}× · {scenes.size[0]}×{scenes.size[1]} logical",
        f"Scenes: {stack}",
    ]
    current = scenes.current
    if isinstance(current, AppHost):
        meta = current.app_cls.meta
        lines.append(f"App: {meta.id} v{meta.version} · {current.state.name.lower()} · F5 reload")
    held = [a for a in ACTIONS if services.input.held(a)]
    pads = len(services.input.gamepads.pads)
    lines.append(f"Held: {', '.join(held) or '—'} · {pads} gamepad{'s' if pads != 1 else ''}")
    return lines


def draw_overlay(surface: Canvas, services: Services, fps: float, frame_ms: float) -> None:
    t = services.theme
    font = t.font(t.size.caption, "medium")
    lines = overlay_lines(services, fps, frame_ms)
    width = max(font.size(line)[0] for line in lines) + 24
    rect = pygame.Rect(0, 0, width, len(lines) * 18 + 16)
    rect.bottomleft = (8, surface.get_height() - 8)
    draw.rounded_rect(surface, rect, (8, 9, 13, 200), t.radius.sm)
    for i, line in enumerate(lines):
        color = t.palette.success if i == 0 else (225, 228, 236)
        draw.text(surface, line, font, color, (rect.x + 12, rect.y + 8 + i * 18))
