"""Sudoku rules, solver and puzzle generator. Pure Python, no pygame.

Boards are flat lists of 81 ints in row-major order; ``0`` means empty.
"""

from __future__ import annotations

import random
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal

Board = list[int]
Difficulty = Literal["easy", "medium", "hard"]

DIFFICULTIES: tuple[Difficulty, ...] = ("easy", "medium", "hard")
#: Target number of given clues. Fewer clues generally means harder.
CLUES: dict[Difficulty, int] = {"easy": 40, "medium": 32, "hard": 26}

ALL_DIGITS = 0b1111111110  # bits 1..9 set


def row_of(i: int) -> int:
    return i // 9


def col_of(i: int) -> int:
    return i % 9


def box_of(i: int) -> int:
    return (i // 27) * 3 + (i % 9) // 3


def _build_peers() -> list[frozenset[int]]:
    peers = []
    for i in range(81):
        peers.append(
            frozenset(
                j
                for j in range(81)
                if j != i
                and (row_of(j) == row_of(i) or col_of(j) == col_of(i) or box_of(j) == box_of(i))
            )
        )
    return peers


#: ``PEERS[i]`` = the 20 cells sharing a row, column or box with cell ``i``.
PEERS: list[frozenset[int]] = _build_peers()


# ---------------------------------------------------------------------------- solving
def _candidates(board: Sequence[int], i: int) -> int:
    """Bitmask of digits that can legally go in cell ``i``."""
    used = 0
    for j in PEERS[i]:
        used |= 1 << board[j]
    return ALL_DIGITS & ~used


def _search(board: Board, limit: int, rng: random.Random | None, found: list[Board]) -> None:
    """Backtracking search choosing the most constrained cell first (MRV)."""
    best, best_mask, best_count = -1, 0, 10
    for i in range(81):
        if board[i] == 0:
            mask = _candidates(board, i)
            count = mask.bit_count()
            if count < best_count:
                best, best_mask, best_count = i, mask, count
                if count <= 1:
                    break
    if best == -1:
        found.append(board.copy())
        return
    if best_count == 0:
        return
    digits = [d for d in range(1, 10) if best_mask >> d & 1]
    if rng is not None:
        rng.shuffle(digits)
    for d in digits:
        board[best] = d
        _search(board, limit, rng, found)
        if len(found) >= limit:
            break
    board[best] = 0


def is_valid_placement(board: Sequence[int]) -> bool:
    """True if no two filled cells in a row/column/box share a digit."""
    return not conflicts(board)


def solve(board: Sequence[int]) -> Board | None:
    """Return a solution of ``board``, or ``None`` if it has none."""
    if not is_valid_placement(board):
        return None
    found: list[Board] = []
    _search(list(board), 1, None, found)
    return found[0] if found else None


def count_solutions(board: Sequence[int], limit: int = 2) -> int:
    """Count solutions, stopping at ``limit`` (2 is enough to test uniqueness)."""
    if not is_valid_placement(board):
        return 0
    found: list[Board] = []
    _search(list(board), limit, None, found)
    return len(found)


def conflicts(board: Sequence[int]) -> set[int]:
    """Indices of filled cells whose digit also appears in one of their peers."""
    bad: set[int] = set()
    for i, value in enumerate(board):
        if value and any(board[j] == value for j in PEERS[i]):
            bad.add(i)
    return bad


# ---------------------------------------------------------------------------- generating
def generate_solution(rng: random.Random) -> Board:
    """A random, completely filled valid grid."""
    found: list[Board] = []
    _search([0] * 81, 1, rng, found)
    return found[0]


def generate_puzzle(
    difficulty: Difficulty, rng: random.Random | None = None, attempts: int = 12
) -> tuple[Board, Board]:
    """Return ``(puzzle, solution)`` where ``puzzle`` has exactly one solution.

    Cells are removed in random symmetric pairs; a removal is kept only if the
    puzzle still has a unique solution. A single pass can get stuck above the
    clue target, so up to ``attempts`` grids are tried and the sparsest kept.
    """
    rng = rng or random.Random()
    target = CLUES[difficulty]
    best: tuple[Board, Board] | None = None
    best_clues = 82
    for _ in range(attempts):
        solution = generate_solution(rng)
        puzzle = _remove_clues(solution, target, rng)
        clues = sum(1 for v in puzzle if v)
        if clues < best_clues:
            best, best_clues = (puzzle, solution), clues
        if clues <= target:
            break
    assert best is not None
    return best


def _remove_clues(solution: Board, target: int, rng: random.Random) -> Board:
    puzzle = solution.copy()
    clues = 81
    order = list(range(41))  # cell 40 is the centre; i and 80 - i are symmetric
    rng.shuffle(order)
    for i in order:
        if clues <= target:
            break
        pair = {i, 80 - i}
        for j in pair:
            puzzle[j] = 0
        if count_solutions(puzzle, 2) == 1:
            clues -= len(pair)
        else:
            for j in pair:
                puzzle[j] = solution[j]
    return puzzle


# ---------------------------------------------------------------------------- game state
@dataclass
class _Move:
    index: int
    value: int
    notes: int
    peer_notes: dict[int, int]


@dataclass
class SudokuGame:
    """A game in progress: the player's entries, pencil notes, timer and undo stack.

    Notes are stored as bitmasks (bit ``d`` set = digit ``d`` pencilled in).
    """

    puzzle: Board
    solution: Board
    difficulty: Difficulty = "easy"
    values: Board = field(default_factory=list)
    notes: list[int] = field(default_factory=list)
    selected: int = 40
    pencil: bool = False
    elapsed: float = 0.0
    solved: bool = False
    _undo: list[_Move] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.values:
            self.values = self.puzzle.copy()
        if not self.notes:
            self.notes = [0] * 81

    @classmethod
    def new(cls, difficulty: Difficulty, rng: random.Random | None = None) -> SudokuGame:
        puzzle, solution = generate_puzzle(difficulty, rng)
        return cls(puzzle, solution, difficulty)

    # ------------------------------------------------------------------ queries
    def is_given(self, i: int) -> bool:
        return self.puzzle[i] != 0

    def conflicts(self) -> set[int]:
        return conflicts(self.values)

    def wrong_cells(self) -> set[int]:
        """Filled cells that don't match the solution (used by "Check")."""
        return {i for i in range(81) if self.values[i] and self.values[i] != self.solution[i]}

    def remaining(self, digit: int) -> int:
        """How many more of ``digit`` still need to be placed."""
        return 9 - sum(1 for v in self.values if v == digit)

    def note_digits(self, i: int) -> list[int]:
        return [d for d in range(1, 10) if self.notes[i] >> d & 1]

    # ------------------------------------------------------------------ actions
    def select(self, i: int) -> None:
        self.selected = max(0, min(80, i))

    def move(self, d_row: int, d_col: int) -> None:
        """Move the selection, wrapping around the edges."""
        r = (row_of(self.selected) + d_row) % 9
        c = (col_of(self.selected) + d_col) % 9
        self.selected = r * 9 + c

    def toggle_pencil(self) -> None:
        self.pencil = not self.pencil

    def enter(self, digit: int) -> None:
        """Place ``digit`` (or toggle a note in pencil mode) in the selected cell."""
        i = self.selected
        if self.solved or self.is_given(i) or not 1 <= digit <= 9:
            return
        if self.pencil:
            if self.values[i]:
                return
            self._record(i)
            self.notes[i] ^= 1 << digit
            return
        if self.values[i] == digit:
            return
        move = self._record(i)
        self.values[i] = digit
        self.notes[i] = 0
        # Remove this digit from the notes of every peer (and remember them for undo).
        bit = 1 << digit
        for j in PEERS[i]:
            if self.notes[j] & bit:
                move.peer_notes[j] = self.notes[j]
                self.notes[j] &= ~bit
        self.solved = self.values == self.solution

    def erase(self) -> None:
        i = self.selected
        if self.solved or self.is_given(i) or (self.values[i] == 0 and self.notes[i] == 0):
            return
        self._record(i)
        self.values[i] = 0
        self.notes[i] = 0

    def undo(self) -> bool:
        if self.solved or not self._undo:
            return False
        move = self._undo.pop()
        self.values[move.index] = move.value
        self.notes[move.index] = move.notes
        for j, notes in move.peer_notes.items():
            self.notes[j] = notes
        self.selected = move.index
        return True

    def tick(self, dt: float) -> None:
        if not self.solved:
            self.elapsed += dt

    def _record(self, i: int) -> _Move:
        move = _Move(i, self.values[i], self.notes[i], {})
        self._undo.append(move)
        return move
