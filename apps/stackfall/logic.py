"""Stackfall rules: falling pieces, rotation with kicks, hold, line clears. No pygame.

Coordinates: ``x`` grows to the right, ``y`` grows downward. The board has
``HIDDEN`` extra rows above the visible area where pieces spawn.
"""

from __future__ import annotations

import random
from collections import deque
from dataclasses import dataclass, field
from typing import Literal

WIDTH, HEIGHT = 10, 20
HIDDEN = 2
TOTAL_ROWS = HEIGHT + HIDDEN

Kind = Literal["I", "O", "T", "S", "Z", "J", "L"]
KINDS: tuple[Kind, ...] = ("I", "O", "T", "S", "Z", "J", "L")
Cell = tuple[int, int]

#: Each shape in its spawn orientation, inside a square box of the given size.
SHAPES: dict[Kind, tuple[int, tuple[Cell, ...]]] = {
    "I": (4, ((0, 1), (1, 1), (2, 1), (3, 1))),
    "O": (2, ((0, 0), (1, 0), (0, 1), (1, 1))),
    "T": (3, ((1, 0), (0, 1), (1, 1), (2, 1))),
    "S": (3, ((1, 0), (2, 0), (0, 1), (1, 1))),
    "Z": (3, ((0, 0), (1, 0), (1, 1), (2, 1))),
    "J": (3, ((0, 0), (0, 1), (1, 1), (2, 1))),
    "L": (3, ((2, 0), (0, 1), (1, 1), (2, 1))),
}
#: Offsets tried in order when a rotation collides ("kicks").
KICKS: tuple[Cell, ...] = ((0, 0), (-1, 0), (1, 0), (0, -1), (-2, 0), (2, 0), (-1, -1), (1, -1))
#: Points per lines cleared at once, multiplied by the level.
LINE_POINTS = {1: 100, 2: 250, 3: 450, 4: 700}
LINES_PER_LEVEL = 10
LOCK_DELAY = 0.5
MAX_LOCK_RESETS = 15
PREVIEW = 5


def rotated_cells(kind: Kind, rotation: int) -> tuple[Cell, ...]:
    """Cells of ``kind`` after ``rotation`` clockwise quarter turns, within its box."""
    size, cells = SHAPES[kind]
    for _ in range(rotation % 4):
        cells = tuple((size - 1 - y, x) for x, y in cells)
    return cells


def gravity_interval(level: int) -> float:
    """Seconds per row of automatic falling."""
    return max(0.04, 0.8 * 0.83 ** (level - 1))


@dataclass
class Piece:
    kind: Kind
    x: int
    y: int
    rotation: int = 0

    def cells(self) -> list[Cell]:
        return [(self.x + cx, self.y + cy) for cx, cy in rotated_cells(self.kind, self.rotation)]


class Bag:
    """Shuffled bags of all seven kinds, so droughts are impossible."""

    def __init__(self, rng: random.Random) -> None:
        self.rng = rng
        self.queue: deque[Kind] = deque()

    def peek(self, n: int) -> list[Kind]:
        while len(self.queue) < n:
            bag = list(KINDS)
            self.rng.shuffle(bag)
            self.queue.extend(bag)
        return list(self.queue)[:n]

    def next(self) -> Kind:
        self.peek(1)
        return self.queue.popleft()


@dataclass
class StepResult:
    locked: bool = False
    cleared: list[int] = field(default_factory=list)  # visible row indices that were cleared
    game_over: bool = False


