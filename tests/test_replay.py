"""Replay recording and deterministic playback."""

from __future__ import annotations

import random
from typing import Any

import pygame
import pytest

from core.base_app import AppContext, BaseApp
from core.replay import (
    MAX_STEPS_PER_FRAME,
    STEP,
    Command,
    FixedStep,
    Player,
    Recorder,
    Replay,
    ReplayStore,
)
from core.storage import Storage
from tests.conftest import tap


def test_fixed_step_accumulates() -> None:
    stepper = FixedStep()
    assert stepper.steps(STEP * 0.5) == 0
    assert stepper.steps(STEP * 0.75) == 1
    assert abs(stepper.alpha - 0.25) < 1e-9
    assert stepper.steps(10.0) == MAX_STEPS_PER_FRAME  # no spiral of death


def test_recorder_stamps_commands_with_ticks() -> None:
    rec = Recorder(seed=7)
    rec.command("turn", "left")
    rec.advance()
    rec.advance()
    rec.command("fire", True)
    rec.advance()
    run = rec.finish("demo", 12, "walls", "1.0.0")
    assert run.ticks == 3 and run.seed == 7 and run.variant == "walls"
    assert run.commands == [Command(0, "turn", ("left",)), Command(2, "fire", (True,))]
    assert abs(run.seconds - 3 * STEP) < 1e-12

    player = Player(run)
    seen = []
    while not player.done:
        seen += [(player.tick, c.name) for c in player.commands_for(player.tick)]
        player.advance()
    assert seen == [(0, "turn"), (2, "fire")] and player.progress == 1.0


def test_replay_round_trip_and_validation() -> None:
    run = Replay("demo", 1, 10, 5.0, commands=[Command(3, "x", (1, "a", 2.5, False))])
    assert Replay.from_dict(run.to_dict()) == run
    bad: list[Any] = [
        {"format": 99},
        {**run.to_dict(), "commands": [[1]]},
        {**run.to_dict(), "commands": [[-1, "x"]]},
        {**run.to_dict(), "commands": [[1, "x", [1]]]},
        {**run.to_dict(), "commands": [[11, "x"]]},
    ]
    for data in bad:
        with pytest.raises((ValueError, KeyError, TypeError)):
            Replay.from_dict(data)


def test_store_keeps_only_the_best(storage: Storage) -> None:
    store = ReplayStore(storage)
    assert store.offer(Replay("demo", 1, 10, 5.0))
    assert not store.offer(Replay("demo", 2, 10, 4.0))
    assert store.offer(Replay("demo", 3, 10, 9.0))
    assert store.offer(Replay("demo", 4, 10, 1.0, variant="other"))
    best = store.best("demo")
    assert best is not None and best.seed == 3
    assert store.offer(Replay("timed", 1, 10, 30.0), order="lower")
    assert store.offer(Replay("timed", 2, 10, 20.0), order="lower")
    assert not store.offer(Replay("timed", 3, 10, 25.0), order="lower")
    storage.save_json("replays/broken.json", {"default": {"format": 1}})
    assert store.best("broken") is None and store.best("missing") is None


def frame_times(rng: random.Random) -> float:
    """Uneven frame times, as on a real machine."""
    return rng.choice((1 / 30, 1 / 60, 1 / 60, 1 / 144, 0.05))


def capture_final_state(app: BaseApp, attr: str = "game") -> list[Any]:
    """Wrap ``_to_ready`` so the game state at the end of a replay is kept."""
    captured: list[Any] = []
    original = app._to_ready  # type: ignore[attr-defined]

    def wrapped() -> None:
        captured.append(getattr(app, attr))
        original()

    app._to_ready = wrapped  # type: ignore[attr-defined]
    return captured


def test_snake_run_replays_identically(app_context: AppContext) -> None:
    from apps.snake.app import SnakeApp

    app = SnakeApp(app_context)
    app.on_enter()
    rng = random.Random(5)
    tap(app, pygame.K_SPACE)
    for frame in range(60_000):
        if app.state != "playing":
            break
        if frame % 7 == 0:  # steer toward the food, with the odd random wobble
            (hx, hy), (fx, fy) = app.game.head, app.game.food or (0, 0)
            moves = {pygame.K_RIGHT: (1, 0), pygame.K_LEFT: (-1, 0)}
            moves |= {pygame.K_DOWN: (0, 1), pygame.K_UP: (0, -1)}
            wanted = [
                k
                for k, (dx, dy) in moves.items()
                if (dx and (fx - hx) * dx > 0) or (dy and (fy - hy) * dy > 0)
            ]
            dx, dy = app.game.direction
            options = [k for k in wanted if moves[k] != (-dx, -dy)] or [
                k for k in moves if moves[k] not in ((dx, dy), (-dx, -dy))
            ]
            if rng.random() < 0.05:
                options = list(moves)
            tap(app, rng.choice(options))
        app.update(frame_times(rng))
    assert app.state == "over"
    live = app.game
    assert live.score > 3
    best = app.best_replay()
    assert best is not None and best.score == live.score

    captured = capture_final_state(app)
    app._watch()
    playback = random.Random(99)  # completely different frame timing
    while app.state == "replay":
        app.update(frame_times(playback))
    replayed = captured[0]
    assert (replayed.score, list(replayed.body)) == (live.score, list(live.body))
    assert not replayed.alive


def test_star_siege_run_replays_identically(app_context: AppContext) -> None:
    from apps.star_siege.app import StarSiegeApp
    from tests.conftest import feed, key, key_up

    app = StarSiegeApp(app_context)
    app.on_enter()
    rng = random.Random(11)
    tap(app, pygame.K_SPACE)
    held: set[int] = set()
    for _ in range(40_000):
        if app.state != "playing":
            break
        # A deliberately weak player (so the run ends quickly): wanders, holds fire
        # in short bursts and sometimes taps a single shot.
        roll = rng.random()
        if roll < 0.03:
            k = rng.choice([pygame.K_LEFT, pygame.K_RIGHT, pygame.K_SPACE, pygame.K_SPACE])
            feed(app, key_up(k) if k in held else key(k))
            held ^= {k}
        elif roll < 0.04:
            tap(app, pygame.K_UP)
        if pygame.K_SPACE in held and rng.random() < 0.2:
            feed(app, key_up(pygame.K_SPACE))
            held.discard(pygame.K_SPACE)
        app.update(frame_times(rng))
    assert app.state == "over", "the run should end within the time limit"
    live = app.game
    assert live.score > 0
    for k in held:
        feed(app, key_up(k))

    captured: list[Any] = []
    app._end_replay = lambda: captured.append(app.game)  # type: ignore[method-assign]
    app._watch()
    playback = random.Random(3)
    for _ in range(100_000):
        if captured:
            break
        app.update(frame_times(playback))
    replayed = captured[0]
    assert (replayed.score, replayed.wave, replayed.lives) == (live.score, live.wave, live.lives)
    assert replayed.over
