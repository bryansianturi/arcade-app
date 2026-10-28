"""Echo Pads rules: playback timing, repeating, growth and the app."""

from __future__ import annotations

import random

import pygame

from apps.echo_pads.logic import LEAD, PADS, SUCCESS_PAUSE, EchoGame, step_times
from core.base_app import AppContext
from tests.conftest import feed, key, key_up


def play_back(game: EchoGame) -> list[int | None]:
    """Run playback to the end, sampling the lit pad every 10 ms."""
    seen: list[int | None] = []
    while game.state == "showing":
        game.update(0.01)
        seen.append(game.lit)
    return seen


def lit_runs(seen: list[int | None]) -> list[int]:
    """The pads lit in order, collapsing consecutive frames of the same step."""
    runs: list[int] = []
    prev: int | None = None
    for pad in seen:
        if pad is not None and prev is None:
            runs.append(pad)
        prev = pad
    return runs


def test_playback_shows_each_step_with_gaps() -> None:
    game = EchoGame(rng=random.Random(1))
    game.start()
    game.sequence = [2, 2, 0]
    assert lit_runs(play_back(game)) == [2, 2, 0]  # repeated pads still blink separately
    assert game.state == "input" and game.lit is None


def test_playback_waits_then_speeds_up() -> None:
    game = EchoGame(rng=random.Random(1))
    game.start()
    game.update(LEAD - 0.05)
    assert game.lit is None
    assert step_times(1)[0] > step_times(10)[0] > step_times(30)[0] == step_times(60)[0]


def test_repeating_grows_the_sequence_in_classic() -> None:
    game = EchoGame("classic", random.Random(2))
    game.start()
    for length in range(1, 6):
        play_back(game)
        before = list(game.sequence)
        for pad in before:
            assert game.press(pad) is True
        assert game.state == "success" and game.score == length
        game.update(SUCCESS_PAUSE)
        assert game.sequence[:length] == before and len(game.sequence) == length + 1


def test_shuffle_draws_a_new_sequence() -> None:
    game = EchoGame("shuffle", random.Random(3))
    game.start()
    prefixes_kept = 0
    for _ in range(12):
        play_back(game)
        before = list(game.sequence)
        for pad in before:
            game.press(pad)
        game.update(SUCCESS_PAUSE)
        prefixes_kept += game.sequence[: len(before)] == before
        assert len(game.sequence) == len(before) + 1
    assert prefixes_kept < 12


def test_a_wrong_pad_ends_the_game_and_presses_are_ignored_while_watching() -> None:
    game = EchoGame(rng=random.Random(4))
    game.start()
    assert game.press(0) is None  # still showing
    play_back(game)
    expected = game.sequence[0]
    wrong = (expected + 1) % PADS
    assert game.press(wrong) is False
    assert game.state == "over" and game.wrong == (wrong, expected) and game.score == 0


def test_app_plays_with_arrow_keys(app_context: AppContext) -> None:
    from apps.echo_pads.app import PAD_ACTIONS, EchoPadsApp

    keys = {
        "up": pygame.K_UP,
        "right": pygame.K_RIGHT,
        "down": pygame.K_DOWN,
        "left": pygame.K_LEFT,
    }
    app = EchoPadsApp(app_context)
    app.on_enter()
    feed(app, key(pygame.K_SPACE, " "), key_up(pygame.K_SPACE))
    for _ in range(3):
        while app.game.state != "input":
            app.update(0.02)
        for pad in list(app.game.sequence):
            k = keys[PAD_ACTIONS[pad]]
            feed(app, key(k), key_up(k))
    assert app.game.score == 3
    while app.game.state != "input":
        app.update(0.02)
    wrong = (app.game.sequence[0] + 1) % PADS
    k = keys[PAD_ACTIONS[wrong]]
    feed(app, key(k), key_up(k))
    assert app.menu is not None
    best = app.best_score("classic")
    assert best is not None and best.score == 3
