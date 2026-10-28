"""The bundle of shared objects passed to every scene."""

from __future__ import annotations

from dataclasses import dataclass, field

from core.base_app import BaseApp
from core.registry import DiscoveryFailure
from core.scene_manager import SceneManager
from core.settings import Settings
from core.storage import Storage
from core.theme import Theme


@dataclass
class Services:
    """Everything a screen needs. Apps get the smaller :class:`core.base_app.AppContext`."""

    theme: Theme
    storage: Storage
    settings: Settings
    scenes: SceneManager
    apps: list[type[BaseApp]]
    load_failures: list[DiscoveryFailure] = field(default_factory=list)

    def save_settings(self) -> None:
        """Persist settings and notify listeners (theme, window, transitions...)."""
        self.settings.save(self.storage)
        self.settings.notify()
