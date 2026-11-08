from __future__ import annotations

import random
import string

import pygame
import pytest

from apps.password_generator.logic import (
    AMBIGUOUS,
    MAX_LENGTH,
    MIN_LENGTH,
    SYMBOLS,
    Options,
    crack_time,
    entropy_bits,
    generate,
    strength,
)
from core.base_app import AppContext
from tests.conftest import tap


@pytest.mark.parametrize("seed", range(20))
def test_every_enabled_set_is_used(seed: int) -> None:
    opts = Options(length=4)
    pw = generate(opts, random.Random(seed))
    assert len(pw) == 4
    for chars in (string.ascii_lowercase, string.ascii_uppercase, string.digits, SYMBOLS):
        assert any(c in chars for c in pw)


def test_only_enabled_sets_and_no_ambiguous() -> None:
    opts = Options(length=64, upper=False, symbols=False, avoid_ambiguous=True)
    rng = random.Random(7)
    for _ in range(50):
        pw = generate(opts, rng)
        assert set(pw) <= set(string.ascii_lowercase + string.digits) - AMBIGUOUS


def test_default_generator_is_secure_and_varied() -> None:
    passwords = {generate(Options()) for _ in range(20)}
    assert len(passwords) == 20


def test_no_sets_is_an_error() -> None:
    with pytest.raises(ValueError):
        generate(Options(lower=False, upper=False, digits=False, symbols=False))


def test_entropy_and_strength() -> None:
    assert entropy_bits(Options(length=10, upper=False, digits=False, symbols=False)) == (
        pytest.approx(10 * 4.7004, abs=0.01)  # log2(26)
    )
    assert entropy_bits(Options(lower=False, upper=False, digits=False, symbols=False)) == 0
    assert strength(0) == 0 and strength(30) == 1 and strength(59.9) == 2
    assert strength(60) == 3 and strength(200) == 4


def test_crack_time_text() -> None:
    assert crack_time(10) == "instantly"
    assert crack_time(35, guesses_per_second=1) == "544 years"
    assert crack_time(40, guesses_per_second=1) == "thousands of years"
    assert crack_time(41) == "2 minutes"
    assert crack_time(80) == "millions of years"
    assert crack_time(100) == "billions of years"


def test_options_length_clamp_and_round_trip() -> None:
    opts = Options()
    opts.set_length(1)
    assert opts.length == MIN_LENGTH
    opts.set_length(999)
    assert opts.length == MAX_LENGTH
    opts.symbols = False
    assert Options.from_dict(opts.to_dict()) == opts
    assert Options.from_dict({"length": "x", "upper": 1}) == Options()
    none_on = {"lower": False, "upper": False, "digits": False, "symbols": False}
    assert Options.from_dict(none_on).sets()  # never loads an unusable state


def test_app_keeps_one_set_and_remembers_options(app_context: AppContext) -> None:
    from apps.password_generator.app import PasswordGeneratorApp

    app = PasswordGeneratorApp(app_context)
    app.on_enter()
    first = app.password
    tap(app, pygame.K_SPACE)
    assert app.password != first and app.history == [first]
    for k in (pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4):
        tap(app, k)
    assert app.options.symbols and app.toggles[3].value  # the last set can't be turned off
    tap(app, pygame.K_RIGHT)
    assert len(app.password) == 17
    app.on_exit()
    again = PasswordGeneratorApp(app_context)
    again.on_enter()
    assert again.options == app.options and again.history == []
