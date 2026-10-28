from __future__ import annotations

import math
import random

import pytest

from apps.brick_blitz.logic import (
    BALL_R,
    BALL_START_SPEED,
    BRICK_H,
    BRICK_W,
    COLS,
    FIELD_H,
    FIELD_W,
    LEVELS,
    PADDLE_W,
    PADDLE_Y,
    START_LIVES,
    Brick,
    BrickBlitz,
    build_level,
)
from core.base_app import AppContext


def game() -> BrickBlitz:
    return BrickBlitz(random.Random(0))


def test_levels_are_well_formed() -> None:
    for layout in LEVELS:
        assert all(len(row) == COLS for row in layout)
        assert all(set(row) <= set(".123#") for row in layout)
        assert any(b.breakable for b in build_level(LEVELS.index(layout)))


def test_bricks_fit_in_the_field() -> None:
    for i in range(len(LEVELS)):
        for b in build_level(i):
            assert b.x >= 0 and b.x + BRICK_W <= FIELD_W + 0.01
            assert b.y + BRICK_H < PADDLE_Y - 100


def test_ball_rides_the_paddle_until_launched() -> None:
    g = game()
    g.move = 1
    g.update(0.2)
    assert g.attached and g.ball_x == g.paddle_x
    g.launch()
    assert not g.attached and g.vy < 0
    assert math.hypot(g.vx, g.vy) == pytest.approx(BALL_START_SPEED)


def test_paddle_is_clamped() -> None:
    g = game()
    g.move = -1
    g.update(5)
    assert g.paddle_x == PADDLE_W / 2


def test_mouse_target_moves_paddle() -> None:
    g = game()
    g.target_x = 100
    g.update(2)
    assert g.paddle_x == pytest.approx(max(100, PADDLE_W / 2))


def test_wall_bounces() -> None:
    g = game()
    g.bricks = []
    g.attached = False
    g.ball_x, g.ball_y, g.vx, g.vy = BALL_R + 1, 300, -400, 0
    g.update(0.05)
    assert g.vx > 0
    g.ball_x, g.ball_y, g.vx, g.vy = 300, BALL_R + 1, 0, -400
    g.update(0.05)
    assert g.vy > 0


@pytest.mark.parametrize(("offset", "direction"), [(-50, -1), (0, 0), (50, 1)])
def test_paddle_angle_depends_on_hit_position(offset: float, direction: int) -> None:
    g = game()
    g.bricks = []
    g.attached = False
    g.ball_x, g.ball_y = g.paddle_x + offset, PADDLE_Y - BALL_R - 2
    g.vx, g.vy = 0, 400
    g.update(0.02)
    assert g.vy < 0
    assert (g.vx > 1) - (g.vx < -1) == direction


def test_breaking_bricks_scores_and_multi_hit_bricks_take_damage() -> None:
    g = game()
    brick = Brick(5, 0, 2, 2)
    g.bricks = [brick, Brick(0, 4, 1, 1)]
    g.attached = False
    g.ball_x = brick.x + BRICK_W / 2
    g.ball_y = brick.y + BRICK_H + BALL_R + 2
    g.vx, g.vy = 0, -400
    events = g.update(0.05)
    assert [e.kind for e in events if e.kind.startswith("brick")] == ["brick_hit"]
    assert brick.hp == 1 and g.vy > 0 and g.score == 5
    g.ball_y = brick.y + BRICK_H + BALL_R + 2
    g.vy = -400
    events = g.update(0.05)
    assert any(e.kind == "brick_broken" for e in events) and brick not in g.bricks


def test_unbreakable_bricks_bounce_but_stay() -> None:
    g = game()
    steel = Brick(5, 0, -1, -1)
    g.bricks = [steel, Brick(0, 4, 1, 1)]
    g.attached = False
    g.ball_x, g.ball_y = steel.x + BRICK_W / 2, steel.y + BRICK_H + BALL_R + 2
    g.vx, g.vy = 0, -400
    g.update(0.05)
    assert steel in g.bricks and g.vy > 0


def test_clearing_the_level_advances() -> None:
    g = game()
    last = Brick(5, 0, 1, 1)
    g.bricks = [last, Brick(0, 1, -1, -1)]  # steel doesn't need clearing
    g.attached = False
    g.ball_x, g.ball_y = last.x + BRICK_W / 2, last.y + BRICK_H + BALL_R + 2
    g.vx, g.vy = 0, -400
    events = g.update(0.05)
    assert any(e.kind == "level_clear" for e in events)
    assert g.level == 1 and g.attached and g.remaining() > 0


def test_losing_all_lives_ends_the_game() -> None:
    g = game()
    for _ in range(START_LIVES):
        g.attached = False
        g.ball_x, g.ball_y, g.vx, g.vy = 20, FIELD_H - 5, 0, 400
        events = g.update(0.1)
        assert any(e.kind == "life_lost" for e in events)
    assert g.over and g.lives == 0


def test_ball_never_tunnels_at_max_speed() -> None:
    g = game()
    g.attached = False
    rng = random.Random(5)
    for _ in range(600):
        g.update(1 / 30)  # low frame rate on purpose
        assert -BALL_R <= g.ball_x <= FIELD_W + BALL_R
        assert g.ball_y >= -BALL_R
        if g.attached:
            g.launch()
        g.target_x = g.ball_x + rng.uniform(-20, 20)  # an almost perfect player
        if g.over:
            break


def test_app_records_score(app_context: AppContext) -> None:
    from apps.brick_blitz.app import BrickBlitzApp

    app = BrickBlitzApp(app_context)
    app.on_enter()
    app.game.score = 777
    app.game.lives = 1
    app.game.attached = False
    app.game.ball_x, app.game.ball_y, app.game.vx, app.game.vy = 20, FIELD_H - 5, 0, 400
    app.update(0.1)
    assert app.state == "over" and app.new_best