@dataclass
class Stackfall:
    """Complete game state. Call the action methods on input and :meth:`update` every frame."""

    rng: random.Random = field(default_factory=random.Random)
    grid: list[list[Kind | None]] = field(
        default_factory=lambda: [[None] * WIDTH for _ in range(TOTAL_ROWS)]
    )
    score: int = 0
    lines: int = 0
    over: bool = False
    hold_kind: Kind | None = None
    can_hold: bool = True
    soft_dropping: bool = False
    piece: Piece = field(init=False)
    bag: Bag = field(init=False)
    _fall: float = field(init=False, default=0.0)
    _lock: float = field(init=False, default=0.0)
    _lock_resets: int = field(init=False, default=0)

    def __post_init__(self) -> None:
        self.bag = Bag(self.rng)
        self.piece = self._spawn(self.bag.next())

    # ------------------------------------------------------------------ queries
    @property
    def level(self) -> int:
        return 1 + self.lines // LINES_PER_LEVEL

    def upcoming(self) -> list[Kind]:
        return self.bag.peek(PREVIEW)

    def fits(self, piece: Piece) -> bool:
        for x, y in piece.cells():
            if not (0 <= x < WIDTH and 0 <= y < TOTAL_ROWS) or self.grid[y][x] is not None:
                return False
        return True

    def ghost(self) -> Piece:
        """Where the current piece would land if hard-dropped."""
        g = Piece(self.piece.kind, self.piece.x, self.piece.y, self.piece.rotation)
        while self.fits(Piece(g.kind, g.x, g.y + 1, g.rotation)):
            g.y += 1
        return g

    def resting(self) -> bool:
        p = self.piece
        return not self.fits(Piece(p.kind, p.x, p.y + 1, p.rotation))

    # ------------------------------------------------------------------ actions
    def move(self, dx: int) -> bool:
        return self._try(
            Piece(self.piece.kind, self.piece.x + dx, self.piece.y, self.piece.rotation)
        )

    def rotate(self, direction: int = 1) -> bool:
        """Rotate clockwise (1) or counter-clockwise (-1), trying wall/floor kicks."""
        p = self.piece
        rotation = (p.rotation + direction) % 4
        return any(self._try(Piece(p.kind, p.x + dx, p.y + dy, rotation)) for dx, dy in KICKS)

    def soft_drop(self) -> bool:
        """Move down one row (1 point). Returns ``False`` if the piece is resting."""
        if self.over or not self._try(
            Piece(self.piece.kind, self.piece.x, self.piece.y + 1, self.piece.rotation),
            reset_lock=False,
        ):
            return False
        self.score += 1
        self._fall = 0.0
        return True

    def hard_drop(self) -> StepResult:
        """Drop to the bottom and lock immediately (2 points per row)."""
        if self.over:
            return StepResult(game_over=True)
        target = self.ghost()
        self.score += 2 * (target.y - self.piece.y)
        self.piece = target
        return self._lock_piece()

    def hold(self) -> bool:
        """Swap the current piece with the held one (once per piece)."""
        if self.over or not self.can_hold:
            return False
        current = self.piece.kind
        incoming = self.hold_kind or self.bag.next()
        self.hold_kind = current
        self.piece = self._spawn(incoming)
        self.can_hold = False
        if not self.fits(self.piece):
            self.over = True
        return True

    def update(self, dt: float) -> StepResult:
        """Apply gravity and lock delay."""
        if self.over:
            return StepResult(game_over=True)
        if self.resting():
            self._lock += dt
            if self._lock >= LOCK_DELAY:
                return self._lock_piece()
            return StepResult()
        self._fall += dt
        interval = gravity_interval(self.level)
        if self.soft_dropping:
            interval = min(interval, 0.035)
        while self._fall >= interval and not self.resting():
            self._fall -= interval
            self.piece.y += 1
            if self.soft_dropping:
                self.score += 1
        return StepResult()

    # ------------------------------------------------------------------ internals
    def _spawn(self, kind: Kind) -> Piece:
        size = SHAPES[kind][0]
        piece = Piece(kind, (WIDTH - size) // 2, HIDDEN - 1 if kind != "I" else HIDDEN - 2)
        self._fall = 0.0
        self._lock = 0.0
        self._lock_resets = 0
        return piece

    def _try(self, candidate: Piece, reset_lock: bool = True) -> bool:
        if self.over or not self.fits(candidate):
            return False
        self.piece = candidate
        if reset_lock and self._lock > 0 and self._lock_resets < MAX_LOCK_RESETS:
            self._lock = 0.0
            self._lock_resets += 1
        return True

    def _lock_piece(self) -> StepResult:
        for x, y in self.piece.cells():
            self.grid[y][x] = self.piece.kind
        full = [y for y in range(TOTAL_ROWS) if all(self.grid[y])]
        for y in full:
            del self.grid[y]
            self.grid.insert(0, [None] * WIDTH)
        if full:
            self.score += LINE_POINTS[len(full)] * self.level
            self.lines += len(full)
        result = StepResult(locked=True, cleared=[y - HIDDEN for y in full])
        # Locking entirely above the visible area also ends the game.
        if all(y < HIDDEN for _, y in self.piece.cells()):
            self.over = True
        self.piece = self._spawn(self.bag.next())
        self.can_hold = True
        if not self.fits(self.piece):
            self.over = True
        result.game_over = self.over
        return result
