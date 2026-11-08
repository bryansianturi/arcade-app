from __future__ import annotations

import pygame
import pytest

from core import clipboard
from core.canvas import Canvas
from core.input import ACTIONDOWN
from core.theme import Theme
from core.widgets import Slider


def action(name: str) -> pygame.event.Event:
    return pygame.event.Event(ACTIONDOWN, action=name, repeat=False, source="keyboard", key=None)


def test_slider_snaps_clamps_and_reports_changes() -> None:
    seen: list[float] = []
    s = Slider(Theme(), (100, 0, 220, 30), 4, 64, 17.4, seen.append, step=2)
    assert s.value == 18  # snapped to a step from the minimum
    s.set_value(1000)
    s.set_value(1000)  # no change, no callback
    assert s.value == 64 and seen == [64]


def test_slider_mouse_drag_and_keys() -> None:
    s = Slider(Theme(), (100, 0, 220, 30), 0, 100, 50)
    left, right = 100 + Slider.KNOB_R, 320 - Slider.KNOB_R
    s.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=(left, 15), button=1))
    assert s.value == 0 and s.dragging
    s.handle_event(pygame.event.Event(pygame.MOUSEMOTION, pos=(right + 50, 90), rel=(0, 0)))
    assert s.value == 100  # dragging keeps working outside the widget
    s.handle_event(pygame.event.Event(pygame.MOUSEBUTTONUP, pos=(right, 15), button=1))
    assert not s.dragging
    s.handle_event(action("left"))
    assert s.value == 100  # arrows only work when focused
    s.focused = True
    s.handle_event(action("left"))
    assert s.value == 99


def test_slider_fractional_steps_and_draw() -> None:
    s = Slider(Theme(), (0, 0, 200, 30), 0.5, 4.0, 1.26, step=0.25)
    assert s.value == 1.25 and s.fraction() == pytest.approx(0.75 / 3.5)
    s.draw(Canvas.new((300, 40)))


def test_copy_text_reports_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(text: str) -> None:
        raise pygame.error("no clipboard")

    monkeypatch.setattr(pygame.scrap, "put_text", broken)
    assert clipboard.copy_text("x") is False
    monkeypatch.setattr(pygame.scrap, "put_text", lambda text: None)
    assert clipboard.copy_text("x") is True
