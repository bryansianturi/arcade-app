"""Firefly rules: maze, movement, motes, lanterns, shade personalities and lives."""

from __future__ import annotations

import random
from collections import deque

import pytest

from apps.firefly.logic import (
    COLS,
    DOOR,
    DOWN,
    HOUSE,
    HOUSE_EXIT,
    LANTERN_POINTS,
    LEFT,
    MAZE,
    MOTE_POINTS,
    PLAYER_START,
    RIGHT,
    ROWS,
    SCATTER_CORNERS,
    SHADE_POINTS,
    START_LIVES,
    STOP,
    UP,
    Actor,
    Firefly,
    Shade,
    find,
    is_tunnel,
    step,
    walkable,
)
from core.base_app import AppContext


def game(seed: int = 1) -> Firefly:
    return Firefly(random.Random(seed))


def reachable(start: tuple[int, int]) -> set[tuple[int, int]]:
    seen, queue = {start}, deque([start])
    while queue:
        tile = queue.popleft()
        for d in (UP, DOWN, LEFT, RIGHT):
            nxt = step(tile, d)
            if nxt not in seen and walkable(nxt):
                seen.add(nxt)
                queue.append(nxt)
    return seen


def test_maze_is_well_formed() -> None:
    assert all(len(row) == COLS for row in MAZE) and len(MAZE) == ROWS
    assert tuple(row[::-1] for row in MAZE) == MAZE  # left-right symmetric
    area = reachable(PLAYER_START)
    assert set(find(".")) | set(find("o")) <= area  # every mote is collectable
    assert len(find("o")) == 4 and DOOR not in area and not set(HOUSE) & area
    assert is_tunnel((0, 10)) and not is_tunnel((5, 10)) and (0, 10) in area


def test_player_moves_turns_and_stops_at_walls() -> None:
    g = game()
    g.want = LEFT
    g.update(0.5)
    assert g.player.tile[1] == PLAYER_START[1] and g.player.tile[0] < PLAYER_START[0]
    assert g.score > 0  # ate motes along the way
    g.want = RIGHT  # reversing is instant
    g.update(0.05)
    assert g.player.direction == RIGHT
    g.want = UP  # up is a wall at the start row's centre: keep going
    g.update(2.0)
    assert g.player.direction in (STOP, UP, RIGHT)
    assert walkable(g.player.tile)


def test_eating_motes_and_lanterns() -> None:
    g = game()
    g.motes = {(PLAYER_START[0] - 1, PLAYER_START[1])}
    g.lanterns = {(PLAYER_START[0] - 2, PLAYER_START[1])}
    g.motes.add((1, 1))  # keep the level from ending
    for s in g.shades:
        s.state = "house"
        s.house_timer = 99
    g.shades[0].state = "active"
    g.shades[0].tile = (1, 4)
    events = []
    g.want = LEFT
    for _ in range(40):
        events += g.update(1 / 60)
    kinds = [e.kind for e in events]
    assert "mote" in kinds and "lantern" in kinds
    assert g.score == MOTE_POINTS + LANTERN_POINTS
    assert g.shades[0].frightened and g.fright_timer > 0


def test_catching_frightened_shades_doubles_points() -> None:
    g = game()
    g.fright_timer = 5
    for s in g.shades:
        s.state, s.frightened = "active", True
        s.tile, s.direction, s.progress = g.player.tile, STOP, 0.0
        g._collide()
        assert s.state == "returning"
    assert g.score == sum(SHADE_POINTS)
    assert g.combo == 4


def test_a_normal_shade_costs_a_life_then_actors_reset() -> None:
    g = game()
    s = g.shades[0]
    s.tile, s.direction, s.progress = g.player.tile, STOP, 0.0
    events = g.update(1 / 60)
    assert any(e.kind == "player_caught" for e in events)
    assert g.lives == START_LIVES - 1 and g.pending == "respawn"
    g.update(2.0)
    assert g.player.tile == PLAYER_START and g.pending == ""


