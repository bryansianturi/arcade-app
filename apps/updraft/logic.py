"""Updraft rules: bounce up a tower of platforms. Pure Python, no pygame.

World coordinates have ``y`` growing *upwards* from the starting platform, so
height is just ``y``. The player bounces automatically whenever they land on a
platform while falling; the only control is steering. The field wraps
horizontally.

Platforms are generated ahead of the camera. Every vertical gap stays below
the height of a normal jump (with a safety margin), so the tower is always
climbable. Gaps widen and special platforms get more common with height:

- ``moving`` slides left and right,
- ``crumble`` holds for one bounce and then falls away,
- ``spring`` launches much higher than a normal bounce.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Literal

FIELD_W = 480.0
FIELD_H = 640.0
GRAVITY = 1800.0
JUMP_V = 900.0
SPRING_V = 1500.0
MAX_JUMP = JUMP_V**2 / (2 * GRAVITY)  # 225 px
MAX_GAP = MAX_JUMP * 0.8
MIN_GAP = 56.0
PLAYER_W = 34.0
PLAYER_H = 34.0
STEER_SPEED = 420.0
STEER_ACCEL = 2400.0
PLATFORM_H = 14.0
STEP = 1 / 240  # physics substep, so fast falls never tunnel through a platform
#: The camera keeps the player at or below this fraction of the field height.
CAMERA_LINE = 0.45
PIXELS_PER_POINT = 10
CRUMBLE_FALL = 420.0  # how fast a broken platform drops away

Kind = Literal["normal", "moving", "crumble", "spring"]
State = Literal["ready", "playing", "over"]


@dataclass
class Platform:
    x: float  # left edge
    y: float  # top surface
    w: float
    kind: Kind = "normal"
    vx: float = 0.0
    broken: bool = False

    def under(self, px: float) -> bool:
        """Whether a player centred at ``px`` overlaps this platform horizontally."""
        half = PLAYER_W / 2 - 4  # a little forgiveness at the edges
        return self.x - half <= px <= self.x + self.w + half


@dataclass
class Updraft:
    rng: random.Random = field(default_factory=random.Random)
    x: float = FIELD_W / 2
    y: float = 0.0
    vx: float = 0.0
    vy: float = 0.0
    camera: float = -40.0  # world y at the bottom of the field
    best_height: float = 0.0
    state: State = "ready"
    platforms: list[Platform] = field(default_factory=list)
    springs_used: int = 0
    time: float = 0.0
    #: Seconds since the last bounce (for squash-and-stretch in the UI).
    since_bounce: float = 1.0
    _top: float = 0.0  # y of the highest generated platform

    def __post_init__(self) -> None:
        self.platforms = [Platform(FIELD_W / 2 - 50, 0.0, 100.0)]
        self._generate()

    @property
    def score(self) -> int:
        return int(self.best_height / PIXELS_PER_POINT)

    # ------------------------------------------------------------------ generation
    def _difficulty(self, height: float) -> float:
        """0 at the start, 1 from 12,000 px (1,200 points) up."""
        return min(1.0, height / 12000)

    def _generate(self) -> None:
        while self._top < self.camera + FIELD_H + 240:
            d = self._difficulty(self._top)
            gap = self.rng.uniform(MIN_GAP, MIN_GAP + (MAX_GAP - MIN_GAP) * (0.35 + 0.65 * d))
            self._top += min(gap, MAX_GAP)
            w = 92 - 30 * d
            roll = self.rng.random()
            kind: Kind = "normal"
            if roll < 0.06 + 0.04 * d:
                kind = "spring"
            elif roll < 0.16 + 0.22 * d:
                kind = "moving"
            elif roll < 0.22 + 0.2 * d and self.platforms[-1].kind != "crumble":
                kind = "crumble"
            vx = self.rng.choice((-1, 1)) * self.rng.uniform(60, 110 + 70 * d)
            self.platforms.append(
                Platform(
                    self.rng.uniform(0, FIELD_W - w),
                    self._top,
                    w,
                    kind,
                    vx if kind == "moving" else 0.0,
                )
            )
            # Extra platforms early on make the opening forgiving and busy.
            if self.rng.random() < 0.45 * (1 - d):
                self.platforms.append(
                    Platform(
                        self.rng.uniform(0, FIELD_W - w),
                        self._top - self.rng.uniform(10, gap * 0.6),
                        w,
                    )
                )

    # ------------------------------------------------------------------ simulation
    def start(self) -> None:
        if self.state == "ready":
            self.state = "playing"
            self.vy = JUMP_V
            self.since_bounce = 0.0

    def update(self, dt: float, steer: float) -> bool:
        """Advance by ``dt`` seconds with ``steer`` in -1..1. Returns ``True`` on a bounce."""
        if self.state != "playing":
            return False
        bounced = False
        remaining = min(dt, 0.1)
        while remaining > 1e-9 and self.state == "playing":
            step = min(STEP, remaining)
            remaining -= step
            bounced |= self._step(step, steer)
        return bounced

    def _step(self, dt: float, steer: float) -> bool:
        self.time += dt
        self.since_bounce += dt
        target = max(-1.0, min(1.0, steer)) * STEER_SPEED
        change = STEER_ACCEL * dt
        self.vx += max(-change, min(change, target - self.vx))
        self.x = (self.x + self.vx * dt) % FIELD_W
        for p in self.platforms:
            if p.broken:
                p.y -= CRUMBLE_FALL * dt
            elif p.kind == "moving":
                p.x += p.vx * dt
                if p.x < 0 or p.x + p.w > FIELD_W:
                    p.vx = -p.vx
                    p.x = max(0.0, min(FIELD_W - p.w, p.x))
        prev_y = self.y
        self.vy -= GRAVITY * dt
        self.y += self.vy * dt
        bounced = False
        if self.vy < 0:
            for p in self.platforms:
                if not p.broken and self.y <= p.y <= prev_y and p.under(self.x):
                    self.y = p.y
                    self.vy = SPRING_V if p.kind == "spring" else JUMP_V
                    if p.kind == "spring":
                        self.springs_used += 1
                    elif p.kind == "crumble":
                        p.broken = True
                    self.since_bounce = 0.0
                    bounced = True
                    break
        self.best_height = max(self.best_height, self.y)
        self.camera = max(self.camera, self.y - FIELD_H * CAMERA_LINE)
        self.platforms = [p for p in self.platforms if p.y > self.camera - 40]
        self._generate()
        if self.y < self.camera - PLAYER_H:
            self.state = "over"
        return bounced
