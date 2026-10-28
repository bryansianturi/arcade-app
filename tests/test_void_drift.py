"""Void Drift rules: inertia, wrapping, splitting rocks, drones, lives and waves."""

from __future__ import annotations

import random

import pytest

from apps.void_drift.logic import (
    BULLET_LIFE,
    DRONE_POINTS,
    EXTRA_LIFE_EVERY,
    FIELD_H,
    FIELD_W,
    MAX_BULLETS,
    MAX_SPEED,
    RESPAWN_SECONDS,
    ROCK_SIZES,
    START_LIVES,
    WAVE_DELAY,
    Bullet,
    Drone,
    Rock,
    VoidDrift,
    distance,
    heading,
    wrap,
    wrapped_delta,
)
from core.base_app import AppContext


def game(seed: int = 1) -> VoidDrift:
    g = VoidDrift(random.Random(seed))
    g.invulnerable = 0.0
    return g


def rock_at(x: float, y: float, size: int = 3) -> Rock:
    return Rock(x, y, 0.0, 0.0, size, 0.0, 0.0, (1.0,) * 11)


def test_geometry_helpers() -> None:
    assert wrap(-1, FIELD_H + 2) == (FIELD_W - 1, 2)
    assert wrapped_delta(10, FIELD_W - 10, FIELD_W) == -20  # shorter across the edge
    assert distance(5, 5, FIELD_W - 5, 5) == pytest.approx(10)
    assert heading(0) == pytest.approx((0, -1)) and heading(90) == pytest.approx((1, 0))


def test_first_wave_spawns_large_rocks_away_from_the_ship() -> None:
    g = game()
    assert g.wave == 1 and len(g.rocks) == 4
    assert all(r.size == 3 for r in g.rocks)
    assert all(distance(r.x, r.y, g.ship.x, g.ship.y) > 200 for r in g.rocks)


def test_thrust_builds_momentum_that_drifts_on_with_drag() -> None:
    g = game()
    g.rocks.clear()
    g.wave_timer = 99  # don't advance the wave during this test
    g.thrust = True
    g.update(1.0)
    vy = g.ship.vy
    assert vy < -200  # moving "up" (angle 0)
    g.thrust = False
    g.update(0.5)
    assert vy < g.ship.vy < 0  # still drifting, but slower
    g.thrust = True
    g.update(10)
    assert abs(g.ship.vy) <= MAX_SPEED + 1e-6
    assert 0 <= g.ship.y < FIELD_H  # wrapped around the field


def test_turning() -> None:
    g = game()
    g.turn = 1
    g.update(0.5)
    assert 120 < g.ship.angle < 130
    g.turn = -1
    g.update(0.6)  # 125° - 150° = -25° → 335°
    assert 330 < g.ship.angle < 340


def test_bullets_limit_cooldown_and_lifetime() -> None:
    g = game()
    g.rocks.clear()
    g.wave_timer = 99
    assert g.fire() and not g.fire()  # cooldown
    for _ in range(MAX_BULLETS * 2):
        g.update(0.2)
        g.fire()
    assert sum(b.friendly for b in g.bullets) <= MAX_BULLETS
    g.update(BULLET_LIFE + 0.01)
    assert not g.bullets


@pytest.mark.parametrize("size", [3, 2, 1])
def test_rocks_split_and_score(size: int) -> None:
    g = game()
    g.rocks = [rock_at(600, 100, size), rock_at(100, 500)]
    g.bullets = [Bullet(600, 100, 0, 0, 1.0, True)]
    g.update(0.001)
    assert g.score == ROCK_SIZES[size][1]
    children = [r for r in g.rocks if r.size == size - 1]
    assert len(children) == (2 if size > 1 else 0)


def test_clearing_the_field_starts_the_next_wave() -> None:
    g = game()
    g.rocks = [rock_at(600, 100, 1)]
    g.bullets = [Bullet(600, 100, 0, 0, 1.0, True)]
    events = g.update(0.001)
    assert any(e.kind == "wave_cleared" for e in events)
    g.update(WAVE_DELAY + 0.1)
    assert g.wave == 2 and len(g.rocks) == 5


