"""Checkers (English draughts) rules and a small engine. Pure Python, no pygame.

The board is 8×8 and only dark squares (``(row + col) % 2 == 1``) are used.
``"d"``/``"D"`` are dark men/kings, ``"l"``/``"L"`` light men/kings, ``"."``
empty. Dark starts at the bottom (rows 5–7), moves up the board and moves first.

Rules implemented:

* Men move diagonally forward one square; kings move both ways.
* Captures are compulsory, and a capturing piece must keep jumping while it can
  (a move is a whole jump sequence). Any capture sequence may be chosen.
* A man reaching the far row is crowned; if that happens mid-capture, the move ends.
* A player who cannot move loses. 40 moves each without a capture or a man move
  is a draw.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from typing import Literal

Side = Literal["dark", "light"]
Square = tuple[int, int]  # (row, col)
SIZE = 8
DRAW_PLIES = 80  # 40 moves each without progress

FORWARD: dict[Side, int] = {"dark": -1, "light": 1}
KING_ROW: dict[Side, int] = {"dark": 0, "light": SIZE - 1}


def side_of(piece: str) -> Side:
    return "dark" if piece.lower() == "d" else "light"


def opponent(side: Side) -> Side:
    return "light" if side == "dark" else "dark"


def is_king(piece: str) -> bool:
    return piece.isupper()


@dataclass(frozen=True)
class Move:
    path: tuple[Square, ...]  # start, then every landing square
    captures: tuple[Square, ...] = ()

    @property
    def start(self) -> Square:
        return self.path[0]

    @property
    def end(self) -> Square:
        return self.path[-1]


def initial_board() -> list[list[str]]:
    board = [["."] * SIZE for _ in range(SIZE)]
    for r in range(SIZE):
        for c in range(SIZE):
            if (r + c) % 2 == 1:
                if r < 3:
                    board[r][c] = "l"
                elif r > 4:
                    board[r][c] = "d"
    return board


@dataclass
class Checkers:
    board: list[list[str]] = field(default_factory=initial_board)
    turn: Side = "dark"
    quiet_plies: int = 0  # plies since the last capture or man move
    _history: list[tuple[list[list[str]], Side, int]] = field(default_factory=list)

    # ------------------------------------------------------------------ queries
    def piece(self, sq: Square) -> str:
        return self.board[sq[0]][sq[1]]

    def pieces(self, side: Side) -> list[Square]:
        return [
            (r, c)
            for r in range(SIZE)
            for c in range(SIZE)
            if self.board[r][c] != "." and side_of(self.board[r][c]) == side
        ]

    def _directions(self, piece: str) -> list[tuple[int, int]]:
        if is_king(piece):
            return [(-1, -1), (-1, 1), (1, -1), (1, 1)]
        f = FORWARD[side_of(piece)]
        return [(f, -1), (f, 1)]

    def _jumps_from(
        self,
        sq: Square,
        piece: str,
        path: tuple[Square, ...],
        captured: tuple[Square, ...],
        out: list[Move],
    ) -> None:
        r, c = sq
        extended = False
        for dr, dc in self._directions(piece):
            mid, land = (r + dr, c + dc), (r + 2 * dr, c + 2 * dc)
            if not (0 <= land[0] < SIZE and 0 <= land[1] < SIZE):
                continue
            victim = self.piece(mid)
            if victim == "." or side_of(victim) == side_of(piece) or mid in captured:
                continue
            if self.piece(land) != "." and land != path[0]:  # the start square is vacated
                continue
            extended = True
            crowned = not is_king(piece) and land[0] == KING_ROW[side_of(piece)]
            if crowned:  # crowning ends the move
                out.append(Move((*path, land), (*captured, mid)))
            else:
                self._jumps_from(land, piece, (*path, land), (*captured, mid), out)
        if not extended and captured:
            out.append(Move(path, captured))

    def legal_moves(self, side: Side | None = None) -> list[Move]:
        side = side or self.turn
        jumps: list[Move] = []
        for sq in self.pieces(side):
            self._jumps_from(sq, self.piece(sq), (sq,), (), jumps)
        if jumps:
            return jumps  # capturing is compulsory
        moves = []
        for sq in self.pieces(side):
            piece = self.piece(sq)
            for dr, dc in self._directions(piece):
                to = (sq[0] + dr, sq[1] + dc)
                if 0 <= to[0] < SIZE and 0 <= to[1] < SIZE and self.piece(to) == ".":
                    moves.append(Move((sq, to)))
        return moves

    def must_capture(self) -> bool:
        moves = self.legal_moves()
        return bool(moves and moves[0].captures)

    def winner(self) -> Side | None:
        if not self.legal_moves():
            return opponent(self.turn)
        return None

    @property
    def draw(self) -> bool:
        return self.quiet_plies >= DRAW_PLIES and self.winner() is None

    @property
    def over(self) -> bool:
        return self.winner() is not None or self.draw

    # ------------------------------------------------------------------ actions
    def play(self, move: Move) -> bool:
        """Play ``move`` if it is legal. Returns whether a man was crowned."""
        if move not in self.legal_moves():
            raise ValueError("illegal move")
        self._history.append(([row[:] for row in self.board], self.turn, self.quiet_plies))
        return self._apply(move)

    def _apply(self, move: Move) -> bool:
        piece = self.piece(move.start)
        self.board[move.start[0]][move.start[1]] = "."
        for r, c in move.captures:
            self.board[r][c] = "."
        crowned = not is_king(piece) and move.end[0] == KING_ROW[side_of(piece)]
        if crowned:
            piece = piece.upper()
        self.board[move.end[0]][move.end[1]] = piece
        progress = bool(move.captures) or not is_king(self.piece(move.end)) or crowned
        self.quiet_plies = 0 if progress else self.quiet_plies + 1
        self.turn = opponent(self.turn)
        return crowned

    def undo(self) -> bool:
        if not self._history:
            return False
        self.board, self.turn, self.quiet_plies = self._history.pop()
        return True

    @property
    def can_undo(self) -> bool:
        return bool(self._history)

    def copy(self) -> Checkers:
        return Checkers([row[:] for row in self.board], self.turn, self.quiet_plies)


# ---------------------------------------------------------------------- engine
MAN, KING = 100, 165
WIN = 100_000


def evaluate(game: Checkers) -> int:
    """Score from the point of view of the side to move."""
    score = 0
    for r in range(SIZE):
        for c in range(SIZE):
            piece = game.board[r][c]
            if piece == ".":
                continue
            side = side_of(piece)
            if is_king(piece):
                value = KING + (3 if 2 <= r <= 5 and 2 <= c <= 5 else 0)  # kings like the centre
            else:
                advance = (SIZE - 1 - r) if side == "dark" else r
                back_row = (
                    6 if r == (SIZE - 1 if side == "dark" else 0) else 0
                )  # guards the king row
                value = MAN + advance * 4 + back_row
            score += value if side == "dark" else -value
    return score if game.turn == "dark" else -score


class _TimeoutError(Exception):
    pass


def choose_move(
    game: Checkers,
    depth: int,
    time_limit: float = 3.0,
    rng: random.Random | None = None,
    randomness: float = 0.0,
) -> Move | None:
    """Pick a move with iterative-deepening negamax alpha-beta.

    ``randomness`` (0..1) is the chance of playing a random legal move instead
    (used for the easiest level).
    """
    rng = rng or random.Random()
    moves = game.legal_moves()
    if not moves:
        return None
    if len(moves) == 1:
        return moves[0]
    if rng.random() < randomness:
        return rng.choice(moves)
    deadline = time.perf_counter() + time_limit
    counter = [0]

    def search(node: Checkers, d: int, alpha: int, beta: int, ply: int) -> int:
        counter[0] += 1
        if counter[0] % 256 == 0 and time.perf_counter() > deadline:
            raise _TimeoutError
        legal = node.legal_moves()
        if not legal:
            return -WIN + ply
        if node.quiet_plies >= DRAW_PLIES:
            return 0
        if d <= 0 and not legal[0].captures:  # keep searching while captures are forced
            return evaluate(node)
        if d <= -6:
            return evaluate(node)
        legal.sort(key=lambda m: -len(m.captures))
        for move in legal:
            child = node.copy()
            child._apply(move)
            score = -search(child, d - 1, -beta, -alpha, ply + 1)
            if score >= beta:
                return beta
            alpha = max(alpha, score)
        return alpha

    best = moves[0]
    rng.shuffle(moves)  # vary play between equally good moves
    for d in range(1, depth + 1):
        try:
            alpha, depth_best = -WIN - 1, moves[0]
            for move in moves:
                child = game.copy()
                child._apply(move)
                score = -search(child, d - 1, -WIN - 1, -alpha, 1)
                if score > alpha:
                    alpha, depth_best = score, move
            best = depth_best
            moves.sort(key=lambda m: m != best)
            if alpha >= WIN - 100:
                break
        except _TimeoutError:
            break
    return best
