"""Rooftop Dash rules: run across the rooftops, jump the gaps, dodge crates and drones.

Pure Python, no pygame. World ``x`` grows to the right and ``y`` grows *upwards*
(0 is the street-level reference; rooftops sit at different heights above it).

Speed depends only on distance run, so the generator knows exactly how fast
the player will be going at every point and can keep each challenge fair:

- a gap is never wider than 70% of the distance a full jump covers at that speed,
  allowing for any step up or down to the next roof;
- a step up is never taller than a comfortable jump;
- obstacles are spaced at least ``REACTION`` seconds apart, leave room to land
  after a gap, and stay a full jump away from the far edge of their roof.

Controls: jump (hold for height; letting go early cuts the jump short), and
down to slide under drones on the ground or to drop faster in the air.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Literal

GRAVITY = 3000.0
#: Weaker gravity while the jump button is held and the runner is rising.
HOLD_GRAVITY = 1500.0
FAST_FALL = 5200.0
JUMP_V = 760.0
BASE_SPEED = 380.0
MAX_SPEED = 780.0
SPEED_GAIN = 0.008  # px/s of speed per px run
COYOTE = 0.08  # seconds after leaving a roof when a jump still works
BUFFER = 0.12  # a jump pressed this long before landing still happens
PLAYER_W = 30.0
PLAYER_H = 56.0
SLIDE_H = 28.0
#: Where the runner stands on screen, measured from the left of the view.
PLAYER_SCREEN_X = 220.0
VIEW_W = 1120.0
REACTION = 0.75  # minimum seconds between obstacles
DRONE_BOTTOM = 36.0  # drones hover this high above the roof: slide under or jump over
MAX_STEP_UP = 90.0
STEP = 1 / 240
PX_PER_POINT = 40
COIN_POINTS = 5
COIN_R = 11.0

ObstacleKind = Literal["crate", "double", "drone"]
State = Literal["ready", "running", "over"]


def speed_at(x: float) -> float:
    return min(MAX_SPEED, BASE_SPEED + max(0.0, x) * SPEED_GAIN)


def jump_reach(speed: float, drop: float) -> float:
    """Horizontal distance of a full (held) jump that lands ``drop`` px lower (negative: higher)."""
    rise_t = JUMP_V / HOLD_GRAVITY
    peak = JUMP_V**2 / (2 * HOLD_GRAVITY)
    fall = peak + drop
    if fall <= 0:
        return 0.0
    return speed * (rise_t + math.sqrt(2 * fall / GRAVITY))


@dataclass
class Roof:
    x0: float
    x1: float
    h: float


@dataclass
class Obstacle:
    x: float
    kind: ObstacleKind
    base: float  # roof height it stands on
    passed: bool = False

    @property
    def box(self) -> tuple[float, float, float, float]:
        """(left, bottom, width, height) in world units."""
        if self.kind == "drone":
            return self.x, self.base + DRONE_BOTTOM, 46.0, 24.0
        if self.kind == "double":
            return self.x, self.base, 34.0, 68.0
        return self.x, self.base, 34.0, 34.0


@dataclass
class Coin:
    x: float
    y: float
    taken: bool = False


@dataclass
class RooftopDash:
    rng: random.Random = field(default_factory=random.Random)
    x: float = 0.0  # runner's world x (centre)
    y: float = 0.0  # feet
    vy: float = 0.0
    state: State = "ready"
    grounded: bool = True
    sliding: bool = False
    coins: int = 0
    drones_ducked: int = 0
    time: float = 0.0
    roofs: list[Roof] = field(default_factory=list)
    obstacles: list[Obstacle] = field(default_factory=list)
    coin_list: list[Coin] = field(default_factory=list)
    _air_time: float = 0.0  # seconds since last on a roof
    _buffer: float = 0.0  # seconds left on a buffered jump
    _gen_x: float = 0.0
    #: Why the run ended: "fell" or the obstacle kind hit.
    cause: str = ""

    def __post_init__(self) -> None:
        start = Roof(-PLAYER_SCREEN_X - 200, 1500.0, 120.0)
        self.roofs = [start]
        self.y = start.h
        self._gen_x = start.x1
        self._generate()

    @property
    def speed(self) -> float:
        return speed_at(self.x)

    @property
    def camera(self) -> float:
        """World x at the left edge of the view."""
        return self.x - PLAYER_SCREEN_X

    @property
    def score(self) -> int:
        return int(max(0.0, self.x) / PX_PER_POINT) + COIN_POINTS * self.coins

    @property
    def height(self) -> float:
        return SLIDE_H if self.sliding else PLAYER_H

    # ------------------------------------------------------------------ generation
    def _generate(self) -> None:
        while self._gen_x < self.camera + VIEW_W + 600:
            last = self.roofs[-1]
            speed = speed_at(last.x1)
            difficulty = (speed - BASE_SPEED) / (MAX_SPEED - BASE_SPEED)
            h = max(40.0, min(260.0, last.h + self.rng.choice((-80, -40, 0, 0, 40, 80))))
            h = min(h, last.h + MAX_STEP_UP)
            reach = jump_reach(speed, last.h - h)
            gap = 0.0
            if self.rng.random() < 0.55 + 0.3 * difficulty:
                gap = self.rng.uniform(70, max(80.0, reach * (0.4 + 0.3 * difficulty)))
                gap = min(gap, reach * 0.7)
            x0 = last.x1 + gap
            length = self.rng.uniform(600, 1400) * (1 + 0.4 * difficulty)
            roof = Roof(x0, x0 + length, h)
            self.roofs.append(roof)
            if gap:
                self._coin_arc(last, roof, speed)
            self._place_obstacles(roof, speed, difficulty)
            self._gen_x = roof.x1

    def _place_obstacles(self, roof: Roof, speed: float, difficulty: float) -> None:
        # Room to land before the first obstacle, and a full jump plus a run-up between
        # the last one and the edge, so clearing an obstacle never drops you in a gap.
        x = roof.x0 + speed * 0.45
        end = roof.x1 - jump_reach(speed, 0) - speed * 0.3
        while True:
            x += speed * self.rng.uniform(REACTION, REACTION + 1.2 - 0.6 * difficulty)
            if x > end:
                break
            roll = self.rng.random()
            kind: ObstacleKind = (
                "drone"
                if roll < 0.2 + 0.25 * difficulty
                else "double"
                if roll < 0.35 + 0.2 * difficulty
                else "crate"
            )
            self.obstacles.append(Obstacle(x, kind, roof.h))
            if self.rng.random() < 0.35:  # a few coins after it, as a reward
                for i in range(3):
                    self.coin_list.append(Coin(x + 90 + i * 34, roof.h + 26))

    def _coin_arc(self, a: Roof, b: Roof, speed: float) -> None:
        """Coins along the path of a jump that takes off near the edge of ``a``."""
        takeoff = a.x1 - 30
        for i in range(1, 6):
            t = i * 0.08
            x = takeoff + speed * t
            y = a.h + JUMP_V * t - HOLD_GRAVITY * t * t / 2 + 20
            if x < b.x0 + 60:
                self.coin_list.append(Coin(x, y))

    # ------------------------------------------------------------------ queries
    def roof_at(self, x: float) -> Roof | None:
        for roof in self.roofs:
            if roof.x0 <= x <= roof.x1:
                return roof
        return None

    def _support(self) -> Roof | None:
        """The roof under the runner's feet (any part of their width)."""
        half = PLAYER_W / 2
        best: Roof | None = None
        for roof in self.roofs:
            if roof.x0 - half <= self.x <= roof.x1 + half and (best is None or roof.h > best.h):
                best = roof
        return best

    # ------------------------------------------------------------------ simulation
    def jump(self) -> None:
        """Press jump: starts the run, or jumps now / as soon as the runner lands."""
        if self.state == "ready":
            self.state = "running"
        if self.state == "running":
            self._buffer = BUFFER

    def update(self, dt: float, holding_jump: bool, down: bool) -> bool:
        """Advance ``dt`` seconds. Returns ``True`` if a coin was collected."""
        if self.state != "running":
            return False
        got_coin = False
        remaining = min(dt, 0.1)
        while remaining > 1e-9 and self.state == "running":
            step = min(STEP, remaining)
            remaining -= step
            got_coin |= self._step(step, holding_jump, down)
        return got_coin

    def _step(self, dt: float, holding: bool, down: bool) -> bool:
        self.time += dt
        self._buffer = max(0.0, self._buffer - dt)
        self._air_time = 0.0 if self.grounded else self._air_time + dt
        if self._buffer > 0 and (self.grounded or self._air_time < COYOTE) and self.vy <= 0:
            self.vy = JUMP_V
            self.grounded = False
            self._buffer = 0.0
            self._air_time = COYOTE  # no second coyote jump
        self.sliding = self.grounded and down

        prev_x = self.x
        self.x += self.speed * dt
        # Running into the side of a taller roof ends the run.
        for roof in self.roofs:
            front = self.x + PLAYER_W / 2
            if prev_x + PLAYER_W / 2 <= roof.x0 < front and roof.h > self.y + 6:
                self.state, self.cause = "over", "wall"
                return False

        if self.grounded:
            support = self._support()
            if support is None or support.h < self.y - 1:
                self.grounded = False
            else:
                self.y = support.h
        if not self.grounded:
            g = FAST_FALL if down else GRAVITY
            if holding and self.vy > 0 and not down:
                g = HOLD_GRAVITY
            prev_y = self.y
            self.vy -= g * dt
            self.y += self.vy * dt
            if self.vy <= 0:
                support = self._support()
                if support is not None and self.y <= support.h <= prev_y + 1:
                    self.y, self.vy, self.grounded = support.h, 0.0, True
            if self.y < -150:
                self.state, self.cause = "over", "fell"
                return False

        return self._collide()

    def _collide(self) -> bool:
        left, right = self.x - PLAYER_W / 2, self.x + PLAYER_W / 2
        bottom, top = self.y, self.y + self.height
        for ob in self.obstacles:
            ox, oy, ow, oh = ob.box
            if ox < right and left < ox + ow and oy < top - 2 and bottom + 2 < oy + oh:
                self.state, self.cause = "over", ob.kind
                return False
            if not ob.passed and ox + ow < left:
                ob.passed = True
                if ob.kind == "drone" and self.grounded and self.sliding:
                    self.drones_ducked += 1
        got = False
        cy = self.y + self.height / 2
        for coin in self.coin_list:
            near_x = abs(coin.x - self.x) < COIN_R + PLAYER_W / 2
            if not coin.taken and near_x and abs(coin.y - cy) < COIN_R + self.height / 2:
                coin.taken = True
                self.coins += 1
                got = True
        # Forget what has scrolled off the left of the view.
        edge = self.camera - 100
        self.roofs = [r for r in self.roofs if r.x1 > edge] or self.roofs[-1:]
        self.obstacles = [o for o in self.obstacles if o.x + 60 > edge]
        self.coin_list = [c for c in self.coin_list if c.x > edge]
        self._generate()
        return got
