"""Five Letters rules: scoring guesses, hard mode, keyboard hints and stats. No pygame."""

from __future__ import annotations

import random
from collections import Counter
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

WORD_LENGTH = 5
MAX_GUESSES = 6
DATA_DIR = Path(__file__).parent / "data"

Mark = Literal["correct", "present", "absent"]
Status = Literal["playing", "won", "lost"]
RANK: dict[Mark, int] = {"absent": 0, "present": 1, "correct": 2}


def _read(name: str) -> list[str]:
    lines = (DATA_DIR / name).read_text(encoding="utf-8").splitlines()
    return [w.strip().lower() for w in lines if w.strip() and not w.startswith("#")]


@lru_cache(maxsize=1)
def answers() -> tuple[str, ...]:
    return tuple(_read("answers.txt"))


@lru_cache(maxsize=1)
def guesses() -> frozenset[str]:
    return frozenset(_read("guesses.txt"))


@lru_cache(maxsize=1)
def four_letter_words() -> frozenset[str]:
    return frozenset(_read("fours.txt"))


def is_valid_word(word: str) -> bool:
    """Accept dictionary words and regular plurals of four-letter words ("tears")."""
    word = word.lower()
    if len(word) != WORD_LENGTH or not word.isalpha():
        return False
    return word in guesses() or (word.endswith("s") and word[:-1] in four_letter_words())


def score_guess(guess: str, answer: str) -> list[Mark]:
    """Mark each letter of ``guess`` against ``answer``.

    Duplicates are handled like a careful human would: exact matches are
    claimed first, then each remaining answer letter can satisfy at most one
    "present" mark. E.g. guess ``speed`` vs answer ``abide`` → only one ``e`` is
    marked present.
    """
    marks: list[Mark] = ["absent"] * WORD_LENGTH
    unmatched = Counter(a for g, a in zip(guess, answer, strict=True) if g != a)
    for i, (g, a) in enumerate(zip(guess, answer, strict=True)):
        if g == a:
            marks[i] = "correct"
    for i, g in enumerate(guess):
        if marks[i] != "correct" and unmatched[g] > 0:
            marks[i] = "present"
            unmatched[g] -= 1
    return marks


def hard_mode_problem(guess: str, history: list[tuple[str, list[Mark]]]) -> str | None:
    """In hard mode, every revealed hint must be reused. Returns a message if not."""
    for word, marks in history:
        for i, (letter, mark) in enumerate(zip(word, marks, strict=True)):
            if mark == "correct" and guess[i] != letter:
                return f"Letter {i + 1} must be {letter.upper()}"
        needed = Counter(
            letter for letter, mark in zip(word, marks, strict=True) if mark != "absent"
        )
        have = Counter(guess)
        for letter, count in needed.items():
            if have[letter] < count:
                return f"Guess must contain {letter.upper()}"
    return None


@dataclass
class FiveLetters:
    answer: str
    hard: bool = False
    history: list[tuple[str, list[Mark]]] = field(default_factory=list)
    current: str = ""

    @classmethod
    def random(cls, rng: random.Random | None = None, hard: bool = False) -> FiveLetters:
        return cls((rng or random.Random()).choice(answers()), hard)

    @property
    def status(self) -> Status:
        if self.history and self.history[-1][0] == self.answer:
            return "won"
        return "lost" if len(self.history) >= MAX_GUESSES else "playing"

    def type_letter(self, letter: str) -> None:
        if self.status == "playing" and len(self.current) < WORD_LENGTH and letter.isalpha():
            self.current += letter.lower()

    def backspace(self) -> None:
        self.current = self.current[:-1]

    def submit(self) -> str | None:
        """Submit the current row. Returns an error message, or ``None`` if accepted."""
        if self.status != "playing":
            return "The round is over"
        guess = self.current
        if len(guess) < WORD_LENGTH:
            return "Not enough letters"
        if not is_valid_word(guess):
            return "Not in word list"
        if self.hard:
            problem = hard_mode_problem(guess, self.history)
            if problem:
                return problem
        self.history.append((guess, score_guess(guess, self.answer)))
        self.current = ""
        return None

    def letter_states(self) -> dict[str, Mark]:
        """Best known state per letter, for colouring the keyboard."""
        states: dict[str, Mark] = {}
        for word, marks in self.history:
            for letter, mark in zip(word, marks, strict=True):
                if letter not in states or RANK[mark] > RANK[states[letter]]:
                    states[letter] = mark
        return states


@dataclass
class Stats:
    """Lifetime statistics, stored as plain JSON-friendly data."""

    played: int = 0
    wins: int = 0
    streak: int = 0
    best_streak: int = 0
    distribution: list[int] = field(default_factory=lambda: [0] * MAX_GUESSES)

    @classmethod
    def from_dict(cls, data: Any) -> Stats:
        if not isinstance(data, dict):
            return cls()
        dist = data.get("distribution")
        if not (isinstance(dist, list) and len(dist) == MAX_GUESSES):
            dist = [0] * MAX_GUESSES
        try:
            return cls(
                int(data.get("played", 0)),
                int(data.get("wins", 0)),
                int(data.get("streak", 0)),
                int(data.get("best_streak", 0)),
                [int(v) for v in dist],
            )
        except (TypeError, ValueError):
            return cls()

    def to_dict(self) -> dict[str, Any]:
        return {
            "played": self.played,
            "wins": self.wins,
            "streak": self.streak,
            "best_streak": self.best_streak,
            "distribution": self.distribution,
        }

    def record(self, won: bool, guesses_used: int) -> None:
        self.played += 1
        if won:
            self.wins += 1
            self.streak += 1
            self.best_streak = max(self.best_streak, self.streak)
            self.distribution[guesses_used - 1] += 1
        else:
            self.streak = 0

    @property
    def win_rate(self) -> int:
        return round(100 * self.wins / self.played) if self.played else 0
