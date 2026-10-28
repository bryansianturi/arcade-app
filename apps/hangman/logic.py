"""Hangman rules and word lists. Pure Python, no pygame.

Only letters are guessed; spaces and hyphens in a phrase are shown from the
start. Six misses lose the round. A hint reveals one hidden letter but costs a
miss, so it can't be used when only one miss is left.
"""

from __future__ import annotations

import random
import string
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

DATA_DIR = Path(__file__).parent / "data"
MAX_MISSES = 6
LETTERS = string.ascii_lowercase

Outcome = Literal["hit", "miss", "repeat"]


def load_words(path: Path = DATA_DIR / "words.txt") -> dict[str, list[str]]:
    """Category name → words, from a file of ``[Category]`` sections."""
    categories: dict[str, list[str]] = {}
    current: list[str] | None = None
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            current = categories.setdefault(line[1:-1], [])
        elif current is not None:
            current.append(line.lower())
    return categories


def pick_word(
    categories: dict[str, list[str]], rng: random.Random, recent: list[str]
) -> tuple[str, str]:
    """A random (category, word), avoiding the ``recent`` words when possible."""
    pool = [(c, w) for c, words in categories.items() for w in words if w not in recent]
    if not pool:
        pool = [(c, w) for c, words in categories.items() for w in words]
    return rng.choice(pool)


@dataclass
class Hangman:
    word: str
    category: str = ""
    guessed: set[str] = field(default_factory=set)
    misses: list[str] = field(default_factory=list)
    hints: int = 0
    #: Letters revealed by hints (they cost a miss but aren't wrong guesses).
    hinted: set[str] = field(default_factory=set)

    @property
    def letters(self) -> set[str]:
        return {ch for ch in self.word if ch in LETTERS}

    @property
    def miss_count(self) -> int:
        return len(self.misses) + self.hints

    @property
    def won(self) -> bool:
        return self.letters <= self.guessed

    @property
    def lost(self) -> bool:
        return self.miss_count >= MAX_MISSES

    @property
    def over(self) -> bool:
        return self.won or self.lost

    def masked(self) -> list[str | None]:
        """Each character of the word, or ``None`` where a letter is still hidden."""
        return [ch if ch not in LETTERS or ch in self.guessed else None for ch in self.word]

    def guess(self, letter: str) -> Outcome | None:
        letter = letter.lower()
        if self.over or len(letter) != 1 or letter not in LETTERS:
            return None
        if letter in self.guessed or letter in self.misses:
            return "repeat"
        if letter in self.letters:
            self.guessed.add(letter)
            return "hit"
        self.misses.append(letter)
        return "miss"

    @property
    def can_hint(self) -> bool:
        return not self.over and self.miss_count < MAX_MISSES - 1

    def hint(self, rng: random.Random) -> str | None:
        """Reveal a hidden letter for the price of one miss."""
        if not self.can_hint:
            return None
        letter = rng.choice(sorted(self.letters - self.guessed))
        self.guessed.add(letter)
        self.hinted.add(letter)
        self.hints += 1
        return letter