def test_collisions_cost_lives_then_respawn_safely() -> None:
    g = game()
    g.rocks = [rock_at(g.ship.x, g.ship.y, 1), rock_at(100, 100)]
    events = g.update(0.01)
    assert {"ship_destroyed", "rock_destroyed"} <= {e.kind for e in events}
    assert g.lives == START_LIVES - 1 and not g.ship_alive
    g.update(RESPAWN_SECONDS + 0.1)  # respawns once the center is clear of rocks
    assert g.ship_alive and g.invulnerable > 0


def test_respawn_waits_for_a_clear_center() -> None:
    g = game()
    g.rocks = [rock_at(g.ship.x, g.ship.y, 1)]
    g.update(0.01)
    g.rocks = [rock_at(FIELD_W / 2, FIELD_H / 2, 3)]
    g.rocks[0].vx = 0
    g.update(3)
    assert not g.ship_alive  # still waiting


def test_game_over_after_last_life() -> None:
    g = game()
    g.lives = 1
    g.rocks = [rock_at(g.ship.x, g.ship.y, 1), rock_at(50, 50)]
    events = g.update(0.01)
    assert g.over and any(e.kind == "game_over" for e in events)
    assert not g.fire() and not g.warp()


def test_extra_life() -> None:
    g = game()
    g.score = EXTRA_LIFE_EVERY - 10
    g.rocks = [rock_at(600, 100, 1), rock_at(50, 50)]
    g.bullets = [Bullet(600, 100, 0, 0, 1.0, True)]
    events = g.update(0.001)
    assert g.lives == START_LIVES + 1 and any(e.kind == "extra_life" for e in events)


def test_drones_appear_from_wave_two_and_can_be_shot() -> None:
    g = game()
    g.drone_timer = 0.0
    g.update(0.01)
    assert not g.drones  # not in wave 1
    g.start_wave(2)
    g.drone_timer = 0.0
    g.update(0.01)
    assert len(g.drones) == 1
    d = g.drones[0]
    g.bullets = [Bullet(d.x, d.y, 0, 0, 1.0, True)]
    g.update(0.001)
    assert not g.drones and g.drones_destroyed == 1 and g.score == DRONE_POINTS[d.kind]


def test_small_drones_aim_at_the_ship() -> None:
    g = game()
    g.rocks = [rock_at(50, 50)]
    g.drones = [Drone(300, g.ship.y, 0.0, "small", g.ship.y, fire_timer=0.0)]
    g.update(0.001)
    shot = next(b for b in g.bullets if not b.friendly)
    assert shot.vx > 0 and abs(shot.vy) < abs(shot.vx) * 0.5  # roughly toward the ship


def test_enemy_shots_hit_the_ship() -> None:
    g = game()
    g.rocks = [rock_at(50, 50)]
    g.bullets = [Bullet(g.ship.x, g.ship.y, 0, 0, 1.0, False)]
    g.update(0.001)
    assert not g.ship_alive


def test_warp_moves_the_ship_away_from_rocks() -> None:
    g = game()
    g.rocks = [rock_at(g.ship.x + 40, g.ship.y)]
    assert g.warp() and not g.warp()  # cooldown
    assert all(distance(g.ship.x, g.ship.y, r.x, r.y) > r.radius + 60 for r in g.rocks)
    assert g.invulnerable > 0


def test_same_seed_same_game() -> None:
    a, b = VoidDrift(random.Random(9)), VoidDrift(random.Random(9))
    for g in (a, b):
        g.turn, g.thrust = 1, True
        for _ in range(300):
            g.fire()
            g.update(1 / 60)
    assert (a.score, a.ship.x, len(a.rocks)) == (b.score, b.ship.x, len(b.rocks))


def test_app_plays_and_records_score(app_context: AppContext) -> None:
    import pygame

    from apps.void_drift.app import VoidDriftApp
    from tests.conftest import hold, tap

    app = VoidDriftApp(app_context)
    app.on_enter()
    tap(app, pygame.K_SPACE)
    assert app.state == "playing"
    hold(app, pygame.K_UP)
    app.update(0.5)
    assert app.game.thrust and app.game.ship.vy < 0
    app.game.lives = 1
    app.game.invulnerable = 0
    app.game.score = 120
    app.game.rocks.append(rock_at(app.game.ship.x, app.game.ship.y, 1))
    app.update(0.02)
    assert app.state == "over" and app.best_score() is not None
