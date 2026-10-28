"""Scene stack, app hosting (pause/crash isolation), grid layout and formatting."""

from __future__ import annotations

import pygame

from core.app_host import AppHost, HostState
from core.base_app import AppMeta, BaseApp, format_score
from core.canvas import Canvas, Viewport, set_viewport
from core.input import ACTIONDOWN
from core.scene_manager import Scene, SceneManager
from core.services import Services
from core.widgets import Grid
from screens.high_scores import build_rows
from screens.launcher import LauncherScreen, matches
from tests.conftest import feed, host_app, tap


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
    sm.draw(Canvas.new((64, 36)))
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

    def draw(self, surface: Canvas) -> None: ...


def test_crashing_app_is_contained(services: Services) -> None:
    Exploding.exits = 0
    host = host_app(services, Exploding)
    tap(host, pygame.K_x)
    assert state(host) is HostState.CRASHED
    assert host.app is None and "kaboom" in host.error
    assert Exploding.exits == 1  # on_exit still ran so the app could save
    host.draw(Canvas.new(services.scenes.size))  # dialog renders without the app
    tap(host, pygame.K_RETURN)  # "Back to menu"
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
    tap(host, pygame.K_ESCAPE)
    assert state(host) is HostState.PAUSED
    tap(host, pygame.K_ESCAPE)
    assert state(host) is HostState.RUNNING
    tap(host, pygame.K_ESCAPE)
    tap(host, pygame.K_DOWN)
    tap(host, pygame.K_RETURN)  # Restart
    assert state(host) is HostState.RUNNING and host.app is not None
    tap(host, pygame.K_ESCAPE)
    tap(host, pygame.K_UP)  # wraps to "Back to menu"
    tap(host, pygame.K_RETURN)
    assert services.scenes.current is not host


class Typist(BaseApp):
    meta = AppMeta(id="typist", name="Typist", description="", category="tool", accent=(0, 0, 0))

    def on_enter(self) -> None:
        self.keys: list[int] = []
        self.actions: list[str] = []

    def uses_text_input(self) -> bool:
        return True

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN:
            self.keys.append(event.key)
        elif event.type == ACTIONDOWN:
            self.actions.append(event.action)

    def update(self, dt: float) -> None: ...

    def draw(self, surface: Canvas) -> None: ...


def test_remapped_pause_and_gamepad_start(services: Services) -> None:
    services.input.bind("pause", 0, pygame.K_q)
    host = host_app(services, Exploding)
    tap(host, pygame.K_ESCAPE)
    assert state(host) is HostState.RUNNING  # Esc is no longer bound
    tap(host, pygame.K_q)
    assert state(host) is HostState.PAUSED
    feed(host, pygame.event.Event(pygame.JOYBUTTONDOWN, instance_id=0, button=7))
    assert state(host) is HostState.RUNNING  # Start resumes


def test_text_apps_receive_typed_pause_keys(services: Services) -> None:
    services.input.bind("pause", 1, pygame.K_q)
    host = host_app(services, Typist)
    tap(host, pygame.K_q, "q")  # typed: delivered as a key, no pause
    tap(host, pygame.K_w, "w")  # typed: no "up" action
    assert state(host) is HostState.RUNNING
    assert isinstance(host.app, Typist)
    assert host.app.keys == [pygame.K_q, pygame.K_w] and host.app.actions == []
    tap(host, pygame.K_UP)
    assert host.app.actions == ["up"]
    tap(host, pygame.K_ESCAPE, "\x1b")
    assert state(host) is HostState.PAUSED
    assert pygame.K_ESCAPE not in host.app.keys  # the pause key itself is not delivered


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
    assert format_score(231.4, "ms") == "231 ms"


def test_launcher_filtering(services: Services) -> None:
    assert matches(Exploding, "", None)
    assert matches(Exploding, "EXPL", "game")
    assert not matches(Exploding, "", "tool")
    assert not matches(Exploding, "snake", None)

    services.apps = [Exploding]
    services.scenes.push(LauncherScreen(services), transition="none")
    launcher = services.scenes.current
    assert isinstance(launcher, LauncherScreen) and len(launcher.cards) == 1
    tap(launcher, pygame.K_TAB)  # Games -> still visible
    assert len(launcher.cards) == 1
    tap(launcher, pygame.K_TAB)  # Tools -> hidden
    assert launcher.cards == []
    launcher.draw(Canvas.new(services.scenes.size))


def test_launcher_enter_launches_app(services: Services) -> None:
    services.apps = [Exploding]
    services.scenes.push(LauncherScreen(services), transition="none")
    tap(services.scenes, pygame.K_RETURN, input_map=services.input)
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


def test_screens_and_transitions_draw_at_2x(services: Services) -> None:
    from screens.high_scores import HighScoresScreen
    from screens.settings_screen import SettingsScreen

    services.apps = [Exploding]
    scenes = SceneManager(services.scenes.size, animations=True)
    services.scenes = scenes
    set_viewport(Viewport(scale=2.0))
    try:
        canvas = Canvas.new(scenes.size)
        scenes.push(LauncherScreen(services), transition="none")
        for screen in (SettingsScreen(services), HighScoresScreen(services)):
            scenes.push(screen)
            scenes.draw(canvas)  # mid-transition
            scenes.update(1.0)
            scenes.draw(canvas)
            scenes.pop()
            scenes.update(0.1)
            scenes.draw(canvas)
    finally:
        set_viewport(Viewport())
    # The window is "resized" back to 1x mid-transition: the 2x snapshot is rescaled.
    assert scenes.transitioning
    scenes.draw(Canvas.new(scenes.size))


def test_controls_screen_rebinds_with_keyboard(services: Services) -> None:
    from screens.controls import ControlsScreen

    services.scenes.push(Scene(services), transition="none")
    screen = ControlsScreen(services)
    services.scenes.push(screen, transition="none")
    tap(screen, pygame.K_DOWN)  # focus row 0 ("up"), primary slot
    tap(screen, pygame.K_DOWN)  # row 1 ("down")
    tap(screen, pygame.K_RETURN)  # start capturing
    assert screen.capturing == ("down", 0)
    tap(screen, pygame.K_j)
    assert services.input.keys_for("down")[0] == pygame.K_j
    assert services.scenes.current is screen and screen.cursor == (1, 0)  # J didn't navigate
    assert services.storage.load_json("input.json")["down"][0] == "j"
    tap(screen, pygame.K_RETURN)
    tap(screen, pygame.K_ESCAPE)  # cancels the capture without leaving the screen
    assert screen.capturing is None and services.scenes.current is screen
    screen.cursor = (5, 0)  # pause, primary
    screen._refresh()
    tap(screen, pygame.K_RETURN)
    tap(screen, pygame.K_BACKSPACE)  # can't remove the only pause key
    assert services.input.keys_for("pause") == (pygame.K_ESCAPE,)
    assert "Pause needs" in screen.message
    screen.reset_btn.activate()
    assert services.input.keys_for("down")[0] == pygame.K_DOWN
    screen.draw(Canvas.new(services.scenes.size))
    tap(screen, pygame.K_ESCAPE)
    assert services.scenes.current is not screen
