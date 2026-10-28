"""Scene stack, app hosting (pause/crash isolation), grid layout and formatting."""

from __future__ import annotations

import pygame

from core.app_host import AppHost, HostState
from core.base_app import AppMeta, BaseApp, format_score
from core.scene_manager import Scene, SceneManager
from core.services import Services
from core.widgets import Grid
from screens.high_scores import build_rows
from screens.launcher import LauncherScreen, matches
from tests.conftest import host_app, key


def state(host: AppHost) -> HostState:
    """Read the state via a call so mypy doesn't narrow it across method calls."""
    return host.state


class Recorder(Scene):
    def __init__(self, services: Services, name: str, log: list[str]) -> None:
        super().__init__(services)
        self.name, self.log = name, log

    def on_enter(self) -> None:
        self.log.append(f"enter {self.name}")

    def on_exit(self) -> None:
        self.log.append(f"exit {self.name}")

    def on_reveal(self) -> None:
        self.log.append(f"reveal {self.name}")


def test_scene_stack_lifecycle(services: Services) -> None:
    log: list[str] = []
    sm = services.scenes
    sm.push(Recorder(services, "a", log))
    sm.push(Recorder(services, "b", log))
    sm.pop()
    sm.pop()  # never pops the root scene
    sm.replace(Recorder(services, "c", log))
    sm.push(Recorder(services, "d", log))
    sm.pop_to_root()
    assert log == [
        "enter a",
        "enter b",
        "exit b",
        "reveal a",
        "exit a",
        "enter c",
        "enter d",
        "exit d",
        "reveal c",
    ]
    assert sm.depth == 1


def test_transitions_block_input_and_finish(services: Services) -> None:
    sm = SceneManager((64, 36), animations=True)
    services.scenes = sm
    got: list[int] = []

    class Sink(Scene):
        def handle_event(self, event: pygame.event.Event) -> None:
            got.append(event.type)

    sm.push(Scene(services), transition="none")
    sm.push(Sink(services))
    assert sm.transitioning is True
    sm.handle_event(pygame.event.Event(pygame.USEREVENT))
    sm.draw(pygame.Surface((64, 36)))
    sm.update(1.0)
    assert not sm.transitioning
    sm.handle_event(pygame.event.Event(pygame.USEREVENT))
    assert got == [pygame.USEREVENT]


class Exploding(BaseApp):
    meta = AppMeta(
        id="exploding", name="Exploding", description="", category="game", accent=(255, 0, 0)
    )
    exits = 0

    def on_exit(self) -> None:
        Exploding.exits += 1

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN and event.key == pygame.K_x:
            raise ValueError("kaboom")

    def update(self, dt: float) -> None: ...

    def draw(self, surface: pygame.Surface) -> None: ...


def test_crashing_app_is_contained(services: Services) -> None:
    Exploding.exits = 0
    host = host_app(services, Exploding)
    host.handle_event(key(pygame.K_x))
    assert state(host) is HostState.CRASHED
    assert host.app is None and "kaboom" in host.error
    assert Exploding.exits == 1  # on_exit still ran so the app could save
    host.draw(pygame.Surface(services.scenes.size))  # dialog renders without the app
    host.handle_event(key(pygame.K_RETURN))  # "Back to menu"
    assert services.scenes.current is not host


class BrokenInit(Exploding):
    meta = AppMeta(id="broken", name="Broken", description="", category="game", accent=(0, 0, 0))

    def on_enter(self) -> None:
        raise RuntimeError("cannot start")


def test_app_failing_on_start_is_contained(services: Services) -> None:
    host = host_app(services, BrokenInit)
    assert state(host) is HostState.CRASHED and "cannot start" in host.error


def test_escape_pauses_and_menu_works(services: Services) -> None:
    host = host_app(services, Exploding)
    host.handle_event(key(pygame.K_ESCAPE))
    assert state(host) is HostState.PAUSED
    host.handle_event(key(pygame.K_ESCAPE))
    assert state(host) is HostState.RUNNING
    host.handle_event(key(pygame.K_ESCAPE))
    host.handle_event(key(pygame.K_DOWN))
    host.handle_event(key(pygame.K_RETURN))  # Restart
    assert state(host) is HostState.RUNNING and host.app is not None
    host.handle_event(key(pygame.K_ESCAPE))
    host.handle_event(key(pygame.K_UP))  # wraps to "Back to menu"
    host.handle_event(key(pygame.K_RETURN))
    assert services.scenes.current is not host


def test_game_pauses_on_focus_loss(services: Services) -> None:
    host = host_app(services, Exploding)
    host.handle_event(pygame.event.Event(pygame.WINDOWFOCUSLOST))
    assert state(host) is HostState.PAUSED


def test_grid_layout_and_navigation() -> None:
    grid = Grid(pygame.Rect(0, 0, 340, 500), columns=3, cell_height=100, gap=20)
    assert grid.cell_width == 100
    assert grid.cell(4).topleft == (120, 120)
    assert grid.cell(4, scroll=50).y == 70
    assert grid.rows(7) == 3 and grid.content_height(7) == 340
    # 7 items: rows [0 1 2] [3 4 5] [6]
    assert grid.move(4, 0, 1, 7) == 6  # nothing directly below 4 -> last item
    assert grid.move(6, 0, 1, 7) == 6  # already on the last row
    assert grid.move(1, 0, -1, 7) == 1
    assert grid.move(5, 0, -1, 7) == 2
    assert grid.move(0, -1, 0, 7) == 0 and grid.move(6, 1, 0, 7) == 6
    assert Grid.fit(pygame.Rect(0, 0, 1184, 10), 260, 10, gap=24).columns == 4


def test_format_score() -> None:
    assert format_score(1234, "points") == "1,234"
    assert format_score(65, "time") == "1:05"
    assert format_score(3725.4, "time") == "1:02:05"


def test_launcher_filtering(services: Services) -> None:
    assert matches(Exploding, "", None)
    assert matches(Exploding, "EXPL", "game")
    assert not matches(Exploding, "", "tool")
    assert not matches(Exploding, "snake", None)

    services.apps = [Exploding]
    services.scenes.push(LauncherScreen(services), transition="none")
    launcher = services.scenes.current
    assert isinstance(launcher, LauncherScreen) and len(launcher.cards) == 1
    launcher.handle_event(key(pygame.K_TAB))  # Games -> still visible
    assert len(launcher.cards) == 1
    launcher.handle_event(key(pygame.K_TAB))  # Tools -> hidden
    assert launcher.cards == []
    launcher.draw(pygame.Surface(services.scenes.size))


def test_launcher_enter_launches_app(services: Services) -> None:
    services.apps = [Exploding]
    services.scenes.push(LauncherScreen(services), transition="none")
    services.scenes.handle_event(key(pygame.K_RETURN))
    assert isinstance(services.scenes.current, AppHost)


def test_high_score_rows(services: Services) -> None:
    class Timed(Exploding):
        meta = AppMeta(
            id="timed",
            name="Timed",
            description="",
            category="game",
            accent=(0, 0, 0),
            tracks_scores=True,
            score_order="lower",
            score_format="time",
            variants=("easy", "hard"),
        )

    services.apps = [Exploding, Timed]  # Exploding doesn't track scores
    services.storage.record_score("timed", 90, "hard", "lower")
    rows = build_rows(services)
    assert len(rows) == 1
    assert [(c.variant, c.value) for c in rows[0].cells] == [("Easy", "—"), ("Hard", "1:30")]
