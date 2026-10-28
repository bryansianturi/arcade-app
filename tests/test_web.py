"""Browser support, checked on the desktop: localStorage saves, no-thread work, think limits."""

from __future__ import annotations

import pytest

from core import background, web
from core.base_app import AppContext
from core.storage import BrowserStorage


class FakeLocalStorage:
    """The two ``window.localStorage`` methods the arcade uses."""

    def __init__(self) -> None:
        self.items: dict[str, str] = {}

    def getItem(self, key: str) -> str | None:  # noqa: N802 - the JavaScript name
        return self.items.get(key)

    def setItem(self, key: str, value: str) -> None:  # noqa: N802
        self.items[key] = value


def test_browser_storage_round_trips_through_local_storage() -> None:
    local = FakeLocalStorage()
    storage = BrowserStorage(local)
    assert storage.load_json("scores.json") == {}
    assert storage.record_score("snake", 12)
    assert not storage.record_score("snake", 5)
    assert "arcade/scores.json" in local.items
    data = storage.app_data("sudoku")
    data["level"] = "hard"
    data.save()
    reopened = BrowserStorage(local)  # a page reload
    assert reopened.best_score("snake") is not None
    assert reopened.app_data("sudoku")["level"] == "hard"


def test_browser_storage_survives_corrupt_values() -> None:
    local = FakeLocalStorage()
    local.items["arcade/settings.json"] = "{not json"
    local.items["arcade/scores.json"] = "[1, 2]"
    storage = BrowserStorage(local)
    assert storage.load_json("settings.json") == {}
    assert storage.load_json("scores.json") == {}


@pytest.fixture
def no_threads(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(background, "USE_THREADS", False)


@pytest.mark.usefixtures("no_threads")
def test_without_threads_work_waits_for_the_frame_loop() -> None:
    done: list[int] = []
    background.run_in_background(lambda: done.append(1))
    background.run_in_background(lambda: done.append(2))
    assert done == []
    background.run_pending()
    assert done == [1, 2]
    background.run_pending()
    assert done == [1, 2]


@pytest.mark.usefixtures("no_threads")
def test_board_game_cpu_moves_without_threads(app_context: AppContext) -> None:
    from apps.four_in_a_row.app import FourInARowApp

    app = FourInARowApp(app_context)
    app.on_enter()
    app._set_first(1)  # CPU starts
    for _ in range(60):
        app.update(1 / 30)
        background.run_pending()  # what the main loop does after each frame
        if app.game.board.moves:
            break
    assert app.game.board.moves == 1


def test_think_limit_only_caps_in_the_browser(monkeypatch: pytest.MonkeyPatch) -> None:
    assert web.think_limit(4.0) == 4.0
    monkeypatch.setattr(web, "IS_BROWSER", True)
    assert web.think_limit(4.0) == web.BROWSER_THINK_LIMIT
    assert web.think_limit(0.5) == 0.5
