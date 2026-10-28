"""The user's favorite apps, shown in their own row at the top of the launcher."""

from __future__ import annotations

from core.storage import Storage

FAVORITES_FILE = "favorites.json"


class Favorites:
    """An ordered set of app ids (in the order they were favorited)."""

    def __init__(self, storage: Storage) -> None:
        self.storage = storage
        raw = storage.load_json(FAVORITES_FILE).get("apps", [])
        ids = raw if isinstance(raw, list) else []
        self.ids: list[str] = list(dict.fromkeys(i for i in ids if isinstance(i, str)))

    def __contains__(self, app_id: object) -> bool:
        return app_id in self.ids

    def toggle(self, app_id: str) -> bool:
        """Add or remove ``app_id``; returns whether it is now a favorite."""
        if app_id in self.ids:
            self.ids.remove(app_id)
        else:
            self.ids.append(app_id)
        self.storage.save_json(FAVORITES_FILE, {"apps": self.ids})
        return app_id in self.ids
