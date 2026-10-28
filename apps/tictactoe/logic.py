"""Tic-tac-toe rules and computer players. No pygame.

The unbeatable player uses minimax with alpha-beta pruning and prefers
faster wins (and slower losses), so it never plays aimlessly.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from functools import cache
from typing import Literal

Mark = Literal["X", "O"]
Cell = Literal["X", "O", ""]
Board = tuple[Cell, ...]
Level = Literal["easy", "unbeatable"]

LINES: tuple[tuple[int, int, int], ...] = (
    (0, 1, 2), (3, 4, 5), (6, 7, 8),  # rows
    (0, 3, 6), (1, 4, 7), (2, 5, 8),  # columns
    (0, 4, 8), (2, 4, 6),  # diagonals
)  # fmt: skip
EMPTY: Board = ("",) * 9


def other(mark: Mark) -> Mark:
    return "O" if mark == "X" else "X"


def winning_line(board: Board) -> tuple[int, int, int] | None:
    for line in LINES:
        a, b, c = line
        if board[a] and board[a] == board[b] == board[c]:
            return line
    return None


def winner(board: Board) -> Mark | Literal["draw"] | None:
    """``"X"``/``"O"`` if someone has three in a row, ``"draw"`` if the board is full."""
    line = winning_line(board)
    if line is not None:
        mark = board[line[0]]
        assert mark != ""
        return mark
    return "draw" if all(board) else None


def legal_moves(board: Board) -> list[int]:
    return [i for i, cell in enumerate(board) if not cell]


def play(board: Board, index: int, mark: Mark) -> Board:
    if board[index]:
        raise ValueError(f"Cell {index} is taken")
    return (*board[:index], mark, *board[index + 1 :])


@cache
def _minimax(board: Board, to_move: Mark, me: Mark, alpha: int, beta: int, depth: int) -> int:
    result = winner(board)
    if result == me:
        return 10 - depth
    if result == other(me):
        return depth - 10
    if result == "draw":
        return 0
    maximizing = to_move == me
    best = -100 if maximizing else 100
    for move in legal_moves(board):
        score = _minimax(play(board, move, to_move), other(to_move), me, alpha, beta, depth + 1)
        if maximizing:
            best = max(best, score)
            alpha = max(alpha, best)
        else:
            best = min(best, score)
            beta = min(beta, best)
        if beta <= alpha:
            break
    return best


def best_move(board: Board, mark: Mark, rng: random.Random | None = None) -> int:
    """The optimal move for ``mark``. Ties are broken randomly for variety."""
    moves = legal_moves(board)
    if not moves:
        raise ValueError("No moves left")
    scores = {m: _minimax(play(board, m, mark), other(mark), mark, -100, 100, 1) for m in moves}
    top = max(scores.values())
    choices = [m for m, s in scores.items() if s == top]
    return (rng or random).choice(choices)


def easy_move(board: Board, mark: Mark, rng: random.Random) -> int:
    """A beatable player: takes a win or blocks a loss only some of the time."""
    moves = legal_moves(board)
    for target, chance in ((mark, 0.6), (other(mark), 0.4)):
        for m in moves:
            if winner(play(board, m, target)) == target and rng.random() < chance:
                return m
    return rng.choice(moves)


@dataclass
class TicTacToe:
    """One round. The human plays ``human``; X always moves first."""

    human: Mark = "X"
    level: Level = "unbeatable"
    rng: random.Random = field(default_factory=random.Random)
    board: Board = EMPTY
    turn: Mark = "X"

    @property
    def cpu(self) -> Mark:
        return other(self.human)

    @property
    def result(self) -> Mark | Literal["draw"] | None:
        return winner(self.board)

    @property
    def cpu_to_move(self) -> bool:
        return self.result is None and self.turn == self.cpu

    def human_move(self, index: int) -> bool:
        """Play for the human. Returns ``False`` if it isn't their turn or the cell is taken."""
        if self.result is not None or self.turn != self.human or self.board[index]:
            return False
        self._apply(index)
        return True

    def cpu_move(self) -> int | None:
        if not self.cpu_to_move:
            return None
        if self.level == "unbeatable":
            index = best_move(self.board, self.cpu, self.rng)
        else:
            index = easy_move(self.board, self.cpu, self.rng)
        self._apply(index)
        return index

    def _apply(self, index: int) -> None:
        self.board = play(self.board, index, self.turn)
        self.turn = other(self.turn)
