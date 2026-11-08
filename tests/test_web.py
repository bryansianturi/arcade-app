"""Browser support, checked on the desktop: localStorage saves, no-thread work, think limits."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

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


class BlockedLocalStorage:
    """A browser that blocks site storage: every call throws, as Safari's private mode can."""

    def getItem(self, key: str) -> str | None:  # noqa: N802
        raise Exception("The operation is insecure.")  # how pygbag surfaces a SecurityError

    def setItem(self, key: str, value: str) -> None:  # noqa: N802
        raise Exception("The operation is insecure.")


def test_blocked_browser_storage_keeps_saves_for_the_visit() -> None:
    storage = BrowserStorage(BlockedLocalStorage())
    assert storage.load_json("settings.json") == {}  # no crash
    assert not storage.persistent
    assert storage.record_score("snake", 12)
    assert storage.best_score("snake") is not None  # still works until the page closes


def test_storage_that_fails_on_write_keeps_what_it_read() -> None:
    local = FakeLocalStorage()
    local.items["arcade/scores.json"] = '{"snake": {"default": {"score": 30, "date": "x"}}}'
    storage = BrowserStorage(local)

    def full(key: str, value: str) -> None:
        raise Exception("QuotaExceededError")

    local.setItem = full  # type: ignore[method-assign]
    assert storage.record_score("snake", 40)
    assert not storage.persistent
    best = storage.best_score("snake")
    assert best is not None and best.score == 40


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


def test_loading_card_calls_are_no_ops_on_the_desktop() -> None:
    web.loading_progress("Loading games…", 0.5)
    web.loading_failed("boom")
    web.loading_done()


def test_web_build_bundles_world_clock_zones(tmp_path: Path) -> None:
    """The browser has no time zone database; the build ships World Clock's zones."""
    pytest.importorskip("tzdata")
    from apps.world_clock.logic import CITIES
    from tools.build_web import bundle_time_zones, world_clock_zones

    assert world_clock_zones() == [c.zone for c in CITIES]
    bundle_time_zones(tmp_path)
    files = list((tmp_path / "tzdata").rglob("*"))
    assert len([f for f in files if f.is_file()]) < 80  # not the whole database
    script = (
        "import sys, zoneinfo; sys.path.insert(0, sys.argv[1]); zoneinfo.reset_tzpath([]);"
        "print(zoneinfo.ZoneInfo('America/Argentina/Buenos_Aires').key)"
    )
    result = subprocess.run(
        [sys.executable, "-I", "-S", "-c", script, str(tmp_path)],  # -S: no site-packages
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == "America/Argentina/Buenos_Aires"
