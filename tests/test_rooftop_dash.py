"""Rooftop Dash rules: fair generation, jumping, sliding, crashes, and a bot run."""

from __future__ import annotations

import itertools
import random

from apps.rooftop_dash.logic import (
    BASE_SPEED,
    MAX_SPEED,
    MAX_STEP_UP,
    PLAYER_W,
    REACTION,
    Obstacle,
    Roof,
    RooftopDash,
    jump_reach,
    speed_at,
)
from core.base_app import AppContext


def test_speed_ramps_and_caps() -> None:
    assert speed_at(0) == BASE_SPEED
    assert speed_at(10_000) > speed_at(1_000)
    assert speed_at(10**7) == MAX_SPEED


def test_every_gap_and_step_is_clearable() -> None:
    for seed in range(6):
        game = RooftopDash(random.Random(seed))
        roofs: list[Roof] = list(game.roofs)
        while roofs[-1].x1 < 150_000:
            game.x = roofs[-1].x1
            game._generate()
            roofs.extend(r for r in game.roofs if r.x0 > roofs[-1].x0)
        for a, b in itertools.pairwise(roofs):
            gap = b.x0 - a.x1
            assert 0 <= gap <= jump_reach(speed_at(a.x1), a.h - b.h) * 0.7 + 1e-6
            assert b.h - a.h <= MAX_STEP_UP


def test_obstacles_leave_reaction_time() -> None:
    game = RooftopDash(random.Random(3))
    obstacles: list[Obstacle] = []
    seen: set[int] = set()
    while game._gen_x < 60_000:
        game.x = game._gen_x
        game._generate()
        for ob in game.obstacles:
            if id(ob) not in seen:
                seen.add(id(ob))
                obstacles.append(ob)
    obstacles.sort(key=lambda o: o.x)
    for a, b in itertools.pairwise(obstacles):
        if a.base == b.base:
            assert b.x - a.x >= speed_at(a.x) * REACTION - 1


def flat(game: RooftopDash, obstacles: list[Obstacle]) -> None:
    game.roofs = [Roof(-500, 100_000, 100)]
    game.obstacles = obstacles
    game.coin_list = []
    game._gen_x = 10**9  # stop generating
    game.y = 100
    game.state = "running"


def test_hitting_a_crate_ends_the_run_and_jumping_clears_it() -> None:
    game = RooftopDash(random.Random(1))
    flat(game, [Obstacle(400, "crate", 100)])
    for _ in range(120):
        game.update(1 / 60, False, False)
    assert game.state == "over" and game.cause == "crate"

    game = RooftopDash(random.Random(1))
    flat(game, [Obstacle(400, "crate", 100)])
    for _ in range(240):
        if game.x + PLAYER_W / 2 > 330 and game.grounded and game.x < 400:
            game.jump()
        game.update(1 / 60, True, False)
    assert game.state == "running" and game.x > 600


def test_sliding_ducks_under_drones() -> None:
    game = RooftopDash(random.Random(2))
    flat(game, [Obstacle(400, "drone", 100)])
    for _ in range(180):
        game.update(1 / 60, False, True)
    assert game.state == "running" and game.drones_ducked == 1
    game = RooftopDash(random.Random(2))
    flat(game, [Obstacle(400, "drone", 100)])
    for _ in range(180):
        game.update(1 / 60, False, False)
    assert game.cause == "drone"


def test_holding_jumps_higher_and_buffered_jumps_fire_on_landing() -> None:
    peaks = []
    for hold in (False, True):
        game = RooftopDash(random.Random(4))
        flat(game, [])
        game.jump()
        peak = 0.0
        for _ in range(90):
            game.update(1 / 60, hold, False)
            peak = max(peak, game.y)
        peaks.append(peak)
    assert peaks[1] > peaks[0] + 40
    game = RooftopDash(random.Random(4))
    flat(game, [])
    game.y, game.grounded, game.vy = 106, False, -200  # just above the roof
    game.jump()
    for _ in range(6):
        game.update(1 / 60, False, False)
    assert game.vy > 0  # the early press still jumped


def test_running_off_the_edge_falls() -> None:
    game = RooftopDash(random.Random(5))
    flat(game, [])
    game.roofs = [Roof(-500, 300, 100)]
    for _ in range(240):
        game.update(1 / 60, False, False)
    assert game.state == "over" and game.cause == "fell"


def bot_inputs(game: RooftopDash) -> tuple[bool, bool, bool]:
    """(press jump, hold jump, slide) for a simple look-ahead bot."""
    front = game.x + PLAYER_W / 2
    speed = game.speed
    roof = game.roof_at(game.x)
    ahead = [o for o in game.obstacles if o.box[0] + o.box[2] > game.x - PLAYER_W]
    nxt = min(ahead, key=lambda o: o.x, default=None)
    slide = press = False
    hold = game.vy > 0
    if nxt is not None:
        dist = nxt.x - front
        if nxt.kind == "drone":
            slide = dist < speed * 0.25 and nxt.x + 46 > game.x - PLAYER_W
        elif dist < speed * (0.16 if nxt.kind == "crate" else 0.2):
            press = True
            hold = hold and (nxt.kind == "double" or (roof is not None and roof.x1 - front < speed))
    if roof is not None and game.grounded:
        after = game.roof_at(roof.x1 + 1)
        step_up = after is not None and after.h > roof.h
        if roof.x1 - front < speed * (0.15 if step_up else 0.06):
            press, hold = True, True
    return press, hold, slide


def test_a_bot_survives_long_runs() -> None:
    for seed in range(4):
        game = RooftopDash(random.Random(seed))
        game.jump()
        for _ in range(60 * 150):
            press, hold, slide = bot_inputs(game)
            if press:
                game.jump()
            game.update(1 / 60, hold, slide)
            if game.state == "over":
                break
        assert game.state == "running", f"seed {seed}: {game.cause} at x={game.x:.0f}"


def test_app_records_the_score(app_context: AppContext) -> None:
    from apps.rooftop_dash.app import RooftopDashApp

    app = RooftopDashApp(app_context)
    app.on_enter()
    app.game.jump()
    app.game.coins = 3
    app.game.roofs = [Roof(-500, 400, 120)]
    app.game._gen_x = 10**9
    for _ in range(200):
        app.update(0.05)
    assert app.menu is not None
    best = app.best_score()
    assert best is not None and best.score == app.game.score > 0
