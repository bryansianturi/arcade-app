"""Filesystem locations used by the arcade: bundled assets and the per-user data folder."""

from __future__ import annotations

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ASSETS_DIR = PROJECT_ROOT / "assets"
FONTS_DIR = ASSETS_DIR / "fonts"

APP_DIR_NAME = "Arcade"

#: Environment variable that overrides the data folder (handy for tests and development).
DATA_DIR_ENV = "ARCADE_DATA_DIR"


def user_data_dir() -> Path:
    """Return the platform-appropriate folder for saves, settings and logs.

    - macOS: ``~/Library/Application Support/Arcade``
    - Windows: ``%APPDATA%\\Arcade``
    - Linux/other: ``$XDG_DATA_HOME/arcade`` (default ``~/.local/share/arcade``)

    The ``ARCADE_DATA_DIR`` environment variable takes precedence when set.
    The folder is not created here; :class:`core.storage.Storage` does that lazily.
    """
    override = os.environ.get(DATA_DIR_ENV)
    if override:
        return Path(override).expanduser()

    home = Path.home()
    platform: str = sys.platform  # typed as str so mypy checks every branch
    if platform == "darwin":
        return home / "Library" / "Application Support" / APP_DIR_NAME
    if platform == "win32":
        appdata = os.environ.get("APPDATA")
        return (Path(appdata) if appdata else home / "AppData" / "Roaming") / APP_DIR_NAME
    xdg = os.environ.get("XDG_DATA_HOME")
    return (Path(xdg) if xdg else home / ".local" / "share") / APP_DIR_NAME.lower()
