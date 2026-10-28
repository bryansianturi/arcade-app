from __future__ import annotations

import random
from collections import deque

from apps.snake.logic import DOWN, LEFT, MAX_SPEED, RIGHT, START_SPEED, UP, SnakeGame
from core.base_app import AppContext


def game(**kwargs: object) -> SnakeGame:
    g = SnakeGame(cols=10, rows=10, rng=random.Random(0), **kwargs)  # type: ignore[arg-type]
    g.food = None  # tests place food explicitly
    return g


def test_initial_state() -> None:
    g = SnakeGame(cols=10, rows=10, rng=random.Random(0))
    assert list(g.body) == [(5, 5), (4, 5), (3, 5)]
    assert g.direction == RIGHT and g.alive and g.score == 0
    assert g.food is not None and g.food not in g.body


def test_moves_one_cell_per_step() -> None:
    g = game()
    g.step()
    assert list(g.body) == [(6, 5), (5, 5), (4, 5)]


def test_update_steps_by_speed() -> None:
    g = game()
    g.update(0.5 / START_SPEED)
    assert g.head == (5, 5)  # half a step: not moved yet
    g.update(2.0 / START_SPEED)
    assert g.head == (7, 5)  # 2.5 steps total -> moved twice
    assert 0.4 < g.progress < 0.6


def test_cannot_reverse_into_itself() -> None:
    g = game()
    g.turn(LEFT)
    g.step()
    assert g.head == (6, 5) and g.alive


def test_quick_double_turn_is_queued() -> None:
    g = game()
    g.turn(UP)
    g.turn(LEFT)  # would be a reversal relative to RIGHT, but valid after UP
    g.step()
    g.step()
    assert list(g.body)[:2] == [(4, 4), (5, 4)]


def test_turn_queue_is_bounded() -> None:
    g = game()
    for d in (UP, LEFT, DOWN, RIGHT):
        g.turn(d)
    assert len(g._turns) == 2


def test_wall_collision_kills() -> None:
    g = game()
    for _ in range(4):
        g.step()
    assert g.head == (9, 5) and g.alive
    g.step()
    assert not g.alive and g.head == (9, 5)


def test_wrap_around() -> None:
    g = game(wrap=True)
    for _ in range(5):
        g.step()
    assert g.head == (0, 5) and g.alive
    g.turn(UP)
    for _ in range(6):
        g.step()
    assert g.head == (0, 9)


def test_eating_grows_scores_and_speeds_up() -> None:
    g = game()
    g.food = (6, 5)
    g.step()
    assert g.score == 1 and len(g.body) == 4
    assert g.speed > START_SPEED
    assert g.food is not None and g.food not in g.body


def test_speed_is_capped() -> None:
    g = game()
    g.speed = MAX_SPEED - 0.1
    g.food = (6, 5)
    g.step()
    assert g.speed == MAX_SPEED


def test_self_collision() -> None:
    g = game()
    g.body = deque([(5, 5), (4, 5), (4, 4), (5, 4), (6, 4), (6, 5)])
    g.direction = UP  # moving into (5, 4), which is part of the body
    g.step()
    assert not g.alive


def test_moving_into_the_tail_is_allowed() -> None:
    g = game()
    # A 4-long loop: the head may follow the tail, which moves away this step.
    g.body = deque([(5, 5), (5, 4), (4, 4), (4, 5)])
    g.direction = LEFT
    g.step()
    assert g.alive and g.head == (4, 5)


def test_filling_the_board_wins() -> None:
    g = SnakeGame(cols=2, rows=2, rng=random.Random(0))
    g.body = deque([(0, 0), (0, 1), (1, 1)])
    g.direction = RIGHT
    g.food = (1, 0)
    g.step()
    assert g.won and not g.alive and g.score == 1


def test_dead_snake_does_not_move() -> None:
    g = game()
    g.alive = False
    g.update(10)
    assert g.head == (5, 5)


def test_app_saves_score_per_mode(app_context: AppContext) -> None:
    from apps.snake.app import SnakeApp

    app = SnakeApp(app_context)
    app.on_enter()
    app._start()
    app.game.score = 7
    app.game.alive = False
    app.update(0.01)
    assert app.state == "over" and app.new_best
    best = app.best_score("walls")
    assert best is not None and best.score == 7
    assert app.best_score("wrap") is None

    app._set_wrap(1)
    assert app_context.storage.app_data("snake")["wrap"] is True
