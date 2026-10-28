"""Brick Blitz rules: paddle, ball physics, bricks, lives and levels. No pygame.

Coordinates are in a ``FIELD_W`` × ``FIELD_H`` playfield, origin top-left.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Literal

FIELD_W, FIELD_H = 960, 620
PADDLE_W, PADDLE_H = 120, 14
PADDLE_Y = FIELD_H - 48
PADDLE_SPEED = 760.0
BALL_R = 8
BALL_START_SPEED = 430.0
BALL_MAX_SPEED = 820.0
SPEEDUP_PER_HIT = 6.0
MAX_BOUNCE_ANGLE = math.radians(62)
START_LIVES = 3
MAX_STEP = 1 / 240

COLS = 12
BRICK_GAP = 6
BRICK_H = 24
BRICK_TOP = 70
BRICK_W = (FIELD_W - 2 * 30 - (COLS - 1) * BRICK_GAP) / COLS

#: Level layouts: one string per row, one char per column.
#: ``.`` empty, ``1``-``3`` hit points, ``#`` unbreakable.
LEVELS: tuple[tuple[str, ...], ...] = (
    (
        "333333333333",
        "222222222222",
        "222222222222",
        "111111111111",
        "111111111111",
    ),
    (
        "..1..22..1..",
        ".1.12332.1.1",
        "1.12.33.21.1",
        ".1.12332.1.1",
        "..1..22..1..",
        "............",
        "##........##",
    ),
    (
        "3.3.3..3.3.3",
        ".2.2.22.2.2.",
        "1.1.1111.1.1",
        "..22#..#22..",
        "1.1.1111.1.1",
        ".2.2.22.2.2.",
    ),
    (
        "#3333333333#",
        "#2........2#",
        "#2.111111.2#",
        "#2.1.33.1.2#",
        "#2.111111.2#",
        "#2........2#",
        "#....22....#",
    ),
)

EventKind = Literal[
    "brick_hit", "brick_broken", "paddle", "wall", "life_lost", "level_clear", "game_over"
]


@dataclass(frozen=True)
class Event:
    kind: EventKind
    x: float = 0.0
    y: float = 0.0
    value: int = 0


@dataclass
class Brick:
    col: int
    row: int
    hp: int  # -1 = unbreakable
    max_hp: int

    @property
    def x(self) -> float:
        return 30 + self.col * (BRICK_W + BRICK_GAP)

    @property
    def y(self) -> float:
        return BRICK_TOP + self.row * (BRICK_H + BRICK_GAP)

    @property
    def breakable(self) -> bool:
        return self.hp != -1


def build_level(index: int) -> list[Brick]:
    layout = LEVELS[index % len(LEVELS)]
    bricks = []
    for r, line in enumerate(layout):
        for c, ch in enumerate(line):
            if ch == "#":
                bricks.append(Brick(c, r, -1, -1))
            elif ch.isdigit():
                bricks.append(Brick(c, r, int(ch), int(ch)))
    return bricks


@dataclass
class BrickBlitz:
    rng: random.Random = field(default_factory=random.Random)
    paddle_x: float = FIELD_W / 2  # centre
    ball_x: float = 0.0
    ball_y: float = 0.0
    vx: float = 0.0
    vy: float = 0.0
    speed: float = BALL_START_SPEED
    attached: bool = True  # ball sits on the paddle until launched
    lives: int = START_LIVES
    score: int = 0
    level: int = 0
    over: bool = False
    move: int = 0  # keyboard input: -1, 0, 1
    target_x: float | None = None  # mouse input: paddle follows this x
    bricks: list[Brick] = field(default_factory=list)
    _events: list[Event] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.bricks:
            self.bricks = build_level(self.level)
        self._attach()

    # ------------------------------------------------------------------ actions
    def launch(self) -> None:
        if not self.attached or self.over:
            return
        self.attached = False
        angle = self.rng.uniform(-0.35, 0.35)
        self.vx = math.sin(angle) * self.speed
        self.vy = -math.cos(angle) * self.speed

    def update(self, dt: float) -> list[Event]:
        steps = max(1, math.ceil(dt / MAX_STEP))
        for _ in range(steps):
            if self.over:
                break
            self._step(dt / steps)
        events, self._events = self._events, []
        return events

    # ------------------------------------------------------------------ internals
    def remaining(self) -> int:
        return sum(1 for b in self.bricks if b.breakable)

    def _attach(self) -> None:
        self.attached = True
        self.ball_x = self.paddle_x
        self.ball_y = PADDLE_Y - BALL_R - 1

    def _step(self, dt: float) -> None:
        half = PADDLE_W / 2
        if self.target_x is not None:
            delta = self.target_x - self.paddle_x
            self.paddle_x += max(-PADDLE_SPEED * 1.6 * dt, min(PADDLE_SPEED * 1.6 * dt, delta))
        else:
            self.paddle_x += self.move * PADDLE_SPEED * dt
        self.paddle_x = max(half, min(FIELD_W - half, self.paddle_x))
        if self.attached:
            self.ball_x = self.paddle_x
            return

        self.ball_x += self.vx * dt
        self.ball_y += self.vy * dt
        self._walls()
        self._paddle()
        self._bricks()
        if self.ball_y - BALL_R > FIELD_H:
            self._lose_life()

    def _walls(self) -> None:
        if self.ball_x - BALL_R < 0:
            self.ball_x, self.vx = BALL_R, abs(self.vx)
            self._events.append(Event("wall", self.ball_x, self.ball_y))
        elif self.ball_x + BALL_R > FIELD_W:
            self.ball_x, self.vx = FIELD_W - BALL_R, -abs(self.vx)
            self._events.append(Event("wall", self.ball_x, self.ball_y))
        if self.ball_y - BALL_R < 0:
            self.ball_y, self.vy = BALL_R, abs(self.vy)
            self._events.append(Event("wall", self.ball_x, self.ball_y))

    def _paddle(self) -> None:
        if self.vy <= 0:
            return
        left = self.paddle_x - PADDLE_W / 2
        if (
            PADDLE_Y - BALL_R <= self.ball_y <= PADDLE_Y + PADDLE_H
            and left - BALL_R <= self.ball_x <= left + PADDLE_W + BALL_R
        ):
            # Where it hits decides the angle: centre goes straight up, edges go wide.
            offset = (self.ball_x - self.paddle_x) / (PADDLE_W / 2 + BALL_R)
            angle = max(-1.0, min(1.0, offset)) * MAX_BOUNCE_ANGLE
            self.speed = min(BALL_MAX_SPEED, self.speed + SPEEDUP_PER_HIT)
            self.vx = math.sin(angle) * self.speed
            self.vy = -math.cos(angle) * self.speed
            self.ball_y = PADDLE_Y - BALL_R
            self._events.append(Event("paddle", self.ball_x, self.ball_y))

    def _bricks(self) -> None:
        for brick in self.bricks:
            # Closest point on the brick to the ball centre.
            cx = max(brick.x, min(self.ball_x, brick.x + BRICK_W))
            cy = max(brick.y, min(self.ball_y, brick.y + BRICK_H))
            dx, dy = self.ball_x - cx, self.ball_y - cy
            if dx * dx + dy * dy > BALL_R * BALL_R:
                continue
            # Bounce off the side we penetrated least.
            pen_x = (
                BALL_R - abs(dx)
                if dx
                else BALL_R + min(self.ball_x - brick.x, brick.x + BRICK_W - self.ball_x)
            )
            pen_y = (
                BALL_R - abs(dy)
                if dy
                else BALL_R + min(self.ball_y - brick.y, brick.y + BRICK_H - self.ball_y)
            )
            if pen_x < pen_y:
                self.vx = math.copysign(
                    abs(self.vx), dx if dx else self.ball_x - (brick.x + BRICK_W / 2)
                )
                self.ball_x += math.copysign(pen_x, self.vx)
            else:
                self.vy = math.copysign(
                    abs(self.vy), dy if dy else self.ball_y - (brick.y + BRICK_H / 2)
                )
                self.ball_y += math.copysign(pen_y, self.vy)
            self._hit(brick)
            return  # one brick per step keeps bounces predictable

    def _hit(self, brick: Brick) -> None:
        center = (brick.x + BRICK_W / 2, brick.y + BRICK_H / 2)
        if not brick.breakable:
            self._events.append(Event("brick_hit", *center, -1))
            return
        brick.hp -= 1
        if brick.hp > 0:
            self.score += 5
            self._events.append(Event("brick_hit", *center, brick.hp))
            return
        self.bricks.remove(brick)
        self.score += 10 * brick.max_hp * (1 + self.level // 2)
        self._events.append(Event("brick_broken", *center, brick.max_hp))
        if self.remaining() == 0:
            self._next_level()

    def _next_level(self) -> None:
        self.level += 1
        self.bricks = build_level(self.level)
        self.speed = min(BALL_MAX_SPEED, BALL_START_SPEED + 40 * self.level)
        self._attach()
        self._events.append(Event("level_clear", value=self.level))

    def _lose_life(self) -> None:
        self.lives -= 1
        self._events.append(Event("life_lost", self.ball_x, FIELD_H))
        if self.lives <= 0:
            self.over = True
            self._events.append(Event("game_over"))
            return
        self.speed = max(BALL_START_SPEED, self.speed * 0.85)
        self._attach()
