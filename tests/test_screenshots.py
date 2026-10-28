"""F12 screenshots."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pygame

from core.canvas import Canvas
from core.screenshots import save_screenshot

NOW = datetime(2026, 5, 1, 9, 30, 15)


def test_saves_native_resolution_png_with_unique_names(tmp_path: Path) -> None:
    canvas = Canvas.new((64, 36), scale=2.0)
    canvas.fill((10, 200, 30))
    first = save_screenshot(canvas.surface, tmp_path, NOW)
    second = save_screenshot(canvas.surface, tmp_path, NOW)
    assert first.name == "arcade-20260501-093015.png"
    assert second.name == "arcade-20260501-093015-2.png"
    image = pygame.image.load(str(first))
    assert image.get_size() == (128, 72)
    assert image.get_at((5, 5))[:3] == (10, 200, 30)
