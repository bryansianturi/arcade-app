from __future__ import annotations

import random

import pytest

from apps.paddle_duel.logic import (
    BALL_R,
    FIELD_H,
    FIELD_W,
    PADDLE_H,
    SERVE_DELAY,
    SERVE_SPEED,
    WIN_SCORE,
    CpuController,
    Level,
    PaddleDuel,
    predict_y,
)
from core.base_app import AppContext


def served(seed: int = 0) -> PaddleDuel:
    g = PaddleDuel(random.Random(seed))
    g.update(SERVE_DELAY + 0.01)
    return g


def test_serve_after_delay() -> None:
    g = PaddleDuel(random.Random(0))
    g.update(SERVE_DELAY / 2)
    assert g.vx == 0 and g.serving
    g.update(SERVE_DELAY)
    assert not g.serving and abs(g.vx) > 0


def test_paddles_are_clamped() -> None:
    g = PaddleDuel(random.Random(0))
    g.left.move = -1
    g.right.move = 1
    g.update(5)
    assert g.left.y == PADDLE_H / 2 and g.right.y == FIELD_H - PADDLE_H / 2


def test_wall_bounce() -> None:
    g = served()
    g.ball_x, g.ball_y, g.vx, g.vy = FIELD_W / 2, BALL_R + 2, 100, -400
    events = g.update(0.05)
    assert g.vy > 0 and any(e.kind == "wall" for e in events)


@pytest.mark.parametrize(("offset", "sign"), [(-40, -1), (0, 0), (40, 1)])
def test_paddle_hit_angle_and_speedup(offset: float, sign: int) -> None:
    g = served()
    g.left.y = FIELD_H / 2
    g.ball_x, g.ball_y = g.left.face_x + 30, FIELD_H / 2 + offset
    g.vx, g.vy, g.speed = -500, 0, 500
    events = g.update(0.1)
    assert any(e.kind == "hit" and e.side == "left" for e in events)
    assert g.vx > 0 and g.speed > 500 and g.rally == 1
    assert (g.vy > 1) - (g.vy < -1) == sign


def test_moving_paddle_adds_spin() -> None:
    still, moving = served(), served()
    for g, move in ((still, 0.0), (moving, 1.0)):
        g.left.y = FIELD_H / 2
        g.left.move = move
        # Touching the face, so contact happens on the first physics step and both
        # balls hit the same spot on the paddle; only the paddle's motion differs.
        g.ball_x, g.ball_y, g.vx, g.vy = g.left.face_x + BALL_R, FIELD_H / 2, -500, 0
        g.update(1 / 60)
    assert still.rally == moving.rally == 1
    assert moving.vy > still.vy + 50


def test_missing_the_ball_scores_for_the_other_side() -> None:
    g = served()
    g.left.y = PADDLE_H / 2  # far away from the ball
    g.ball_x, g.ball_y, g.vx, g.vy = 60, FIELD_H - 40, -600, 0
    events = g.update(0.3)
    assert g.scores == {"left": 0, "right": 1}
    assert any(e.kind == "point" and e.side == "right" for e in events)
    assert g.serving and g.serve_to == "left" and g.rally == 0


def test_first_to_win_score_wins() -> None:
    g = served()
    g.scores["left"] = WIN_SCORE - 1
    g.right.y = PADDLE_H / 2
    g.ball_x, g.ball_y, g.vx, g.vy = FIELD_W - 60, FIELD_H - 40, 600, 0
    events = g.update(0.3)
    assert g.winner == "left" and any(e.kind == "match" for e in events)


def test_predict_y_unfolds_bounces() -> None:
    assert predict_y(0, 300, 100, 0, 500) == 300
    # Going up at 45°: 400 px to the right means 400 px up from y=300, bouncing off the top.
    y = predict_y(0, 300, 100, -100, 400)
    assert y == pytest.approx(BALL_R + (400 - (300 - BALL_R)))
    assert BALL_R <= predict_y(0, 300, 100, 330, 2000) <= FIELD_H - BALL_R


def play_match(left: Level, right: Level, seed: int) -> PaddleDuel:
    g = PaddleDuel(random.Random(seed))
    lc = CpuController(g.left, left, random.Random(seed + 1))
    rc = CpuController(g.right, right, random.Random(seed + 2))
    for _ in range(60 * 900):
        if g.winner is not None:
            break
        lc.update(g, 1 / 60)
        rc.update(g, 1 / 60)
        g.update(1 / 60)
    return g


def test_harder_cpu_beats_easier_cpu() -> None:
    assert all(play_match("hard", "easy", seed).winner == "left" for seed in range(3))
    assert all(play_match("easy", "medium", seed).winner == "right" for seed in range(3))


def test_even_hard_cpu_eventually_misses() -> None:
    g = play_match("hard", "hard", 0)
    assert g.winner is not None and g.best_rally < 400


def test_app_two_players_and_rally_record(app_context: AppContext) -> None:
    import pygame

    from apps.paddle_duel.app import PaddleDuelApp
    from tests.conftest import key

    app = PaddleDuelApp(app_context)
    app.on_enter()
    assert app.state == "choose" and app.menu is not None
    app.menu.buttons[-1].activate()  # 2 Players
    assert app.cpu is None and app.state == "playing"
    app.handle_event(key(pygame.K_UP))
    y = app.game.right.y
    app.update(0.1)
    assert app.game.right.y < y  # arrows drive the right paddle in 2-player mode
    app.game.best_rally = 12
    app.game.scores["left"] = WIN_SCORE
    app.game.winner = "left"
    app.update(0.01)
    assert app.state == "over" and app.new_best
    best = app.best_score("rally")
    assert best is not None and best.score == 12 and SERVE_SPEED > 0
