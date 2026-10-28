"""Typing test rules: the word stream, keystroke scoring and WPM. Pure Python, no pygame.

The player types a stream of random common words against the clock. Space
commits a word; backspace can step back into an earlier word only if it was
mistyped. Speed uses the usual convention of five characters per word:

- **WPM** counts the characters of correctly typed words (plus the spaces after
  them, and a correct prefix of the word in progress).
- **Raw WPM** counts every character typed, right or wrong.
- **Accuracy** is the share of keystrokes that were correct when pressed, so a
  fixed typo still costs accuracy.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

DATA_DIR = Path(__file__).parent / "data"
DURATIONS = (15, 30, 60)
CHARS_PER_WORD = 5
#: Words are generated in chunks, always keeping this many ahead of the cursor.
LOOKAHEAD = 60
#: Extra characters allowed past the end of a word.
MAX_EXTRA = 8

CharState = Literal["correct", "wrong", "extra", "pending", "missed"]


def load_words() -> list[str]:
    lines = (DATA_DIR / "words.txt").read_text(encoding="utf-8").splitlines()
    return [w.strip() for w in lines if w.strip() and not w.startswith("#")]


def wpm(chars: float, seconds: float) -> float:
    return chars / CHARS_PER_WORD / (seconds / 60) if seconds > 0 else 0.0


@dataclass
class TypingTest:
    vocabulary: list[str]
    duration: float = 30
    rng: random.Random = field(default_factory=random.Random)
    words: list[str] = field(default_factory=list)
    typed: list[str] = field(default_factory=lambda: [""])
    elapsed: float = 0.0
    keystrokes: int = 0
    correct_keystrokes: int = 0
    #: Net WPM at the end of each whole second, for the results chart.
    samples: list[float] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._top_up()

    def _top_up(self) -> None:
        varied = len(set(self.vocabulary)) > 1
        while len(self.words) < len(self.typed) + LOOKAHEAD:
            word = self.rng.choice(self.vocabulary)
            if not (varied and self.words and word == self.words[-1]):
                self.words.append(word)

    # ------------------------------------------------------------------ state
    @property
    def index(self) -> int:
        """Index of the word being typed."""
        return len(self.typed) - 1

    @property
    def current(self) -> str:
        return self.typed[-1]

    @property
    def started(self) -> bool:
        return self.keystrokes > 0

    @property
    def finished(self) -> bool:
        return self.elapsed >= self.duration

    @property
    def remaining(self) -> float:
        return max(0.0, self.duration - self.elapsed)

    # ------------------------------------------------------------------ input
    def type_char(self, ch: str) -> None:
        if self.finished:
            return
        if ch == " ":
            self._commit()
            return
        target = self.words[self.index]
        pos = len(self.current)
        if pos >= len(target) + MAX_EXTRA:
            return
        self.keystrokes += 1
        if pos < len(target) and target[pos] == ch:
            self.correct_keystrokes += 1
        self.typed[-1] += ch

    def _commit(self) -> None:
        if not self.current:
            return  # a space with nothing typed is ignored
        self.keystrokes += 1
        if self.current == self.words[self.index]:
            self.correct_keystrokes += 1
        self.typed.append("")
        self._top_up()

    def backspace(self, whole_word: bool = False) -> None:
        if self.finished:
            return
        if not self.current:
            prev = self.index - 1
            if prev < 0 or self.typed[prev] == self.words[prev]:
                return  # correct words are locked in
            self.typed.pop()
            if not whole_word:
                return
        self.typed[-1] = "" if whole_word else self.current[:-1]

    def tick(self, dt: float) -> None:
        """Advance the clock; it only runs once the first key has been pressed."""
        if not self.started or self.finished:
            return
        before = int(self.elapsed)
        self.elapsed = min(self.duration, self.elapsed + dt)
        for second in range(before + 1, int(self.elapsed) + 1):
            self.samples.append(wpm(self.correct_chars, second))

    # ------------------------------------------------------------------ scoring
    @property
    def correct_chars(self) -> int:
        done = sum(len(t) + 1 for t, w in zip(self.typed[:-1], self.words, strict=False) if t == w)
        target = self.words[self.index]
        partial = len(self.current) if target.startswith(self.current) else 0
        return done + partial

    @property
    def typed_chars(self) -> int:
        return sum(len(t) for t in self.typed) + self.index

    @property
    def wpm(self) -> float:
        return wpm(self.correct_chars, self.elapsed)

    @property
    def raw_wpm(self) -> float:
        return wpm(self.typed_chars, self.elapsed)

    @property
    def accuracy(self) -> float:
        """Correct keystrokes as a fraction (1.0 before anything is typed)."""
        return self.correct_keystrokes / self.keystrokes if self.keystrokes else 1.0

    def char_counts(self) -> dict[CharState, int]:
        counts: dict[CharState, int] = {"correct": 0, "wrong": 0, "extra": 0, "missed": 0}
        for i in range(len(self.typed)):
            for _, state in self.char_states(i):
                if state in counts:
                    counts[state] += 1
        return counts

    def char_states(self, i: int) -> list[tuple[str, CharState]]:
        """Each displayed character of word ``i`` and how it was typed."""
        target = self.words[i]
        typed = self.typed[i] if i < len(self.typed) else ""
        committed = i < self.index
        out: list[tuple[str, CharState]] = []
        for j in range(max(len(target), len(typed))):
            if j >= len(target):
                out.append((typed[j], "extra"))
            elif j >= len(typed):
                out.append((target[j], "missed" if committed else "pending"))
            else:
                out.append((target[j], "correct" if typed[j] == target[j] else "wrong"))
        return out
