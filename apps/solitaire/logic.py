"""Klondike solitaire rules. Pure Python, no pygame.

Piles are addressed by name: ``"stock"``, ``"waste"``, ``"f0"``–``"f3"``
(foundations) and ``"t0"``–``"t6"`` (tableau). A move takes the cards from
``index`` to the end of a source pile. Every change goes through
:meth:`Klondike.move` or :meth:`Klondike.draw`, which snapshot the state first
so :meth:`Klondike.undo` can step back any number of times.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Literal

Suit = Literal["spades", "hearts", "diamonds", "clubs"]
SUITS: tuple[Suit, ...] = ("spades", "hearts", "diamonds", "clubs")
RED: frozenset[Suit] = frozenset({"hearts", "diamonds"})
RANK_NAMES = {1: "A", 11: "J", 12: "Q", 13: "K"}

FOUNDATIONS = tuple(f"f{i}" for i in range(4))
TABLEAU = tuple(f"t{i}" for i in range(7))
PILES = ("stock", "waste", *FOUNDATIONS, *TABLEAU)


@dataclass(frozen=True)
class Card:
    rank: int  # 1 (ace) .. 13 (king)
    suit: Suit
    face_up: bool = False

    @property
    def red(self) -> bool:
        return self.suit in RED

    @property
    def label(self) -> str:
        return RANK_NAMES.get(self.rank, str(self.rank))

    def turned(self, face_up: bool = True) -> Card:
        return Card(self.rank, self.suit, face_up)


def new_deck() -> list[Card]:
    return [Card(rank, suit) for suit in SUITS for rank in range(1, 14)]


def stacks_on_tableau(card: Card, target: Card | None) -> bool:
    """Can ``card`` go on top of ``target`` in the tableau (``None`` = empty column)?"""
    if target is None:
        return card.rank == 13
    return target.face_up and target.red != card.red and target.rank == card.rank + 1


def stacks_on_foundation(card: Card, top: Card | None) -> bool:
    if top is None:
        return card.rank == 1
    return card.suit == top.suit and card.rank == top.rank + 1


@dataclass
class Klondike:
    rng: random.Random = field(default_factory=random.Random)
    draw_count: Literal[1, 3] = 1
    piles: dict[str, list[Card]] = field(default_factory=dict)
    moves: int = 0
    _history: list[tuple[dict[str, list[Card]], int]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.piles:
            self.deal()

    def deal(self) -> None:
        deck = new_deck()
        self.rng.shuffle(deck)
        self.piles = {name: [] for name in PILES}
        for i, name in enumerate(TABLEAU):
            column = [deck.pop() for _ in range(i + 1)]
            column[-1] = column[-1].turned()
            self.piles[name] = column
        self.piles["stock"] = deck
        self.moves = 0
        self._history.clear()

    # ------------------------------------------------------------------ queries
    def top(self, pile: str) -> Card | None:
        cards = self.piles[pile]
        return cards[-1] if cards else None

    @property
    def won(self) -> bool:
        return all(len(self.piles[f]) == 13 for f in FOUNDATIONS)

    @property
    def can_undo(self) -> bool:
        return bool(self._history)

    def can_move(self, source: str, index: int, target: str) -> bool:
        if source == target or source == "stock" or target in ("stock", "waste"):
            return False
        cards = self.piles[source]
        if not 0 <= index < len(cards) or not cards[index].face_up:
            return False
        moving = cards[index:]
        if source in ("waste", *FOUNDATIONS) and len(moving) != 1:
            return False  # only the top card of the waste or a foundation can move
        if target in FOUNDATIONS:
            return len(moving) == 1 and stacks_on_foundation(moving[0], self.top(target))
        return stacks_on_tableau(moving[0], self.top(target))

    def foundation_for(self, card: Card) -> str | None:
        """The foundation ``card`` can go to right now, if any."""
        for f in FOUNDATIONS:
            if stacks_on_foundation(card, self.top(f)):
                return f
        return None

    @property
    def can_autocomplete(self) -> bool:
        """Everything is face up and dealt: the rest is just moving cards home."""
        if self.won or self.piles["stock"] or self.piles["waste"]:
            return False
        return all(c.face_up for t in TABLEAU for c in self.piles[t])

    def legal_moves(self) -> list[tuple[str, int, str]]:
        """Every legal (source, index, target) move (used for hints and tests)."""
        found = []
        for source in ("waste", *TABLEAU, *FOUNDATIONS):
            cards = self.piles[source]
            for index in range(len(cards)):
                for target in (*FOUNDATIONS, *TABLEAU):
                    if self.can_move(source, index, target):
                        found.append((source, index, target))
        return found

    # ------------------------------------------------------------------ actions
    def _snapshot(self) -> None:
        self._history.append(({k: list(v) for k, v in self.piles.items()}, self.moves))

    def move(self, source: str, index: int, target: str) -> bool:
        """Move ``piles[source][index:]`` onto ``target`` if legal."""
        if not self.can_move(source, index, target):
            return False
        self._snapshot()
        moving = self.piles[source][index:]
        del self.piles[source][index:]
        self.piles[target].extend(moving)
        if source in TABLEAU and self.piles[source] and not self.piles[source][-1].face_up:
            self.piles[source][-1] = self.piles[source][-1].turned()
        self.moves += 1
        return True

    def auto_move(self, source: str) -> str | None:
        """Send the top card of ``source`` to a foundation. Returns the foundation used."""
        card = self.top(source)
        if card is None or not card.face_up or source in FOUNDATIONS:
            return None
        target = self.foundation_for(card)
        if target is not None and self.move(source, len(self.piles[source]) - 1, target):
            return target
        return None

    def draw(self) -> bool:
        """Turn cards from the stock to the waste, or recycle the waste. False if both empty."""
        stock, waste = self.piles["stock"], self.piles["waste"]
        if not stock and not waste:
            return False
        self._snapshot()
        if stock:
            for _ in range(min(self.draw_count, len(stock))):
                waste.append(stock.pop().turned())
        else:
            self.piles["stock"] = [c.turned(False) for c in reversed(waste)]
            self.piles["waste"] = []
        self.moves += 1
        return True

    def undo(self) -> bool:
        if not self._history:
            return False
        self.piles, self.moves = self._history.pop()
        return True

    def autocomplete_step(self) -> tuple[str, str] | None:
        """Move the lowest card that can go home. Returns (source, foundation) or None."""
        best: tuple[int, str, str] | None = None
        for source in ("waste", *TABLEAU):
            card = self.top(source)
            if card is None:
                continue
            target = self.foundation_for(card)
            if target is not None and (best is None or card.rank < best[0]):
                best = (card.rank, source, target)
        if best is None:
            return None
        _, source, target = best
        self.move(source, len(self.piles[source]) - 1, target)
        return source, target