def test_game_over() -> None:
    g = game()
    g.lives = 1
    g.shades[0].tile, g.shades[0].direction = g.player.tile, STOP
    events = g.update(1 / 60)
    assert g.over and events[-1].kind == "game_over"


def test_clearing_the_maze_advances_the_level() -> None:
    g = game()
    g.motes = {(PLAYER_START[0] - 1, PLAYER_START[1])}
    g.lanterns = set()
    g.want = LEFT
    events = []
    for _ in range(30):
        events += g.update(1 / 60)
    assert any(e.kind == "level_clear" for e in events)
    g.update(2.5)
    assert g.level == 2 and g.remaining == len(find(".")) + len(find("o"))
    assert g.speedup > 1


def test_shades_leave_the_house_in_turn() -> None:
    g = game()
    g._collide = lambda: None  # type: ignore[method-assign]  # nobody gets caught
    states: list[tuple[str, ...]] = []
    for _ in range(12 * 60):
        g.update(1 / 60)
        states.append(tuple(s.state for s in g.shades))
    final = states[-1]
    assert final.count("house") == 0, final
    for s in g.shades:
        assert walkable(s.tile, shade=True, door=True)


def shade(personality: str, tile: tuple[int, int]) -> Shade:
    return Shade(tile, STOP, personality=personality, state="active")  # type: ignore[arg-type]


def test_personalities_pick_different_targets() -> None:
    g = game()
    g.phase = 1  # chase
    g.player = Actor((10, 16), RIGHT)
    stalker = shade("stalker", (1, 1))
    g.shades = [stalker]
    assert g.target(stalker) == (10, 16)
    assert g.target(shade("ambusher", (1, 1))) == (14, 16)
    # Flanker: pivot (12, 16) mirrored from the stalker at (1, 1) → (23, 31).
    assert g.target(shade("flanker", (5, 5))) == (23, 31)
    assert g.target(shade("wanderer", (1, 1))) == (10, 16)  # far: chases
    assert g.target(shade("wanderer", (9, 14))) == SCATTER_CORNERS["wanderer"]  # near: shy
    g.phase = 0
    assert g.target(stalker) == SCATTER_CORNERS["stalker"]


def test_shade_never_reverses_except_at_dead_ends() -> None:
    g = game()
    s = shade("stalker", (5, 4))
    s.direction = RIGHT
    g.shades = [s]
    assert g._choose(s) != LEFT


def test_frightened_shades_wander_and_slow_down() -> None:
    g = game()
    s = g.shades[0]
    normal = g._shade_speed(s)
    s.frightened = True
    assert g._shade_speed(s) < normal


def test_phase_change_reverses_shades() -> None:
    g = game()
    s = g.shades[0]
    s.tile, s.direction, s.progress = (5, 4), RIGHT, 0.3
    g.phase_timer = 0.001
    g._update_phase(0.01)
    assert s.direction == LEFT and g.phase == 1


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_long_simulation_stays_consistent(seed: int) -> None:
    g = game(seed)
    rng = random.Random(seed)
    for frame in range(60 * 60):
        if frame % 20 == 0:
            g.want = rng.choice((UP, DOWN, LEFT, RIGHT))
        g.update(1 / 60)
        if g.over:
            break
        assert walkable(g.player.tile) or g.player.tile == PLAYER_START
        for s in g.shades:
            assert walkable(s.tile, shade=True, door=True)
            assert s.tile != DOOR or s.state in ("leaving", "returning")
    assert g.score > 0


def test_house_exit_is_above_the_door() -> None:
    assert (DOOR[0], DOOR[1] - 1) == HOUSE_EXIT and walkable(HOUSE_EXIT)


def test_app_starts_and_steers(app_context: AppContext) -> None:
    import pygame

    from apps.firefly.app import FireflyApp
    from tests.conftest import hold, tap

    app = FireflyApp(app_context)
    app.on_enter()
    tap(app, pygame.K_SPACE)
    assert app.state == "playing"
    hold(app, pygame.K_LEFT)
    app.update(0.3)
    assert app.game.want == LEFT and app.game.score > 0
