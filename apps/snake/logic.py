"""Snake rules: movement, turning, growth, collisions and speed. No pygame."""

from __future__ import annotations

import random
from collections import deque
from dataclasses import dataclass, field

Point = tuple[int, int]
Direction = tuple[int, int]

UP: Direction = (0, -1)
DOWN: Direction = (0, 1)
LEFT: Direction = (-1, 0)
RIGHT: Direction = (1, 0)

START_SPEED = 7.0  # steps per second
SPEED_PER_FOOD = 0.35
MAX_SPEED = 20.0
START_LENGTH = 3
MAX_QUEUED_TURNS = 2


@dataclass
class SnakeGame:
    """A grid-based snake game.

    Call :meth:`update` every frame with the elapsed time; the snake advances
    one cell every ``1 / speed`` seconds. Turns are queued so that two quick
    key presses (e.g. up then left) both register between steps.
    """

    cols: int = 30
    rows: int = 20
    wrap: bool = False
    rng: random.Random = field(default_factory=random.Random)
    body: deque[Point] = field(init=False)
    prev_body: list[Point] = field(init=False)
    direction: Direction = field(init=False, default=RIGHT)
    food: Point | None = field(init=False, default=None)
    score: int = field(init=False, default=0)
    speed: float = field(init=False, default=START_SPEED)
    alive: bool = field(init=False, default=True)
    won: bool = field(init=False, default=False)
    progress: float = field(init=False, default=0.0)  # 0..1 towards the next step
    _turns: deque[Direction] = field(init=False)

    def __post_init__(self) -> None:
        cx, cy = self.cols // 2, self.rows // 2
        self.body = deque((cx - i, cy) for i in range(START_LENGTH))
        self.prev_body = list(self.body)
        self._turns = deque()
        self.food = self._spawn_food()

    # ------------------------------------------------------------------ input
    @property
    def head(self) -> Point:
        return self.body[0]

    def turn(self, direction: Direction) -> None:
        """Queue a direction change. Reversing into yourself is ignored."""
        last = self._turns[-1] if self._turns else self.direction
        if direction in (last, (-last[0], -last[1])) or len(self._turns) >= MAX_QUEUED_TURNS:
            return
        self._turns.append(direction)

    # ------------------------------------------------------------------ simulation
    def update(self, dt: float) -> None:
        """Advance time by ``dt`` seconds, stepping as many times as needed."""
        if not self.alive:
            return
        self.progress += dt * self.speed
        while self.progress >= 1.0 and self.alive:
            self.progress -= 1.0
            self.step()

    def step(self) -> None:
        """Move one cell."""
        if not self.alive:
            return
        if self._turns:
            self.direction = self._turns.popleft()
        self.prev_body = list(self.body)
        x, y = self.head
        nx, ny = x + self.direction[0], y + self.direction[1]
        if self.wrap:
            nx %= self.cols
            ny %= self.rows
        elif not (0 <= nx < self.cols and 0 <= ny < self.rows):
            self.alive = False
            return

        new_head = (nx, ny)
        eating = new_head == self.food
        # The tail moves out of the way this step unless we're growing.
        blocking = list(self.body) if eating else list(self.body)[:-1]
        if new_head in blocking:
            self.alive = False
            return

        self.body.appendleft(new_head)
        if eating:
            self.score += 1
            self.speed = min(MAX_SPEED, self.speed + SPEED_PER_FOOD)
            self.food = self._spawn_food()
            if self.food is None:  # the snake fills the whole board
                self.won = True
                self.alive = False
        else:
            self.body.pop()

    def _spawn_food(self) -> Point | None:
        occupied = set(self.body)
        free = [
            (x, y) for y in range(self.rows) for x in range(self.cols) if (x, y) not in occupied
        ]
        return self.rng.choice(free) if free else None
