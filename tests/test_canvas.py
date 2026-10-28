"""Logical-to-physical drawing: canvases, fonts and mouse mapping."""

from __future__ import annotations

from collections.abc import Iterator

import pygame
import pytest

from core import draw, gfx
from core.canvas import Canvas, Viewport, render_scale, set_viewport, to_logical
from core.display import Display
from core.theme import Theme


@pytest.fixture
def at_2x() -> Iterator[None]:
    set_viewport(Viewport(scale=2.0))
    yield
    set_viewport(Viewport())


def test_new_canvas_has_logical_size_and_native_pixels(at_2x: None) -> None:
    c = Canvas.new((100, 50), alpha=True)
    assert c.get_size() == (100, 50) and c.get_rect() == pygame.Rect(0, 0, 100, 50)
    assert c.surface.get_size() == (200, 100)


def test_rect_edges_stay_flush_at_fractional_scale() -> None:
    c = Canvas.new((10, 10), scale=1.5)
    left, right = c.px_rect((0, 0, 3, 3)), c.px_rect((3, 0, 3, 3))
    assert left.right == right.left  # no gaps or overlaps between neighbours


def test_primitives_draw_in_logical_units(at_2x: None) -> None:
    c = Canvas.new((20, 20))
    gfx.rect(c, (255, 0, 0), (5, 5, 5, 5))
    assert c.surface.get_at((10, 10))[:3] == (255, 0, 0)  # logical (5, 5)
    assert c.surface.get_at((19, 19))[:3] == (255, 0, 0)
    assert c.surface.get_at((20, 20))[:3] == (0, 0, 0)
    gfx.line(c, (0, 255, 0), (0, 15), (19, 15), 1)
    assert c.surface.get_at((10, 30))[:3] == (0, 255, 0)
    assert c.surface.get_at((10, 31))[:3] == (0, 255, 0)  # 1 logical px = 2 physical


def test_clip_round_trips_exactly() -> None:
    c = Canvas.new((100, 100), scale=1.25)
    clip = pygame.Rect(3, 7, 33, 21)
    c.set_clip(clip)
    assert c.get_clip() == clip
    c.set_clip(None)
    assert c.get_clip() == c.get_rect()


def test_font_renders_natively_with_logical_metrics() -> None:
    font = Theme().font(16)
    w1, h1 = font.size("Hello")
    image_1x = font.render("Hello", True, (255, 255, 255))
    set_viewport(Viewport(scale=2.0))
    try:
        w2, h2 = font.size("Hello")
        image_2x = font.render("Hello", True, (255, 255, 255))
    finally:
        set_viewport(Viewport())
    assert abs(w2 - w1) <= 2 and abs(h2 - h1) <= 2  # layout barely moves
    assert image_2x.surface.get_height() >= 2 * image_1x.surface.get_height() - 2
    assert image_2x.scale == 2.0


def test_blit_rescales_canvases_from_another_scale(at_2x: None) -> None:
    old = Canvas.new((10, 10), scale=1.0)
    old.fill((255, 255, 255))
    target = Canvas.new((20, 20))
    target.blit(old, (0, 0))
    assert target.surface.get_at((19, 19))[:3] == (255, 255, 255)
    assert target.surface.get_at((21, 21))[:3] == (0, 0, 0)


def test_round_corners_cuts_transparent_corners(at_2x: None) -> None:
    layer = Canvas.new((40, 40), alpha=True)
    layer.fill((255, 255, 255))
    draw.round_corners(layer, 10)
    assert layer.surface.get_at((0, 0)).a == 0
    assert layer.surface.get_at((40, 40)).a == 255


def test_mouse_maps_through_letterbox_and_retina() -> None:
    # A Retina window (2 px per point) whose canvas is drawn at 1.5x, 30 px down.
    set_viewport(Viewport(scale=1.5, offset=(0, 30), pixel_ratio=2.0))
    try:
        assert to_logical((0, 15)) == (0, 0)
        assert to_logical((480, 285)) == (640, 360)
        event = Display.to_logical(
            pygame.event.Event(pygame.MOUSEMOTION, pos=(480, 285), rel=(3, 0), buttons=(0, 0, 0))
        )
        assert event.pos == (640, 360) and event.rel == (4, 0)
        key = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_a)
        assert Display.to_logical(key) is key
    finally:
        set_viewport(Viewport())
    assert render_scale() == 1.0
