"""Every discovered app must honour the BaseApp contract and survive a headless run."""

from __future__ import annotations

import inspect
import random
import re
import sys
from collections.abc import Iterator
from pathlib import Path

import pygame
import pytest

from core.base_app import AppContext, BaseApp
from core.canvas import Canvas, Viewport, set_viewport
from core.registry import registry
from tests.conftest import feed

# Importing an app package registers it in the global registry.
registry.discover("apps", include_private=True)
ALL_APPS = registry.all()


def test_apps_were_discovered() -> None:
    ids = {a.meta.id for a in ALL_APPS}
    assert "template" in ids
    assert not registry.failures


def test_metadata_is_valid() -> None:
    ids = [a.meta.id for a in ALL_APPS]
    assert len(ids) == len(set(ids))
    for app in ALL_APPS:
        m = app.meta
        assert m.id and m.id == m.id.lower() and " " not in m.id
        assert m.name and m.description
        assert m.category in ("game", "tool")
        assert len(m.accent) == 3 and all(0 <= c <= 255 for c in m.accent)


def _random_events(rng: random.Random, n: int) -> list[pygame.event.Event]:
    keys = [
        pygame.K_UP,
        pygame.K_DOWN,
        pygame.K_LEFT,
        pygame.K_RIGHT,
        pygame.K_SPACE,
        pygame.K_RETURN,
        pygame.K_1,
        pygame.K_5,
        pygame.K_BACKSPACE,
        pygame.K_n,
        pygame.K_c,
    ]
    events = []
    for _ in range(n):
        if rng.random() < 0.5:
            k = rng.choice(keys)
            events.append(pygame.event.Event(pygame.KEYDOWN, key=k, unicode="", mod=0))
            events.append(pygame.event.Event(pygame.KEYUP, key=k, unicode="", mod=0))
        else:
            pos = (rng.randrange(1280), rng.randrange(720))
            events.append(
                pygame.event.Event(pygame.MOUSEMOTION, pos=pos, rel=(0, 0), buttons=(0, 0, 0))
            )
            events.append(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=pos, button=1))
            events.append(pygame.event.Event(pygame.MOUSEBUTTONUP, pos=pos, button=1))
    return events


@pytest.mark.parametrize("app_cls", ALL_APPS, ids=lambda a: a.meta.id)
def test_app_runs_headless(app_cls: type[BaseApp], app_context: AppContext) -> None:
    surface = Canvas.new(app_context.screen_rect.size)
    app = app_cls(app_context)
    app.on_enter()
    rng = random.Random(1234)
    for event in _random_events(rng, 120):
        feed(app, event)
        app.update(1 / 60)
    for _ in range(120):
        app.update(1 / 60)
    app.draw(surface)
    app.on_pause()
    app.on_resume()
    app.restart()
    app.draw(surface)
    app.on_exit()
    app_cls.draw_icon(surface, pygame.Rect(0, 0, 48, 48), app_context.theme)


@pytest.fixture(params=[1.5, 2.0], ids=["1.5x", "2x"])
def hidpi(request: pytest.FixtureRequest) -> Iterator[float]:
    scale: float = request.param
    set_viewport(Viewport(scale=scale))
    yield scale
    set_viewport(Viewport())


@pytest.mark.parametrize("app_cls", ALL_APPS, ids=lambda a: a.meta.id)
def test_app_draws_at_native_resolution(
    app_cls: type[BaseApp], app_context: AppContext, hidpi: float
) -> None:
    surface = Canvas.new(app_context.screen_rect.size)
    assert surface.surface.get_width() == round(1280 * hidpi)
    app = app_cls(app_context)
    app.on_enter()
    for event in _random_events(random.Random(99), 40):
        feed(app, event)
        app.update(1 / 60)
    app.draw(surface)
    app_cls.draw_icon(surface, pygame.Rect(0, 0, 48, 48), app_context.theme)
    app.on_exit()


@pytest.mark.parametrize("app_cls", ALL_APPS, ids=lambda a: a.meta.id)
def test_code_accent_matches_manifest(app_cls: type[BaseApp]) -> None:
    """Apps may keep an ``ACCENT`` constant for drawing; it must match ``app.toml``."""
    module = sys.modules[app_cls.__module__]
    accent = getattr(module, "ACCENT", None)
    assert accent is None or tuple(accent) == app_cls.meta.accent


UNLOCK_CALL = re.compile(r'\.unlock\(\s*"(\w+)"')
MILESTONES = re.compile(r"\.unlock_milestones\([^{]*\{([^}]*)\}", re.S)


@pytest.mark.parametrize("app_cls", ALL_APPS, ids=lambda a: a.meta.id)
def test_unlocked_achievements_are_declared(app_cls: type[BaseApp]) -> None:
    """Every achievement id used in code exists in app.toml, and games have 2-4."""
    source = Path(inspect.getfile(app_cls)).read_text()
    used = set(UNLOCK_CALL.findall(source))
    for block in MILESTONES.findall(source):
        used.update(re.findall(r'"(\w+)"\s*:', block))
    declared = {a.id for a in app_cls.meta.achievements}
    assert used <= declared, f"undeclared: {used - declared}"
    if app_cls.meta.category == "game" and not app_cls.meta.id.startswith("template"):
        assert 2 <= len(declared) <= 4
        assert used == declared, f"never unlocked: {declared - used}"
