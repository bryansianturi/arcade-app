from __future__ import annotations

import random

from apps.star_siege.logic import (
    COLS,
    EXTRA_LIFE_EVERY,
    FIELD_W,
    PLAYER_COOLDOWN,
    PLAYER_SHOT_SPEED,
    PLAYER_W,
    PLAYER_Y,
    POINTS,
    ROWS,
    START_LIVES,
    WAVE_INTRO_SECONDS,
    Box,
    Bullet,
    Shield,
    SiegeGame,
)
from core.base_app import AppContext


def ready_game() -> SiegeGame:
    """A game past the wave intro, with no shields in the way and enemies holding fire."""
    g = SiegeGame(random.Random(0))
    g.wave_intro = 0
    g.shields = []
    g.enemy_fire_timer = 999
    return g


def test_box_intersection() -> None:
    a = Box(0, 0, 10, 10)
    assert a.intersects(Box(5, 5, 10, 10))
    assert not a.intersects(Box(10, 0, 5, 5))  # touching edges don't overlap


def test_initial_wave() -> None:
    g = SiegeGame(random.Random(0))
    assert len(g.alive_enemies()) == ROWS * COLS
    assert g.lives == START_LIVES and g.wave == 1 and len(g.shields) == 4
    assert g.wave_intro == WAVE_INTRO_SECONDS


def test_nothing_moves_during_wave_intro_but_player_can_move() -> None:
    g = SiegeGame(random.Random(0))
    x = g.formation_x
    g.move = 1
    g.update(0.5)
    assert g.formation_x == x and not g.bullets
    assert g.player_x > FIELD_W / 2
    assert not g.fire()  # no shooting during the intro


def test_player_is_clamped_to_the_field() -> None:
    g = ready_game()
    g.move = -1
    g.update(10)
    assert g.player_x == PLAYER_W / 2


def test_fire_cooldown_and_shot_limit() -> None:
    g = ready_game()
    for e in g.enemies[1:]:
        e.alive = False  # one enemy left, far from the player's shots
    g.player_x = FIELD_W - PLAYER_W
    assert g.fire()
    assert not g.fire()  # cooling down
    g.update(PLAYER_COOLDOWN + 0.01)
    assert g.fire()
    g.update(PLAYER_COOLDOWN + 0.01)
    assert sum(b.friendly for b in g.bullets) == 2
    assert not g.fire()  # at most two shots on screen


def test_shooting_an_enemy_scores() -> None:
    g = ready_game()
    target = max(g.alive_enemies(), key=lambda e: (e.row, -e.col))  # bottom row
    g.player_x = g.enemy_box(target).center[0]
    g.fire()
    events = []
    for _ in range(60):
        events += g.update(1 / 60)
    kills = [e for e in events if e.kind == "enemy_destroyed"]
    assert len(kills) == 1
    assert g.score == POINTS[kills[0].variant]
    assert len(g.alive_enemies()) == ROWS * COLS - 1


def test_formation_speeds_up_as_it_thins() -> None:
    g = ready_game()
    full = g.formation_speed()
    for e in g.enemies[:40]:
        e.alive = False
    assert g.formation_speed() > full * 2


def test_formation_drops_and_reverses_at_the_edge() -> None:
    g = ready_game()
    y = g.formation_y
    for _ in range(2000):
        g.update(1 / 60)
        if g.direction == -1:
            break
    assert g.direction == -1 and g.formation_y > y
    right = max(g.enemy_box(e).right for e in g.alive_enemies())
    assert right <= FIELD_W


def test_enemy_shot_hits_player_and_grants_invulnerability() -> None:
    g = ready_game()
    g.bullets.append(Bullet(g.player_x, PLAYER_Y - 20, 300, False))
    events = []
    for _ in range(30):
        events += g.update(1 / 60)
    assert any(e.kind == "player_hit" for e in events)
    assert g.lives == START_LIVES - 1 and g.invulnerable > 0
    g.bullets.append(Bullet(g.player_x, PLAYER_Y - 5, 300, False))
    g.update(0.1)
    assert g.lives == START_LIVES - 1  # invulnerable


def test_losing_last_life_ends_the_game() -> None:
    g = ready_game()
    g.lives = 1
    g.bullets.append(Bullet(g.player_x, PLAYER_Y - 5, 300, False))
    events = g.update(0.2)
    assert g.over and any(e.kind == "game_over" for e in events)
    g.update(1)  # nothing happens after game over
    assert g.lives == 0


def test_enemies_reaching_the_bottom_end_the_game() -> None:
    g = ready_game()
    g.formation_y = PLAYER_Y
    g.update(1 / 60)
    assert g.over


def test_shields_erode() -> None:
    shield = Shield.build(0, 0)
    before = len(shield.cells)
    hit = shield.hit(Box(40, -5, 4, 16), random.Random(0))
    assert hit is not None and len(shield.cells) < before
    assert shield.hit(Box(500, 500, 4, 4), random.Random(0)) is None
    shield.erode(Box(0, 0, 100, 100))
    assert not shield.cells


def test_shields_block_bullets() -> None:
    g = SiegeGame(random.Random(0))
    g.wave_intro = 0
    g.enemy_fire_timer = 999
    shield = g.shields[0]
    cells = len(shield.cells)
    g.player_x = shield.box.center[0] - 30  # under the solid left part of the shield
    g.fire()
    events = []
    for _ in range(40):
        events += g.update(1 / 60)
    assert any(e.kind == "shield_hit" for e in events)
    assert len(shield.cells) < cells and g.score == 0


def test_shots_cancel_each_other() -> None:
    g = ready_game()
    g.bullets = [Bullet(500, 300, -PLAYER_SHOT_SPEED, True), Bullet(500, 290, 300, False)]
    g.update(1 / 60)
    assert g.bullets == []


def test_clearing_a_wave_starts_the_next() -> None:
    g = ready_game()
    for e in g.enemies:
        e.alive = False
    events = g.update(1 / 60)
    assert any(e.kind == "wave_cleared" for e in events)
    assert g.wave == 2 and len(g.alive_enemies()) == ROWS * COLS
    assert g.formation_y > 60  # later waves start lower


def test_extra_life() -> None:
    g = ready_game()
    g._add_score(EXTRA_LIFE_EVERY)
    assert g.lives == START_LIVES + 1


def test_app_records_high_score(app_context: AppContext) -> None:
    from apps.star_siege.app import StarSiegeApp

    app = StarSiegeApp(app_context)
    app.on_enter()
    app._start()
    app.game.score = 990
    app.game.over = True
    app.update(1 / 60)
    assert app.state == "over" and app.new_best
    best = app.best_score()
    assert best is not None and best.score == 990
