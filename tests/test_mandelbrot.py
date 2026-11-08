from __future__ import annotations

import random

import pygame
import pytest

from apps.mandelbrot.logic import (
    BAILOUT,
    INSIDE,
    MIN_SCALE,
    PALETTES,
    PLACES,
    View,
    colour,
    escape_time,
    progressive_samples,
    suggested_iterations,
)
from core.base_app import AppContext
from tests.conftest import click, tap


def naive_escape(cr: float, ci: float, max_iter: int) -> bool:
    """Plain iteration, no shortcuts: does ``c`` escape within ``max_iter``?"""
    zr = zi = 0.0
    for _ in range(max_iter):
        if zr * zr + zi * zi > BAILOUT:
            return True
        zr, zi = zr * zr - zi * zi + cr, 2 * zr * zi + ci
    return False


@pytest.mark.parametrize(
    ("c", "inside"),
    [
        ((0, 0), True),
        ((-1, 0), True),
        ((-2, 0), True),
        ((0.25, 0), True),
        ((-0.1226, 0.7449), True),
        ((1, 0), False),
        ((0.26, 0), False),
        ((-2.1, 0), False),
        ((0, 1.1), False),
    ],
)
def test_known_points(c: tuple[float, float], inside: bool) -> None:
    assert (escape_time(*c, 2000) == INSIDE) is inside


def test_shortcuts_agree_with_plain_iteration() -> None:
    """The cardioid, bulb and periodicity checks never change the answer."""
    rng = random.Random(7)
    for _ in range(3000):
        cr, ci = rng.uniform(-2.1, 0.6), rng.uniform(-1.2, 1.2)
        assert (escape_time(cr, ci, 300) != INSIDE) == naive_escape(cr, ci, 300), (cr, ci)


def test_smooth_values_increase_towards_the_set() -> None:
    far, near = escape_time(0.5, 0, 500), escape_time(0.3, 0, 500)
    assert 0 < far < near
    assert escape_time(0.2501, 0, 50) == INSIDE  # not escaped yet within the budget


def test_progressive_samples_cover_every_pixel_once() -> None:
    seen = [(x, y) for x, y, _ in progressive_samples(37, 21)]
    assert len(seen) == len(set(seen)) == 37 * 21
    blocks = [b for *_, b in progressive_samples(37, 21)]
    assert blocks == sorted(blocks, reverse=True)  # coarse passes first
    assert blocks[0] == 8 and blocks[-1] == 1


def test_view_zoom_keeps_the_point_under_the_cursor() -> None:
    view = View()
    before = view.to_complex(300, 200, 880, 580)
    zoomed = view.zoom(3, 300, 200, 880, 580)
    after = zoomed.to_complex(300, 200, 880, 580)
    assert after == pytest.approx(before, abs=1e-12)
    assert zoomed.magnification() == pytest.approx(3)
    assert view.zoom(1e30, 0, 0, 10, 10).at_limit
    assert view.zoom(1e30, 0, 0, 10, 10).scale == MIN_SCALE
    assert view.zoom(1e-9, 0, 0, 10, 10).scale == 0.05  # can't zoom out forever


def test_view_pan_follows_the_drag() -> None:
    view = View(0, 0, 0.01)
    moved = view.pan(10, -20)  # drag right and up: the picture follows the mouse
    assert moved.to_complex(110, 80, 200, 200) == pytest.approx(view.to_complex(100, 100, 200, 200))


def test_iterations_grow_with_zoom() -> None:
    assert suggested_iterations(View()) == 120
    deep = [suggested_iterations(p.view) for p in PLACES]
    assert deep[0] == 120 and all(d > 120 for d in deep[1:])


def test_colours() -> None:
    for palette in PALETTES:
        assert colour(INSIDE, palette) == palette.inside
        for value in (0, 0.3, 7.5, 123.4, 9999):
            assert all(0 <= c <= 255 for c in colour(value, palette))
    # Smooth: nearby values give nearby colours.
    a, b = colour(10.0, PALETTES[0]), colour(10.01, PALETTES[0])
    assert max(abs(x - y) for x, y in zip(a, b, strict=True)) <= 2


def test_app_renders_progressively_and_zooms(app_context: AppContext) -> None:
    from apps.mandelbrot.app import VIEW, H, MandelbrotApp, W

    app = MandelbrotApp(app_context)
    app.on_enter()
    app._render(0.01)
    assert 0 < app.done_samples < W * H  # a slice at a time
    app._render(60)
    assert app.samples is None and app.done_samples == W * H
    for event in click((VIEW.x + 100, VIEW.y + 100)):
        app.handle_event(event)
    assert app.view.magnification() == pytest.approx(2) and app.samples is not None
    tap(app, pygame.K_r)
    assert app.view == View()
    app.iter_slider.set_value(1000)
    assert not app.auto_iter and app.max_iter == 1000
    tap(app, pygame.K_p)
    app.on_exit()
    again = MandelbrotApp(app_context)
    again.on_enter()
    assert again.palette_index == 1 and again.max_iter == 1000


def test_zoom_preview_stretches_the_old_picture(app_context: AppContext) -> None:
    from apps.mandelbrot.app import H, MandelbrotApp, W

    app = MandelbrotApp(app_context)
    app.on_enter()
    app.buffer.fill((0, 0, 0))
    app.buffer.fill((255, 0, 0), (W // 2 - 10, H // 2 - 10, 20, 20))  # a red square in the middle
    app._zoom_at(2.0, (48 + W // 2, 92 + H // 2))
    assert app.buffer.get_at((W // 2 + 15, H // 2 + 15))[:3] == (255, 0, 0)  # now twice the size
    assert app.buffer.get_at((W // 2 + 25, H // 2 + 25))[:3] == (0, 0, 0)
    app._zoom_at(0.25, (48 + W // 2, 92 + H // 2))  # zooming out shrinks it
    assert app.buffer.get_at((W // 2 + 15, H // 2 + 15))[:3] != (255, 0, 0)
