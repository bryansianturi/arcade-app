"""F12 screenshots: save the current frame as a PNG in the user data folder."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pygame

FOLDER = "screenshots"


def screenshot_path(folder: Path, now: datetime) -> Path:
    """``arcade-YYYYMMDD-HHMMSS.png`` in ``folder``, with ``-2``, ``-3``... if taken."""
    stem = now.strftime("arcade-%Y%m%d-%H%M%S")
    path = folder / f"{stem}.png"
    n = 2
    while path.exists():
        path = folder / f"{stem}-{n}.png"
        n += 1
    return path


def save_screenshot(surface: pygame.Surface, data_root: Path, now: datetime | None = None) -> Path:
    """Write ``surface`` (at its native resolution) and return the file path."""
    folder = data_root / FOLDER
    folder.mkdir(parents=True, exist_ok=True)
    path = screenshot_path(folder, now or datetime.now())
    pygame.image.save(surface, str(path))
    return path
