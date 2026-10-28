"""Four in a Row: gravity grid, win detection and a negamax computer player. No pygame.

Rows are numbered from the bottom (row 0) up, which makes "dropping" a disc
simply ``heights[col]``.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Literal

ROWS, COLS = 6, 7
Player = Literal[1, 2]
Grid = list[list[int]]  # grid[row][col]; 0 empty, 1 or 2 = player
Pos = tuple[int, int]  # (row, col)
Level = Literal["easy", "medium", "hard"]

LEVELS: tuple[Level, ...] = ("easy", "medium", "hard")
DEPTH: dict[Level, int] = {"easy": 1, "medium": 3, "hard": 7}  # 8 takes seconds per move
#: Columns tried centre-first: better moves are searched earlier, so pruning works better.
ORDER = (3, 2, 4, 1, 5, 0, 6)
WIN_SCORE = 1_000_000


def _windows() -> list[tuple[Pos, ...]]:
    """Every line of four cells on the board (69 of them)."""
    out = []
    for r in range(ROWS):
        for c in range(COLS):
            for dr, dc in ((0, 1), (1, 0), (1, 1), (-1, 1)):
                cells = tuple((r + dr * i, c + dc * i) for i in range(4))
                if all(0 <= rr < ROWS and 0 <= cc < COLS for rr, cc in cells):
                    out.append(cells)
    return out


WINDOWS: list[tuple[Pos, ...]] = _windows()


def other(player: Player) -> Player:
    return 2 if player == 1 else 1


@dataclass
class Board:
    grid: Grid = field(default_factory=lambda: [[0] * COLS for _ in range(ROWS)])
    heights: list[int] = field(default_factory=lambda: [0] * COLS)
    moves: int = 0

    def copy(self) -> Board:
        return Board([row[:] for row in self.grid], self.heights[:], self.moves)

    def can_drop(self, col: int) -> bool:
        return 0 <= col < COLS and self.heights[col] < ROWS

    def legal(self) -> list[int]:
        return [c for c in ORDER if self.heights[c] < ROWS]

    def drop(self, col: int, player: Player) -> int:
        """Drop a disc and return the row it landed in."""
        if not self.can_drop(col):
            raise ValueError(f"Column {col} is full or invalid")
        row = self.heights[col]
        self.grid[row][col] = player
        self.heights[col] += 1
        self.moves += 1
        return row

    def undo(self, col: int) -> None:
        self.heights[col] -= 1
        self.grid[self.heights[col]][col] = 0
        self.moves -= 1

    def full(self) -> bool:
        return self.moves == ROWS * COLS

    def winning_cells(self, row: int, col: int) -> list[Pos] | None:
        """If the disc at ``(row, col)`` completes four in a row, return those cells."""
        player = self.grid[row][col]
        if not player:
            return None
        for dr, dc in ((0, 1), (1, 0), (1, 1), (-1, 1)):
            cells = [(row, col)]
            for sign in (1, -1):
                r, c = row + dr * sign, col + dc * sign
                while 0 <= r < ROWS and 0 <= c < COLS and self.grid[r][c] == player:
                    cells.append((r, c))
                    r, c = r + dr * sign, c + dc * sign
            if len(cells) >= 4:
                return sorted(cells)
        return None


# ---------------------------------------------------------------------------- computer player
def evaluate(board: Board, player: Player) -> int:
    """Heuristic score of a non-terminal position from ``player``'s point of view."""
    opp = other(player)
    score = 0
    for row in board.grid:
        score += 3 * (row[3] == player) - 3 * (row[3] == opp)  # centre control
    for window in WINDOWS:
        mine = theirs = 0
        for r, c in window:
            v = board.grid[r][c]
            mine += v == player
            theirs += v == opp
        if mine and theirs:
            continue
        if mine == 3:
            score += 6
        elif mine == 2:
            score += 2
        elif theirs == 3:
            score -= 8  # threats against us weigh a little more
        elif theirs == 2:
            score -= 2
    return score


def _negamax(board: Board, depth: int, alpha: int, beta: int, player: Player) -> int:
    if board.full():
        return 0
    if depth == 0:
        return evaluate(board, player)
    best = -WIN_SCORE * 2
    for col in board.legal():
        row = board.drop(col, player)
        if board.winning_cells(row, col):
            score = WIN_SCORE + depth  # win sooner = better
        else:
            score = -_negamax(board, depth - 1, -beta, -alpha, other(player))
        board.undo(col)
        if score > best:
            best = score
        alpha = max(alpha, score)
        if alpha >= beta:
            break
    return best


def choose_move(board: Board, player: Player, level: Level, rng: random.Random) -> int:
    """Pick a column for ``player``. Easy plays loosely; hard looks seven moves ahead."""
    legal = board.legal()
    if not legal:
        raise ValueError("Board is full")
    if level == "easy" and rng.random() < 0.35:
        return rng.choice(legal)
    depth = DEPTH[level]
    work = board.copy()
    scores: dict[int, int] = {}
    alpha = -WIN_SCORE * 2
    for col in legal:
        row = work.drop(col, player)
        if work.winning_cells(row, col):
            score = WIN_SCORE + depth
        else:
            # Window (alpha - 1, inf): a move that can only *tie* the best so far still gets
            # an exact score, while worse moves fail low below ``alpha`` and can't be chosen.
            score = -_negamax(work, depth - 1, -WIN_SCORE * 2, -(alpha - 1), other(player))
        work.undo(col)
        scores[col] = score
        alpha = max(alpha, score)
    top = max(scores.values())
    return rng.choice([c for c, s in scores.items() if s == top])


@dataclass
class FourInARow:
    """A single round. Player 1 always moves first."""

    human: Player = 1
    level: Level = "medium"
    rng: random.Random = field(default_factory=random.Random)
    board: Board = field(default_factory=Board)
    turn: Player = 1
    winner: Player | None = None
    win_cells: list[Pos] = field(default_factory=list)
    last: Pos | None = None

    @property
    def cpu(self) -> Player:
        return other(self.human)

    @property
    def over(self) -> bool:
        return self.winner is not None or self.board.full()

    def drop(self, col: int) -> Pos | None:
        """Drop a disc for whoever's turn it is. Returns where it landed, or ``None``."""
        if self.over or not self.board.can_drop(col):
            return None
        row = self.board.drop(col, self.turn)
        self.last = (row, col)
        cells = self.board.winning_cells(row, col)
        if cells:
            self.winner = self.turn
            self.win_cells = cells
        self.turn = other(self.turn)
        return (row, col)
