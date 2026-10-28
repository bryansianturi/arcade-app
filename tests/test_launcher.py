"""Launcher: favorites, recently played rows and section-aware navigation."""

from __future__ import annotations

import pygame

from core.app_host import AppHost
from core.base_app import AppMeta, BaseApp
from core.canvas import Canvas
from core.favorites import Favorites
from core.services import Services
from core.storage import Storage
from screens.launcher import LauncherScreen, neighbor
from tests.conftest import click, feed, key, tap


def make_app(app_id: str, category: str = "game") -> type[BaseApp]:
    class App(BaseApp):
        meta = AppMeta(
            id=app_id,
            name=app_id.title(),
            description="d",
            category=category,  # type: ignore[arg-type]
            accent=(1, 2, 3),
        )

        def handle_event(self, event: pygame.event.Event) -> None: ...
        def update(self, dt: float) -> None: ...
        def draw(self, surface: Canvas) -> None: ...

    return App


APPS = [make_app(n) for n in ("alpha", "beta", "gamma", "delta", "epsilon")]


def launcher(services: Services) -> LauncherScreen:
    services.apps = list(APPS)
    services.scenes.push(LauncherScreen(services), transition="none")
    screen = services.scenes.current
    assert isinstance(screen, LauncherScreen)
    return screen


def titles(screen: LauncherScreen) -> list[str | None]:
    return [s.title for s in screen.sections]


def test_favorites_store(storage: Storage) -> None:
    favs = Favorites(storage)
    assert favs.toggle("a") and favs.toggle("b") and not favs.toggle("a")
    assert Favorites(storage).ids == ["b"]
    storage.save_json("favorites.json", {"apps": ["x", 3, "x"]})
    assert Favorites(storage).ids == ["x"]


def test_neighbor_moves_across_rows_and_sections() -> None:
    rects = [pygame.Rect(x * 100, 0, 90, 40) for x in range(2)]  # a short row
    rects += [pygame.Rect(x * 100, 100, 90, 90) for x in range(4)]  # a full row below
    assert neighbor(rects, 0, 1, 0) == 1
    assert neighbor(rects, 1, 1, 0) == 1  # end of row
    assert neighbor(rects, 1, 0, 1) == 3  # straight down
    assert neighbor(rects, 5, 0, -1) == 1  # up to the nearest card above
    assert neighbor(rects, 2, 0, 1) == 2  # nothing below
    assert neighbor([], 0, 1, 0) == 0


def test_sections_appear_only_when_browsing(services: Services) -> None:
    screen = launcher(services)
    assert titles(screen) == [None]
    services.favorites.toggle("gamma")
    services.stats.start_session("beta")
    screen.on_reveal()
    assert titles(screen) == ["Favorites", "Recently played", "All apps"]
    assert [a.meta.id for a in screen.sections[0].apps] == ["gamma"]
    assert screen.cards[1].badge is not None and screen.cards[1].badge.startswith("Played")
    assert len(screen.cards) == 2 + len(APPS)
    screen.search.set_text("alp")
    assert titles(screen) == [None] and len(screen.cards) == 1
    screen.draw(Canvas.new(services.scenes.size))


def test_star_toggles_favorite_without_launching(services: Services) -> None:
    screen = launcher(services)
    screen.update(0)
    card = screen.cards[2]  # gamma
    feed(screen, *click(card.star_rect().center))
    assert "gamma" in services.favorites
    assert titles(screen)[0] == "Favorites"
    assert services.scenes.current is screen  # the star doesn't launch the app


def test_keyboard_navigation_and_ctrl_d(services: Services) -> None:
    screen = launcher(services)
    tap(screen, pygame.K_RIGHT)  # first press only shows the focus ring
    tap(screen, pygame.K_RIGHT)
    assert screen.card_apps[screen.selected] is APPS[1]
    feed(screen, key(pygame.K_d, "", pygame.KMOD_CTRL))
    assert "beta" in services.favorites
    # Beta is now also in the Favorites row; the selection stays on Beta in the grid.
    assert screen.card_apps[screen.selected] is APPS[1]
    assert screen.selected > 0
    tap(screen, pygame.K_UP)
    assert screen.selected == 0 and screen.card_apps[0] is APPS[1]  # up into Favorites
    tap(screen, pygame.K_RETURN)
    assert isinstance(services.scenes.current, AppHost)
