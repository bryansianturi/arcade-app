"""The bundle of shared objects passed to every scene."""

from __future__ import annotations

from dataclasses import dataclass, field

from core import draw
from core.achievements import Achievement, AchievementService
from core.base_app import BaseApp
from core.favorites import Favorites
from core.input import InputMap
from core.registry import DiscoveryFailure
from core.replay import ReplayStore
from core.scene_manager import SceneManager
from core.settings import Settings
from core.stats import StatsService
from core.storage import Storage
from core.theme import Theme
from core.toasts import ToastService


@dataclass
class Services:
    """Everything a screen needs. Apps get the smaller :class:`core.base_app.AppContext`."""

    theme: Theme
    storage: Storage
    settings: Settings
    scenes: SceneManager
    apps: list[type[BaseApp]]
    load_failures: list[DiscoveryFailure] = field(default_factory=list)
    # Created from ``storage``:
    input: InputMap = field(init=False)
    toasts: ToastService = field(init=False)
    achievements: AchievementService = field(init=False)
    stats: StatsService = field(init=False)
    favorites: Favorites = field(init=False)
    replays: ReplayStore = field(init=False)

    def __post_init__(self) -> None:
        self.input = InputMap.load(self.storage)
        self.toasts = ToastService()
        self.achievements = AchievementService(self.storage, self._announce_achievement)
        self.define_achievements()
        self.stats = StatsService(self.storage)
        self.favorites = Favorites(self.storage)
        self.replays = ReplayStore(self.storage)

    def define_achievements(self) -> None:
        """Register every app's achievements (again after ``apps`` changes)."""
        for app in self.apps:
            self.achievements.define(app.meta.id, app.meta.achievements)

    def app(self, app_id: str) -> type[BaseApp] | None:
        return next((a for a in self.apps if a.meta.id == app_id), None)

    def _announce_achievement(self, app_id: str, achievement: Achievement) -> None:
        app = self.app(app_id)
        self.toasts.show(
            achievement.name,
            "Achievement unlocked" + ("" if app is None else f" · {app.meta.name}"),
            accent=None if app is None else app.meta.accent,
            icon=draw.trophy_icon,
        )

    def save_input(self) -> None:
        self.input.save(self.storage)

    def save_settings(self) -> None:
        """Persist settings and notify listeners (theme, window, transitions...)."""
        self.settings.save(self.storage)
        self.settings.notify()
