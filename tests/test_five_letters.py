from __future__ import annotations

import random

import pytest

from apps.five_letters.logic import (
    MAX_GUESSES,
    FiveLetters,
    Stats,
    answers,
    guesses,
    hard_mode_problem,
    is_valid_word,
    score_guess,
)
from core.base_app import AppContext

C, P, A = "correct", "present", "absent"


def test_word_lists_are_consistent() -> None:
    assert len(answers()) > 500
    assert all(len(w) == 5 and w.isalpha() and w.islower() for w in answers())
    assert set(answers()) <= guesses()
    assert len(set(answers())) == len(answers())


@pytest.mark.parametrize(
    ("guess", "answer", "expected"),
    [
        ("crane", "crane", [C, C, C, C, C]),
        ("slate", "crane", [A, A, C, A, C]),
        ("react", "crane", [P, P, C, P, A]),
        # Duplicates: only as many marks as the answer has copies.
        ("speed", "abide", [A, A, P, A, P]),
        ("eerie", "crane", [A, A, P, A, C]),
        ("geese", "eagle", [P, P, A, A, C]),
        ("lolly", "hello", [A, P, C, C, A]),  # both answer Ls are used by exact matches
        ("mamma", "maxim", [C, C, P, A, A]),
    ],
)
def test_score_guess(guess: str, answer: str, expected: list[str]) -> None:
    assert score_guess(guess, answer) == expected


def test_valid_words_include_plurals() -> None:
    assert is_valid_word("crane") and is_valid_word("CRANE")
    assert is_valid_word("tears")  # plural of a four-letter word
    assert not is_valid_word("xqzvk")
    assert not is_valid_word("abcd") and not is_valid_word("ab1de")


def test_game_flow_win() -> None:
    g = FiveLetters("crane")
    for ch in "slatex":  # sixth letter is ignored
        g.type_letter(ch)
    assert g.current == "slate"
    assert g.submit() is None and g.status == "playing"
    for ch in "crane":
        g.type_letter(ch)
    assert g.submit() is None and g.status == "won"
    g.type_letter("a")
    assert g.current == "" and g.submit() == "The round is over"


def test_game_rejects_short_and_unknown_words() -> None:
    g = FiveLetters("crane")
    for ch in "cra":
        g.type_letter(ch)
    assert g.submit() == "Not enough letters"
    for ch in "zz":
        g.type_letter(ch)
    assert g.submit() == "Not in word list"
    assert g.history == []
    g.backspace()
    assert g.current == "craz"


def test_game_lost_after_six() -> None:
    g = FiveLetters("crane")
    for _ in range(MAX_GUESSES):
        for ch in "slate":
            g.type_letter(ch)
        g.submit()
    assert g.status == "lost"


def test_keyboard_states_keep_the_best_mark() -> None:
    g = FiveLetters("crane")
    for word in ("react", "crane"):
        for ch in word:
            g.type_letter(ch)
        g.submit()
    states = g.letter_states()
    assert states["r"] == "correct" and states["t"] == "absent"


def test_hard_mode() -> None:
    history = [("react", score_guess("react", "crane"))]  # r, e, c present; a correct
    assert hard_mode_problem("ocean", history) == "Letter 3 must be A"
    assert hard_mode_problem("brave", history) == "Guess must contain C"
    assert hard_mode_problem("crane", history) is None
    g = FiveLetters("crane", hard=True, history=list(history))
    for ch in "ocean":
        g.type_letter(ch)
    assert g.submit() == "Letter 3 must be A"


def test_stats() -> None:
    s = Stats()
    s.record(True, 3)
    s.record(True, 4)
    s.record(False, 6)
    s.record(True, 1)
    assert (s.played, s.wins, s.streak, s.best_streak) == (4, 3, 1, 2)
    assert s.distribution == [1, 0, 1, 1, 0, 0] and s.win_rate == 75
    assert Stats.from_dict(s.to_dict()) == s
    assert Stats.from_dict("garbage") == Stats()


def test_random_answers_come_from_the_list() -> None:
    assert FiveLetters.random(random.Random(1)).answer in answers()


def test_app_records_stats_and_streak(app_context: AppContext) -> None:
    import pygame

    from apps.five_letters.app import FiveLettersApp
    from tests.conftest import tap

    app = FiveLettersApp(app_context)
    app.on_enter()
    app.game = FiveLetters("crane")
    for ch in "crane":
        tap(app, getattr(pygame, f"K_{ch}"), ch)
    tap(app, pygame.K_RETURN)
    for _ in range(120):
        app.update(1 / 30)  # let the reveal animation finish
    assert app.recorded and app.stats.wins == 1
    best = app.best_score("streak")
    assert best is not None and best.score == 1
    assert app_context.storage.app_data("five_letters")["stats"]["played"] == 1
