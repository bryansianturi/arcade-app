"""Achievement service: definitions, unlocking, persistence and announcements."""

from __future__ import annotations

import pygame

from core.achievements import Achievement, AchievementService
from core.base_app import AppContext, AppMeta, BaseApp
from core.canvas import Canvas
from core.services import Services
from core.storage import Storage

DEFS = (
    Achievement("first", "First", "Do it once."),
    Achievement("secret", "Secret", "Hidden thing.", hidden=True),
)


def test_unlock_is_saved_and_announced_once(storage: Storage) -> None:
    seen: list[tuple[str, str]] = []
    service = AchievementService(storage, lambda app, a: seen.append((app, a.id)))
    service.define("demo", DEFS)
    assert service.progress("demo") == (0, 2)
    assert service.unlock("demo", "first")
    assert not service.unlock("demo", "first")  # idempotent
    assert seen == [("demo", "first")]
    assert service.is_unlocked("demo", "first") and not service.is_unlocked("demo", "secret")
    assert service.unlocked_at("demo", "first") is not None

    reloaded = AchievementService(storage)
    reloaded.define("demo", DEFS)
    assert reloaded.is_unlocked("demo", "first")
    assert reloaded.progress() == (1, 2)


def test_unknown_ids_are_ignored(storage: Storage) -> None:
    service = AchievementService(storage)
    service.define("demo", DEFS)
    assert not service.unlock("demo", "nope")
    assert not service.unlock("other_app", "first")
    assert service.progress() == (0, 2)


def test_ids_are_namespaced_per_app(storage: Storage) -> None:
    service = AchievementService(storage)
    service.define("a", DEFS)
    service.define("b", DEFS)
    service.unlock("a", "first")
    assert not service.is_unlocked("b", "first")
    assert storage.load_json("achievements.json").keys() == {"a/first"}


def test_corrupt_file_and_reset(storage: Storage) -> None:
    storage.save_json("achievements.json", {"a/first": 3, "ok/x": "2026-01-01T00:00:00"})
    service = AchievementService(storage)
    service.define("ok", (Achievement("x", "X", "x"),))
    assert service.is_unlocked("ok", "x")
    service.reset()
    assert service.progress() == (0, 1)


class Achiever(BaseApp):
    meta = AppMeta(
        id="achiever",
        name="Achiever",
        description="",
        category="game",
        accent=(10, 20, 30),
        achievements=DEFS,
    )

    def handle_event(self, event: pygame.event.Event) -> None: ...
    def update(self, dt: float) -> None:
        self.unlock_milestones(5, {"first": 3, "secret": 10})

    def draw(self, surface: Canvas) -> None: ...


def test_apps_unlock_through_context_and_toast(services: Services, app_context: AppContext) -> None:
    services.apps = [Achiever]
    services.define_achievements()
    app = Achiever(app_context)
    app.update(0.1)
    assert services.achievements.is_unlocked("achiever", "first")
    assert not services.achievements.is_unlocked("achiever", "secret")
    [toast] = services.toasts.toasts
    assert toast.title == "First" and toast.message == "Achievement unlocked · Achiever"
    assert toast.accent == (10, 20, 30)
    services.toasts.draw(Canvas.new((1280, 720)), services.theme)
    services.toasts.update(10)
    assert services.toasts.toasts == []
