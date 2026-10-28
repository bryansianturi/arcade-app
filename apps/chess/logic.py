"""Chess rules and a small engine. Pure Python, no pygame.

Squares are 0..63 with ``square = rank * 8 + file`` (a1 = 0, h1 = 7, a8 = 56).
Pieces are single letters, uppercase for White and lowercase for Black
(``P N B R Q K``); empty squares are ``"."``.

:class:`Position` implements the full rules: castling, en passant, promotion,
check, checkmate, stalemate and the draw rules (fifty-move, threefold
repetition, insufficient material). Moves are applied with :meth:`Position.push`
and taken back with :meth:`Position.pop`, which the engine also uses.

The engine (:func:`best_move`) is a negamax alpha-beta search with
material + piece-square evaluation, capture ordering, a quiescence search and
iterative deepening with a time limit.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

Color = Literal["w", "b"]
START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
FILES = "abcdefgh"
PROMOTIONS = "qrbn"

KNIGHT_STEPS = ((1, 2), (2, 1), (2, -1), (1, -2), (-1, -2), (-2, -1), (-2, 1), (-1, 2))
KING_STEPS = ((1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1))
ROOK_DIRS = ((1, 0), (-1, 0), (0, 1), (0, -1))
BISHOP_DIRS = ((1, 1), (1, -1), (-1, 1), (-1, -1))


def square(name: str) -> int:
    """``"e4"`` → 28."""
    return (int(name[1]) - 1) * 8 + FILES.index(name[0])


def square_name(sq: int) -> str:
    return f"{FILES[sq % 8]}{sq // 8 + 1}"


def color_of(piece: str) -> Color:
    return "w" if piece.isupper() else "b"


def other(color: Color) -> Color:
    return "b" if color == "w" else "w"


def _steps(steps: tuple[tuple[int, int], ...]) -> list[tuple[int, ...]]:
    table = []
    for sq in range(64):
        f, r = sq % 8, sq // 8
        table.append(
            tuple((r + dr) * 8 + f + df for df, dr in steps if 0 <= f + df < 8 and 0 <= r + dr < 8)
        )
    return table


def _rays(dirs: tuple[tuple[int, int], ...]) -> list[tuple[tuple[int, ...], ...]]:
    table = []
    for sq in range(64):
        f, r = sq % 8, sq // 8
        rays = []
        for df, dr in dirs:
            ray, nf, nr = [], f + df, r + dr
            while 0 <= nf < 8 and 0 <= nr < 8:
                ray.append(nr * 8 + nf)
                nf, nr = nf + df, nr + dr
            rays.append(tuple(ray))
        table.append(tuple(rays))
    return table


KNIGHT_MOVES = _steps(KNIGHT_STEPS)
KING_MOVES = _steps(KING_STEPS)
ROOK_RAYS = _rays(ROOK_DIRS)
BISHOP_RAYS = _rays(BISHOP_DIRS)


@dataclass(frozen=True)
class Move:
    start: int
    end: int
    promotion: str = ""  # lowercase piece letter, or ""

    @property
    def uci(self) -> str:
        return square_name(self.start) + square_name(self.end) + self.promotion

    @classmethod
    def from_uci(cls, text: str) -> Move:
        return cls(square(text[:2]), square(text[2:4]), text[4:5])


@dataclass
class _Undo:
    move: Move
    piece: str
    captured: str
    captured_sq: int
    castling: str
    ep: int | None
    halfmove: int


@dataclass
class Position:
    board: list[str] = field(default_factory=lambda: ["."] * 64)
    turn: Color = "w"
    castling: str = "KQkq"
    ep: int | None = None  # en passant target square
    halfmove: int = 0
    fullmove: int = 1
    _stack: list[_Undo] = field(default_factory=list)
    _keys: list[str] = field(default_factory=list)  # position keys, for repetition

    # ------------------------------------------------------------------ FEN
    @classmethod
    def from_fen(cls, fen: str = START_FEN) -> Position:
        parts = fen.split()
        rows = parts[0].split("/")
        board = ["."] * 64
        for i, row in enumerate(rows):
            rank, f = 7 - i, 0
            for ch in row:
                if ch.isdigit():
                    f += int(ch)
                else:
                    board[rank * 8 + f] = ch
                    f += 1
        pos = cls(
            board=board,
            turn="w" if parts[1] == "w" else "b",
            castling="" if parts[2] == "-" else parts[2],
            ep=None if parts[3] == "-" else square(parts[3]),
            halfmove=int(parts[4]) if len(parts) > 4 else 0,
            fullmove=int(parts[5]) if len(parts) > 5 else 1,
        )
        pos._keys.append(pos.key())
        return pos

    def fen(self) -> str:
        rows = []
        for rank in range(7, -1, -1):
            row, empty = "", 0
            for f in range(8):
                piece = self.board[rank * 8 + f]
                if piece == ".":
                    empty += 1
                else:
                    row += (str(empty) if empty else "") + piece
                    empty = 0
            rows.append(row + (str(empty) if empty else ""))
        ep = square_name(self.ep) if self.ep is not None else "-"
        placement = "/".join(rows)
        return (
            f"{placement} {self.turn} {self.castling or '-'} {ep} {self.halfmove} {self.fullmove}"
        )

    def key(self) -> str:
        """Identity for repetition: placement, side, castling and en passant."""
        return "".join(self.board) + self.turn + self.castling + str(self.ep)

    def copy(self) -> Position:
        return Position.from_fen(self.fen())

    # ------------------------------------------------------------------ attacks
    def king_square(self, color: Color) -> int:
        return self.board.index("K" if color == "w" else "k")

    def attacked(self, sq: int, by: Color) -> bool:
        b = self.board
        white = by == "w"
        pawn, knight, king = ("P", "N", "K") if white else ("p", "n", "k")
        bishop_queen = ("B", "Q") if white else ("b", "q")
        rook_queen = ("R", "Q") if white else ("r", "q")
        f, r = sq % 8, sq // 8
        pr = r - 1 if white else r + 1  # a pawn attacking ``sq`` stands one rank behind it
        if 0 <= pr < 8:
            for pf in (f - 1, f + 1):
                if 0 <= pf < 8 and b[pr * 8 + pf] == pawn:
                    return True
        if any(b[t] == knight for t in KNIGHT_MOVES[sq]) or any(
            b[t] == king for t in KING_MOVES[sq]
        ):
            return True
        for rays, pieces in ((ROOK_RAYS[sq], rook_queen), (BISHOP_RAYS[sq], bishop_queen)):
            for ray in rays:
                for t in ray:
                    if b[t] != ".":
                        if b[t] in pieces:
                            return True
                        break
        return False

    def in_check(self, color: Color | None = None) -> bool:
        color = color or self.turn
        return self.attacked(self.king_square(color), other(color))

    # ------------------------------------------------------------------ move generation
    def pseudo_moves(self, captures_only: bool = False) -> list[Move]:
        b, us = self.board, self.turn
        them = other(us)
        moves: list[Move] = []
        add = moves.append
        for sq in range(64):
            piece = b[sq]
            if piece == "." or color_of(piece) != us:
                continue
            kind = piece.upper()
            if kind == "P":
                self._pawn_moves(sq, captures_only, add)
            elif kind in "NK":
                for t in (KNIGHT_MOVES if kind == "N" else KING_MOVES)[sq]:
                    target = b[t]
                    empty = target == "."
                    if (empty and not captures_only) or (not empty and color_of(target) == them):
                        add(Move(sq, t))
                if kind == "K" and not captures_only:
                    self._castling_moves(sq, add)
            else:
                rays = (
                    ROOK_RAYS[sq]
                    if kind == "R"
                    else BISHOP_RAYS[sq]
                    if kind == "B"
                    else ROOK_RAYS[sq] + BISHOP_RAYS[sq]
                )
                for ray in rays:
                    for t in ray:
                        target = b[t]
                        if target == ".":
                            if not captures_only:
                                add(Move(sq, t))
                            continue
                        if color_of(target) == them:
                            add(Move(sq, t))
                        break
        return moves

    def _pawn_moves(self, sq: int, captures_only: bool, add: Callable[[Move], None]) -> None:
        b = self.board
        white = self.turn == "w"
        step = 8 if white else -8
        f, r = sq % 8, sq // 8
        last = 7 if white else 0

        def push(t: int) -> None:
            if t // 8 == last:
                for promo in PROMOTIONS:
                    add(Move(sq, t, promo))
            else:
                add(Move(sq, t))

        one = sq + step
        if not captures_only and b[one] == ".":
            push(one)
            start = 1 if white else 6
            if r == start and b[one + step] == ".":
                add(Move(sq, one + step))
        for df in (-1, 1):
            if 0 <= f + df < 8:
                t = one + df
                target = b[t]
                if (target != "." and color_of(target) != self.turn) or t == self.ep:
                    push(t)

    def _castling_moves(self, sq: int, add: Callable[[Move], None]) -> None:
        b = self.board
        white = self.turn == "w"
        home = 4 if white else 60
        if sq != home or self.attacked(sq, other(self.turn)):
            return
        them = other(self.turn)
        king_side, queen_side = ("K", "Q") if white else ("k", "q")
        # The king may not pass through (or land on) an attacked square.
        if (
            king_side in self.castling
            and b[home + 1] == b[home + 2] == "."
            and not self.attacked(home + 1, them)
            and not self.attacked(home + 2, them)
        ):
            add(Move(home, home + 2))
        if (
            queen_side in self.castling
            and b[home - 1] == b[home - 2] == b[home - 3] == "."
            and not self.attacked(home - 1, them)
            and not self.attacked(home - 2, them)
        ):
            add(Move(home, home - 2))

    def legal_moves(self) -> list[Move]:
        legal = []
        us = self.turn
        for move in self.pseudo_moves():
            self.push(move)
            if not self.in_check(us):
                legal.append(move)
            self.pop()
        return legal

    def legal_from(self, sq: int) -> list[Move]:
        return [m for m in self.legal_moves() if m.start == sq]

    # ------------------------------------------------------------------ make / unmake
    def push(self, move: Move) -> None:
        b = self.board
        piece = b[move.start]
        captured_sq = move.end
        if piece in "Pp" and move.end == self.ep:
            captured_sq = move.end - 8 if piece == "P" else move.end + 8
        captured = b[captured_sq]
        self._stack.append(
            _Undo(move, piece, captured, captured_sq, self.castling, self.ep, self.halfmove)
        )
        b[captured_sq] = "."
        b[move.start] = "."
        placed = piece
        if move.promotion:
            placed = move.promotion.upper() if piece == "P" else move.promotion
        b[move.end] = placed
        if piece in "Kk" and abs(move.end - move.start) == 2:  # castling: move the rook too
            rook_from, rook_to = (
                (move.start + 3, move.start + 1)
                if move.end > move.start
                else (move.start - 4, move.start - 1)
            )
            b[rook_to], b[rook_from] = b[rook_from], "."
        self._update_castling(move, piece, captured)
        self.ep = None
        if piece in "Pp" and abs(move.end - move.start) == 16:
            self.ep = (move.start + move.end) // 2
        self.halfmove = 0 if piece in "Pp" or captured != "." else self.halfmove + 1
        if self.turn == "b":
            self.fullmove += 1
        self.turn = other(self.turn)
        self._keys.append(self.key())

    def _update_castling(self, move: Move, piece: str, captured: str) -> None:
        rights = self.castling
        if not rights:
            return
        if piece == "K":
            rights = rights.replace("K", "").replace("Q", "")
        elif piece == "k":
            rights = rights.replace("k", "").replace("q", "")
        for sq, right in ((0, "Q"), (7, "K"), (56, "q"), (63, "k")):
            if move.start == sq or move.end == sq:
                rights = rights.replace(right, "")
        self.castling = rights

    def pop(self) -> Move:
        u = self._stack.pop()
        self._keys.pop()
        b = self.board
        move = u.move
        self.turn = other(self.turn)
        if self.turn == "b":
            self.fullmove -= 1
        b[move.start] = u.piece
        b[move.end] = "."
        b[u.captured_sq] = u.captured
        if u.piece in "Kk" and abs(move.end - move.start) == 2:
            rook_from, rook_to = (
                (move.start + 3, move.start + 1)
                if move.end > move.start
                else (move.start - 4, move.start - 1)
            )
            b[rook_from], b[rook_to] = b[rook_to], "."
        self.castling, self.ep, self.halfmove = u.castling, u.ep, u.halfmove
        return move

    @property
    def history(self) -> list[Move]:
        return [u.move for u in self._stack]

    # ------------------------------------------------------------------ outcome
    def repetitions(self) -> int:
        return self._keys.count(self._keys[-1]) if self._keys else 1

    def insufficient_material(self) -> bool:
        pieces = [p for p in self.board if p not in ".Kk"]
        if not pieces:
            return True
        if len(pieces) == 1 and pieces[0] in "BbNn":
            return True
        if all(p in "Bb" for p in pieces):
            colors = {(sq % 8 + sq // 8) % 2 for sq, p in enumerate(self.board) if p in "Bb"}
            return len(colors) == 1  # bishops all on the same colour can't mate
        return False

    def outcome(self) -> tuple[str, Color | None] | None:
        """``None`` while the game goes on, else ``(reason, winner)``."""
        if not self.legal_moves():
            if self.in_check():
                return "checkmate", other(self.turn)
            return "stalemate", None
        if self.insufficient_material():
            return "insufficient material", None
        if self.halfmove >= 100:
            return "fifty-move rule", None
        if self.repetitions() >= 3:
            return "threefold repetition", None
        return None

    # ------------------------------------------------------------------ notation
    def san(self, move: Move) -> str:
        """Standard algebraic notation for a legal ``move`` in this position."""
        piece = self.board[move.start]
        kind = piece.upper()
        if kind == "K" and abs(move.end - move.start) == 2:
            text = "O-O" if move.end > move.start else "O-O-O"
        else:
            capture = self.board[move.end] != "." or (kind == "P" and move.end == self.ep)
            text = ""
            if kind == "P":
                if capture:
                    text = FILES[move.start % 8]
            else:
                text = kind
                rivals = [
                    m
                    for m in self.legal_moves()
                    if m.end == move.end and m.start != move.start and self.board[m.start] == piece
                ]
                if rivals:
                    if all(m.start % 8 != move.start % 8 for m in rivals):
                        text += FILES[move.start % 8]
                    elif all(m.start // 8 != move.start // 8 for m in rivals):
                        text += str(move.start // 8 + 1)
                    else:
                        text += square_name(move.start)
            if capture:
                text += "x"
            text += square_name(move.end)
            if move.promotion:
                text += "=" + move.promotion.upper()
        self.push(move)
        if self.in_check():
            text += "#" if not self.legal_moves() else "+"
        self.pop()
        return text


# ---------------------------------------------------------------------- engine
VALUES = {"P": 100, "N": 320, "B": 330, "R": 500, "Q": 900, "K": 0}
MATE = 100_000

# Piece-square tables from White's point of view, a8..h8 first (as printed).
_PST_TEXT = {
    "P": """ 0  0  0  0  0  0  0  0
            50 50 50 50 50 50 50 50
            10 10 20 30 30 20 10 10
             5  5 10 25 25 10  5  5
             0  0  0 20 20  0  0  0
             5 -5-10  0  0-10 -5  5
             5 10 10-20-20 10 10  5
             0  0  0  0  0  0  0  0""",
    "N": """-50-40-30-30-30-30-40-50
            -40-20  0  0  0  0-20-40
            -30  0 10 15 15 10  0-30
            -30  5 15 20 20 15  5-30
            -30  0 15 20 20 15  0-30
            -30  5 10 15 15 10  5-30
            -40-20  0  5  5  0-20-40
            -50-40-30-30-30-30-40-50""",
    "B": """-20-10-10-10-10-10-10-20
            -10  0  0  0  0  0  0-10
            -10  0  5 10 10  5  0-10
            -10  5  5 10 10  5  5-10
            -10  0 10 10 10 10  0-10
            -10 10 10 10 10 10 10-10
            -10  5  0  0  0  0  5-10
            -20-10-10-10-10-10-10-20""",
    "R": """ 0  0  0  0  0  0  0  0
             5 10 10 10 10 10 10  5
            -5  0  0  0  0  0  0 -5
            -5  0  0  0  0  0  0 -5
            -5  0  0  0  0  0  0 -5
            -5  0  0  0  0  0  0 -5
            -5  0  0  0  0  0  0 -5
             0  0  0  5  5  0  0  0""",
    "Q": """-20-10-10 -5 -5-10-10-20
            -10  0  0  0  0  0  0-10
            -10  0  5  5  5  5  0-10
             -5  0  5  5  5  5  0 -5
              0  0  5  5  5  5  0 -5
            -10  5  5  5  5  5  0-10
            -10  0  5  0  0  0  0-10
            -20-10-10 -5 -5-10-10-20""",
    "K": """-30-40-40-50-50-40-40-30
            -30-40-40-50-50-40-40-30
            -30-40-40-50-50-40-40-30
            -30-40-40-50-50-40-40-30
            -20-30-30-40-40-30-30-20
            -10-20-20-20-20-20-20-10
             20 20  0  0  0  0 20 20
             20 30 10  0  0 10 30 20""",
}


def _parse_pst(text: str) -> list[int]:
    """Parse an 8×8 table of 3-character numbers, printed a8..h8 first; return a1-first."""
    rows = []
    for line in text.splitlines():
        cells = line.strip().rjust(24)
        rows.append([int(cells[i : i + 3]) for i in range(0, 24, 3)])
    return [v for row in reversed(rows) for v in row]


PST = {kind: _parse_pst(text) for kind, text in _PST_TEXT.items()}


def evaluate(pos: Position) -> int:
    """Centipawns from the side to move's point of view."""
    score = 0
    for sq, piece in enumerate(pos.board):
        if piece == ".":
            continue
        kind = piece.upper()
        if piece.isupper():
            score += VALUES[kind] + PST[kind][sq]
        else:
            score -= VALUES[kind] + PST[kind][(7 - sq // 8) * 8 + sq % 8]
    return score if pos.turn == "w" else -score


def _order_key(pos: Position, move: Move) -> int:
    victim = pos.board[move.end]
    gain = (
        VALUES[victim.upper()] * 10 - VALUES[pos.board[move.start].upper()] if victim != "." else 0
    )
    return -(gain + (800 if move.promotion == "q" else 0))


class _TimeoutError(Exception):
    pass


@dataclass
class SearchStats:
    nodes: int = 0
    depth: int = 0


def best_move(
    pos: Position,
    max_depth: int = 3,
    time_limit: float = 3.0,
    stats: SearchStats | None = None,
) -> Move | None:
    """Pick a move with iterative-deepening alpha-beta search.

    Stops after ``max_depth`` plies or ``time_limit`` seconds, returning the best
    move of the last fully searched depth.
    """
    stats = stats or SearchStats()
    deadline = time.perf_counter() + time_limit
    work = pos.copy()  # never disturb the caller's position (the UI may read it)
    work._keys = list(pos._keys)
    moves = work.legal_moves()
    if not moves:
        return None
    moves.sort(key=lambda m: _order_key(work, m))
    best = moves[0]

    def search(depth: int, alpha: int, beta: int, ply: int) -> int:
        stats.nodes += 1
        if stats.nodes % 512 == 0 and time.perf_counter() > deadline:
            raise _TimeoutError
        if ply and (work.halfmove >= 100 or work.repetitions() >= 2):
            return 0
        if depth <= 0:
            return quiesce(alpha, beta, ply)
        us = work.turn
        legal = 0
        for move in sorted(work.pseudo_moves(), key=lambda m: _order_key(work, m)):
            work.push(move)
            if work.in_check(us):
                work.pop()
                continue
            legal += 1
            score = -search(depth - 1, -beta, -alpha, ply + 1)
            work.pop()
            if score >= beta:
                return beta
            alpha = max(alpha, score)
        if not legal:
            return -MATE + ply if work.in_check() else 0
        return alpha

    def quiesce(alpha: int, beta: int, ply: int) -> int:
        stats.nodes += 1
        stand = evaluate(work)
        if stand >= beta:
            return beta
        alpha = max(alpha, stand)
        us = work.turn
        for move in sorted(
            work.pseudo_moves(captures_only=True), key=lambda m: _order_key(work, m)
        ):
            work.push(move)
            if work.in_check(us):
                work.pop()
                continue
            score = -quiesce(-beta, -alpha, ply + 1)
            work.pop()
            if score >= beta:
                return beta
            alpha = max(alpha, score)
        return alpha

    for depth in range(1, max_depth + 1):
        try:
            alpha, depth_best = -MATE - 1, moves[0]
            for move in moves:
                work.push(move)
                score = -search(depth - 1, -MATE - 1, -alpha, 1)
                work.pop()
                if score > alpha:
                    alpha, depth_best = score, move
            best = depth_best
            stats.depth = depth
            moves.sort(key=lambda m: m != best)  # search the best move first next time
            if alpha >= MATE - 100:
                break  # found a forced mate
        except _TimeoutError:
            break  # ``work`` is a private copy, so it can be abandoned mid-search
    return best
