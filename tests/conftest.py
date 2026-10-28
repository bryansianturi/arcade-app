"""Shared fixtures. Tests run headless with SDL's dummy video driver."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame
import pytest

from core.app_host import AppHost
from core.base_app import AppContext, BaseApp
from core.display import LOGICAL_SIZE
from core.scene_manager import Scene, SceneManager
from core.services import Services
from core.settings import Settings
from core.storage import Storage
from core.theme import Theme


@pytest.fixture(scope="session", autouse=True)
def _pygame() -> Iterator[None]:
    pygame.init()
    pygame.display.set_mode(LOGICAL_SIZE)
    yield
    pygame.quit()


@pytest.fixture
def storage(tmp_path: Path) -> Storage:
    return Storage(tmp_path / "data")


@pytest.fixture
def services(storage: Storage) -> Services:
    settings = Settings()
    settings.transitions = False
    return Services(
        theme=Theme(),
        storage=storage,
        settings=settings,
        scenes=SceneManager(LOGICAL_SIZE, animations=False),
        apps=[],
    )


@pytest.fixture
def app_context(services: Services) -> AppContext:
    return AppContext(
        theme=services.theme,
        storage=services.storage,
        settings=services.settings,
        screen_rect=pygame.Rect((0, 0), LOGICAL_SIZE),
        request_exit=lambda: None,
        request_pause=lambda: None,
    )


def host_app(services: Services, app_cls: type[BaseApp]) -> AppHost:
    """Push a dummy root scene and then ``app_cls`` inside an AppHost."""
    services.scenes.push(Scene(services), transition="none")
    host = AppHost(services, app_cls)
    services.scenes.push(host, transition="none")
    return host


def key(k: int, unicode: str = "", mod: int = 0) -> pygame.event.Event:
    return pygame.event.Event(pygame.KEYDOWN, key=k, unicode=unicode, mod=mod)


def click(pos: tuple[int, int], button: int = 1) -> list[pygame.event.Event]:
    return [
        pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=pos, button=button),
        pygame.event.Event(pygame.MOUSEBUTTONUP, pos=pos, button=button),
    ]
