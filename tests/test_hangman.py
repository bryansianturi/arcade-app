"""Hangman rules: word lists, guessing, hints, and the app."""

from __future__ import annotations

import random

import pygame

from apps.hangman.logic import LETTERS, MAX_MISSES, Hangman, load_words, pick_word
from core.base_app import AppContext
from tests.conftest import key


def test_word_lists_are_clean() -> None:
    categories = load_words()
    assert len(categories) == 6
    for words in categories.values():
        assert len(words) >= 30 and len(set(words)) == len(words)
        assert all(set(w) <= set(LETTERS) | {" ", "-"} for w in words)


def test_pick_word_avoids_recent_words() -> None:
    cats = {"A": ["one", "two"], "B": ["three"]}
    rng = random.Random(1)
    assert all(pick_word(cats, rng, ["one", "two"]) == ("B", "three") for _ in range(10))
    assert pick_word(cats, rng, ["one", "two", "three"])[1] in {"one", "two", "three"}


def test_guessing_hits_misses_and_repeats() -> None:
    g = Hangman("ice cream")
    assert g.masked() == [None, None, None, " ", None, None, None, None, None]
    assert g.guess("E") == "hit"
    assert g.masked()[2] == "e" and g.masked()[6] == "e"
    assert g.guess("z") == "miss" and g.guess("z") == "repeat" and g.guess("e") == "repeat"
    assert g.guess("1") is None and g.guess("ab") is None
    assert g.miss_count == 1
    for letter in "icram":
        g.guess(letter)
    assert g.won and g.over and g.guess("q") is None


def test_six_misses_lose() -> None:
    g = Hangman("cat")
    for letter in "bdefgh":
        g.guess(letter)
    assert g.lost and g.miss_count == MAX_MISSES and not g.won


def test_hints_reveal_a_letter_and_cost_a_miss() -> None:
    g = Hangman("banana")
    letter = g.hint(random.Random(2))
    assert letter in {"b", "a", "n"} and letter in g.guessed and g.miss_count == 1
    for wrong in "xyzq":
        g.guess(wrong)
    assert g.miss_count == MAX_MISSES - 1 and not g.can_hint
    assert g.hint(random.Random(3)) is None  # a hint can't be the losing miss


def test_app_streaks_and_achievements(app_context: AppContext) -> None:
    from apps.hangman.app import HangmanApp

    app = HangmanApp(app_context)
    app.on_enter()
    assert app.uses_text_input()
    for _ in range(2):
        for letter in sorted(app.game.letters):
            app.handle_event(key(pygame.key.key_code(letter), letter))
        assert app.game.won and not app.uses_text_input()
        app.handle_event(key(pygame.K_RETURN))
    assert app.streak == 2
    best = app.best_score()
    assert best is not None and best.score == 2
    for letter in "".join(c for c in LETTERS if c not in app.game.letters)[:MAX_MISSES]:
        app.handle_event(key(pygame.key.key_code(letter), letter))
    assert app.game.lost and app.streak == 0
