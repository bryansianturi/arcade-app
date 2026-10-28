"""Paddle Duel rules: two paddles, one ball, first to ``WIN_SCORE``. No pygame.

The right paddle can be driven by :class:`CpuController`, which predicts
where the ball will cross its side (including wall bounces) and moves there
with a difficulty-dependent reaction delay, speed limit and aim error.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Literal

FIELD_W, FIELD_H = 1000, 600
PADDLE_W, PADDLE_H = 14, 96
PADDLE_MARGIN = 36  # distance from the field edge to the paddle's outer face
PADDLE_SPEED = 600.0
BALL_R = 9
SERVE_SPEED = 460.0
SPEEDUP = 30.0
MAX_SPEED = 1000.0
MAX_ANGLE = math.radians(55)
SPIN = 0.25  # how much paddle movement bends the ball
SERVE_DELAY = 0.8
WIN_SCORE = 7
MAX_STEP = 1 / 240

Side = Literal["left", "right"]
Level = Literal["easy", "medium", "hard"]
EventKind = Literal["hit", "wall", "point", "match"]


@dataclass(frozen=True)
class Event:
    kind: EventKind
    side: Side | None = None
    x: float = 0.0
    y: float = 0.0


@dataclass
class Paddle:
    side: Side
    y: float = FIELD_H / 2  # centre
    move: float = 0.0  # -1..1, set by input or the CPU
    velocity: float = 0.0  # actual movement last step (px/s), used for spin

    @property
    def face_x(self) -> float:
        """x of the face the ball bounces off."""
        return (
            PADDLE_MARGIN + PADDLE_W if self.side == "left" else FIELD_W - PADDLE_MARGIN - PADDLE_W
        )


@dataclass
class PaddleDuel:
    rng: random.Random = field(default_factory=random.Random)
    left: Paddle = field(default_factory=lambda: Paddle("left"))
    right: Paddle = field(default_factory=lambda: Paddle("right"))
    ball_x: float = FIELD_W / 2
    ball_y: float = FIELD_H / 2
    vx: float = 0.0
    vy: float = 0.0
    speed: float = SERVE_SPEED
    scores: dict[Side, int] = field(default_factory=lambda: {"left": 0, "right": 0})
    serve_timer: float = SERVE_DELAY
    serve_to: Side = "left"
    rally: int = 0
    best_rally: int = 0
    winner: Side | None = None
    _events: list[Event] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.serve_to = self.rng.choice(("left", "right"))

    @property
    def serving(self) -> bool:
        return self.serve_timer > 0

    def update(self, dt: float) -> list[Event]:
        steps = max(1, math.ceil(dt / MAX_STEP))
        for _ in range(steps):
            if self.winner is not None:
                break
            self._step(dt / steps)
        events, self._events = self._events, []
        return events

    def _step(self, dt: float) -> None:
        for paddle in (self.left, self.right):
            before = paddle.y
            paddle.y += max(-1.0, min(1.0, paddle.move)) * PADDLE_SPEED * dt
            paddle.y = max(PADDLE_H / 2, min(FIELD_H - PADDLE_H / 2, paddle.y))
            paddle.velocity = (paddle.y - before) / dt if dt else 0.0

        if self.serving:
            self.serve_timer -= dt
            if self.serve_timer <= 0:
                self._serve()
            return

        self.ball_x += self.vx * dt
        self.ball_y += self.vy * dt
        if self.ball_y - BALL_R < 0 or self.ball_y + BALL_R > FIELD_H:
            self.ball_y = max(BALL_R, min(FIELD_H - BALL_R, self.ball_y))
            self.vy = -self.vy
            self._events.append(Event("wall", None, self.ball_x, self.ball_y))

        paddle = self.left if self.vx < 0 else self.right
        self._collide(paddle)

        if self.ball_x < -BALL_R * 2:
            self._point("right")
        elif self.ball_x > FIELD_W + BALL_R * 2:
            self._point("left")

    def _collide(self, paddle: Paddle) -> None:
        face = paddle.face_x
        crossing = (
            self.ball_x - BALL_R <= face <= self.ball_x + BALL_R + abs(self.vx) * MAX_STEP
            if paddle.side == "left"
            else self.ball_x - BALL_R - abs(self.vx) * MAX_STEP <= face <= self.ball_x + BALL_R
        )
        if not crossing or abs(self.ball_y - paddle.y) > PADDLE_H / 2 + BALL_R:
            return
        offset = (self.ball_y - paddle.y) / (PADDLE_H / 2 + BALL_R)
        angle = max(-1.0, min(1.0, offset)) * MAX_ANGLE
        self.speed = min(MAX_SPEED, self.speed + SPEEDUP)
        direction = 1 if paddle.side == "left" else -1
        self.vx = direction * math.cos(angle) * self.speed
        self.vy = math.sin(angle) * self.speed + paddle.velocity * SPIN
        self.ball_x = face + direction * BALL_R
        self.rally += 1
        self.best_rally = max(self.best_rally, self.rally)
        self._events.append(Event("hit", paddle.side, self.ball_x, self.ball_y))

    def _serve(self) -> None:
        self.ball_x, self.ball_y = FIELD_W / 2, FIELD_H / 2
        self.speed = SERVE_SPEED
        angle = self.rng.uniform(-0.45, 0.45)
        direction = -1 if self.serve_to == "left" else 1
        self.vx = direction * math.cos(angle) * self.speed
        self.vy = math.sin(angle) * self.speed

    def _point(self, scorer: Side) -> None:
        self.scores[scorer] += 1
        self.rally = 0
        self._events.append(Event("point", scorer, self.ball_x, self.ball_y))
        self.ball_x, self.ball_y, self.vx, self.vy = FIELD_W / 2, FIELD_H / 2, 0.0, 0.0
        if self.scores[scorer] >= WIN_SCORE:
            self.winner = scorer
            self._events.append(Event("match", scorer))
            return
        self.serve_to = "left" if scorer == "right" else "right"  # serve to whoever lost the point
        self.serve_timer = SERVE_DELAY


# ---------------------------------------------------------------------------- CPU
#: (speed factor, reaction seconds, aim error in px) per difficulty.
#: The aim error grows with ball speed, so even "hard" misses during long, fast rallies.
CPU_TUNING: dict[Level, tuple[float, float, float]] = {
    "easy": (0.5, 0.32, 70.0),
    "medium": (0.78, 0.18, 34.0),
    "hard": (0.92, 0.08, 14.0),
}


def predict_y(x: float, y: float, vx: float, vy: float, target_x: float) -> float:
    """Where a ball at (x, y) moving (vx, vy) will be when it reaches ``target_x``.

    Bounces off the top and bottom walls are unfolded by reflecting the path.
    """
    if vx == 0:
        return y
    t = (target_x - x) / vx
    if t < 0:
        return y
    span = FIELD_H - 2 * BALL_R
    raw = (y - BALL_R) + vy * t
    folded = raw % (2 * span)
    if folded > span:
        folded = 2 * span - folded
    return folded + BALL_R


@dataclass
class CpuController:
    """Steers one paddle like a (fallible) human would."""

    paddle: Paddle
    level: Level = "medium"
    rng: random.Random = field(default_factory=random.Random)
    _target: float = FIELD_H / 2
    _think: float = 0.0
    _error: float = 0.0
    _was_incoming: bool = False

    def update(self, game: PaddleDuel, dt: float) -> None:
        speed_factor, reaction, error = CPU_TUNING[self.level]
        incoming = (game.vx > 0) == (self.paddle.side == "right") and game.vx != 0
        if incoming and not self._was_incoming:
            # New shot coming: pick a fresh aim error and wait a moment before reacting.
            pressure = 1 + max(0.0, game.speed - SERVE_SPEED) / 150
            self._error = self.rng.uniform(-error, error) * pressure
            self._think = reaction
        self._was_incoming = incoming
        self._think -= dt
        if self._think <= 0:
            if incoming:
                face = self.paddle.face_x
                self._target = (
                    predict_y(game.ball_x, game.ball_y, game.vx, game.vy, face) + self._error
                )
            else:
                self._target = FIELD_H / 2  # drift back to the middle
        delta = self._target - self.paddle.y
        dead_zone = 6
        self.paddle.move = (
            0.0 if abs(delta) < dead_zone else max(-1.0, min(1.0, delta / 40)) * speed_factor
        )
