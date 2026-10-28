"""Global, user-editable settings persisted through :class:`core.storage.Storage`."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass, field, fields
from typing import Any, Literal

from core.storage import Storage

ThemeMode = Literal["dark", "light"]

SETTINGS_FILE = "settings.json"

#: Window sizes offered in the settings screen. All are 16:9, matching the canvas.
WINDOW_PRESETS: tuple[tuple[int, int], ...] = (
    (960, 540),
    (1280, 720),
    (1600, 900),
    (1920, 1080),
)


@dataclass
class Settings:
    """User preferences. Unknown or invalid keys in the JSON file are ignored."""

    theme: ThemeMode = "dark"
    window_size: tuple[int, int] = (1280, 720)
    fullscreen: bool = False
    developer_mode: bool = False  # debug overlay + F5 hot reload
    transitions: bool = True
    _listeners: list[Callable[[Settings], None]] = field(
        default_factory=list, repr=False, compare=False
    )

    @classmethod
    def load(cls, storage: Storage) -> Settings:
        """Read settings from disk, falling back to defaults for anything invalid."""
        settings = cls()
        settings.update_from_dict(storage.load_json(SETTINGS_FILE))
        return settings

    def save(self, storage: Storage) -> None:
        """Write settings to disk."""
        storage.save_json(SETTINGS_FILE, self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly dict of the public settings."""
        data = {k: v for k, v in asdict(self).items() if not k.startswith("_")}
        data["window_size"] = list(self.window_size)
        return data

    def update_from_dict(self, data: dict[str, Any]) -> None:
        """Apply values from ``data``, validating each one."""
        if data.get("theme") in ("dark", "light"):
            self.theme = data["theme"]
        size = data.get("window_size")
        if isinstance(size, list | tuple) and tuple(size) in WINDOW_PRESETS:
            self.window_size = (int(size[0]), int(size[1]))
        for name in ("fullscreen", "developer_mode", "transitions"):
            if isinstance(data.get(name), bool):
                setattr(self, name, data[name])
        if data.get("show_fps") is True and "developer_mode" not in data:
            self.developer_mode = True  # the old "Show FPS" toggle became developer mode

    def subscribe(self, listener: Callable[[Settings], None]) -> None:
        """Call ``listener`` whenever :meth:`notify` is called (after a change)."""
        self._listeners.append(listener)

    def notify(self) -> None:
        """Tell subscribers that one or more settings changed."""
        for listener in self._listeners:
            listener(self)


def public_field_names() -> list[str]:
    """Names of the persisted settings fields (used by tests)."""
    return [f.name for f in fields(Settings) if not f.name.startswith("_")]
