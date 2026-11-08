from __future__ import annotations

import random

import pygame
import pytest

from apps.color_picker.logic import (
    HARMONIES,
    HSV,
    contrast,
    hsl_text,
    luminance,
    palette,
    parse_hex,
    random_color,
    rgb_text,
    to_hex,
    wcag_grade,
)
from core.base_app import AppContext
from tests.conftest import tap


@pytest.mark.parametrize(
    ("text", "rgb"),
    [("#1e90ff", (30, 144, 255)), ("1E90FF", (30, 144, 255)), (" #19f ", (17, 153, 255))],
)
def test_parse_hex(text: str, rgb: tuple[int, int, int]) -> None:
    assert parse_hex(text) == rgb


@pytest.mark.parametrize("text", ["", "#12", "#12345", "#GGGGGG", "#1234567", "-12345", "#1_2345"])
def test_parse_hex_rejects(text: str) -> None:
    assert parse_hex(text) is None


def test_text_formats() -> None:
    assert to_hex((30, 144, 255)) == "#1E90FF"
    assert rgb_text((1, 2, 3)) == "rgb(1, 2, 3)"
    assert hsl_text((255, 0, 0)) == "hsl(0, 100%, 50%)"
    assert hsl_text((30, 144, 255)) == "hsl(210, 100%, 56%)"


def test_hsv_round_trip_and_grey_keeps_hue() -> None:
    rng = random.Random(3)
    for _ in range(200):
        rgb = (rng.randrange(256), rng.randrange(256), rng.randrange(256))
        assert HSV.from_rgb(rgb).to_rgb() == rgb
    assert HSV.from_rgb((128, 128, 128), keep_hue=200).h == 200
    assert HSV(-30, 2, -1).clamped() == HSV(330, 1, 0)


def test_palettes_follow_the_color_wheel() -> None:
    base = HSV(0, 1, 1)
    assert palette(base, "complementary")[0] == (255, 0, 0)
    assert palette(base, "complementary")[2] == (0, 255, 255)
    assert palette(base, "triadic")[:3] == [(255, 0, 0), (0, 255, 0), (0, 0, 255)]
    analogous = [HSV.from_rgb(c).h for c in palette(HSV(120, 1, 1), "analogous")]
    assert analogous == pytest.approx([80, 100, 120, 140, 160], abs=1)
    for harmony in HARMONIES:
        colors = palette(random_color(random.Random(harmony)), harmony)
        assert len(colors) == 5 and all(0 <= c <= 255 for rgb in colors for c in rgb)


def test_contrast_and_grades() -> None:
    assert luminance((0, 0, 0)) == 0 and luminance((255, 255, 255)) == pytest.approx(1)
    assert contrast((0, 0, 0), (255, 255, 255)) == pytest.approx(21)
    assert contrast((118, 118, 118), (255, 255, 255)) == pytest.approx(4.54, abs=0.01)
    assert [wcag_grade(r) for r in (7.1, 4.5, 3.2, 2)] == ["AAA", "AA", "AA large", "Fail"]


def test_app_hex_entry_and_saved_color(app_context: AppContext) -> None:
    from apps.color_picker.app import ColorPickerApp

    app = ColorPickerApp(app_context)
    app.on_enter()
    app.hex_input.focus()
    app.hex_input.set_text("#")
    for ch in "336699":
        app.handle_event(pygame.event.Event(pygame.TEXTINPUT, text=ch))
    tap(app, pygame.K_RETURN)
    assert app.rgb == (51, 102, 153) and not app.hex_input.focused
    assert [s.value for s in app.sliders] == [51, 102, 153]
    app.sliders[0].set_value(0)
    assert app.rgb == (0, 102, 153) and app.hex_input.text == "#006699"
    tap(app, pygame.K_h)
    assert app.harmony == "analogous"
    app.on_exit()
    again = ColorPickerApp(app_context)
    again.on_enter()
    assert again.rgb == (0, 102, 153) and again.harmony == "analogous"
