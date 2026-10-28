"""Typing Test rules: scoring, backspace, the clock and the app."""

from __future__ import annotations

import random

import pygame

from apps.typing_test.logic import LOOKAHEAD, TypingTest, load_words, wpm
from core.base_app import AppContext


def make(words: list[str], duration: float = 30) -> TypingTest:
    test = TypingTest(["unused"], duration)
    test.words = list(words)
    return test


def type_text(test: TypingTest, text: str) -> None:
    for ch in text:
        test.type_char(ch)


def test_word_list_is_clean() -> None:
    words = load_words()
    assert len(words) > 300 and len(set(words)) == len(words)
    assert all(w.isalpha() and w.islower() for w in words)


def test_stream_never_repeats_a_word_back_to_back_and_stays_ahead() -> None:
    test = TypingTest(load_words(), rng=random.Random(1))
    for _ in range(100):
        type_text(test, test.words[test.index] + " ")
    assert len(test.words) >= test.index + LOOKAHEAD
    assert all(a != b for a, b in zip(test.words, test.words[1:], strict=False))


def test_perfect_typing_scores_every_character() -> None:
    test = make(["the", "quick", "fox", "jumps"])
    type_text(test, "the quick fox")
    assert test.correct_chars == len("the quick fox")
    assert test.accuracy == 1.0
    test.elapsed = 12
    assert test.wpm == wpm(13, 12) == 13 / 5 / 0.2


def test_mistakes_cost_the_word_and_accuracy() -> None:
    test = make(["the", "quick", "fox"])
    type_text(test, "teh quikk ")
    assert test.correct_chars == 0
    assert test.typed_chars == len("teh quikk ")
    states = test.char_states(0)
    assert [s for _, s in states] == ["correct", "wrong", "wrong"]
    assert test.char_counts() == {"correct": 5, "wrong": 3, "extra": 0, "missed": 0}


def test_extra_and_missed_characters() -> None:
    test = make(["cat", "dog", "sun"])
    type_text(test, "cats do ")
    assert [s for _, s in test.char_states(0)] == ["correct"] * 3 + ["extra"]
    assert [s for _, s in test.char_states(1)] == ["correct", "correct", "missed"]
    assert [s for _, s in test.char_states(2)] == ["pending"] * 3


def test_backspace_fixes_typos_but_accuracy_remembers() -> None:
    test = make(["hello", "world"])
    type_text(test, "hellp")
    test.backspace()
    type_text(test, "o ")
    assert test.typed == ["hello", ""]
    assert test.correct_chars == 6
    assert test.accuracy == 6 / 7


def test_backspace_steps_back_only_into_wrong_words() -> None:
    test = make(["one", "two", "three"])
    type_text(test, "one tow ")
    test.backspace()  # back into "tow"
    assert test.index == 1 and test.current == "tow"
    test.backspace(whole_word=True)
    assert test.current == ""
    type_text(test, "two ")
    test.backspace()  # "two" is correct now: locked in
    assert test.index == 2
    test.backspace()
    test.backspace()  # never back past the start
    assert test.typed[:2] == ["one", "two"]


def test_space_on_an_empty_word_is_ignored() -> None:
    test = make(["a", "b"])
    type_text(test, "  a")
    assert test.index == 0 and test.keystrokes == 1


def test_clock_waits_for_first_key_and_samples_each_second() -> None:
    test = make(["go"] * 200, duration=15)
    test.tick(5)
    assert test.elapsed == 0
    type_text(test, "go ")
    test.tick(2.5)
    assert len(test.samples) == 2
    test.tick(100)
    assert test.finished and test.elapsed == 15 and len(test.samples) == 15
    type_text(test, "go")
    assert test.current == ""  # input is ignored after time runs out


def test_app_runs_a_test_to_the_results_card(app_context: AppContext) -> None:
    from apps.typing_test.app import TypingTestApp

    app = TypingTestApp(app_context)
    app.on_enter()
    assert app.uses_text_input()
    app.test.words = ["word"] * 200
    for _ in range(25):
        app.handle_event(pygame.event.Event(pygame.TEXTINPUT, text="word "))
    app.update(0.016)
    assert app.test.started
    app.update(10.0)
    app.update(25.0)
    assert app.menu is not None and not app.uses_text_input()
    best = app.best_score("30s")
    assert best is not None and best.score == round(app.test.wpm) == 50
    app.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_TAB, mod=0, unicode="\t"))
    assert app.menu is None and not app.test.started
