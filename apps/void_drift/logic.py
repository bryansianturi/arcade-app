"""Void Drift rules: a ship with inertia in a wrap-around field of splitting rocks.

Pure Python, no pygame. Positions are in a ``FIELD_W`` × ``FIELD_H`` torus
(everything wraps at the edges). Angles are in degrees, 0 pointing up and
increasing clockwise. :meth:`VoidDrift.update` returns :class:`Event` objects so
the UI can add particles without the rules knowing anything about drawing.

The ship is driven by four inputs: :attr:`VoidDrift.turn` (-1, 0, 1),
:attr:`VoidDrift.thrust`, :meth:`VoidDrift.fire` and :meth:`VoidDrift.warp`.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Literal

FIELD_W, FIELD_H = 1184, 600

SHIP_RADIUS = 14.0
TURN_SPEED = 250.0  # degrees per second
THRUST = 380.0  # px/s²
DRAG = 0.45  # fraction of speed lost per second (gentle: the ship drifts)
MAX_SPEED = 470.0
START_LIVES = 3
MAX_LIVES = 6
EXTRA_LIFE_EVERY = 10_000
RESPAWN_SECONDS = 1.4
INVULNERABLE_SECONDS = 2.2
SAFE_RADIUS = 150.0  # no rock this close to the centre when (re)spawning
WARP_COOLDOWN = 1.2

BULLET_SPEED = 640.0
BULLET_LIFE = 0.85
FIRE_COOLDOWN = 0.17
MAX_BULLETS = 5

#: Rock size → (radius, points). Large rocks split into two medium, medium into two small.
ROCK_SIZES: dict[int, tuple[float, int]] = {3: (46.0, 20), 2: (26.0, 50), 1: (14.0, 100)}
ROCK_SPEED = (40.0, 95.0)  # range, grows a little each wave
ROCK_VERTICES = 11

DRONE_RADIUS = 16.0
DRONE_SPEED = 120.0
DRONE_FIRE_EVERY = 1.3
DRONE_BULLET_SPEED = 300.0
DRONE_POINTS = {"large": 200, "small": 1000}
FIRST_DRONE_WAVE = 2

WAVE_DELAY = 2.0
MAX_STEP = 1 / 120  # physics sub-step so fast bullets can't skip over small rocks

EventKind = Literal[
    "shot",
    "rock_destroyed",
    "drone_destroyed",
    "ship_destroyed",
    "warp",
    "wave_cleared",
    "extra_life",
    "game_over",
]


@dataclass(frozen=True)
class Event:
    kind: EventKind
    x: float = 0.0
    y: float = 0.0
    size: int = 0  # rock size, or 0


def wrap(x: float, y: float) -> tuple[float, float]:
    return x % FIELD_W, y % FIELD_H


def wrapped_delta(a: float, b: float, size: float) -> float:
    """Shortest signed distance from ``a`` to ``b`` on a circle of length ``size``."""
    d = (b - a) % size
    return d - size if d > size / 2 else d


def distance(ax: float, ay: float, bx: float, by: float) -> float:
    """Distance on the torus (objects near opposite edges are close)."""
    return math.hypot(wrapped_delta(ax, bx, FIELD_W), wrapped_delta(ay, by, FIELD_H))


def heading(angle: float) -> tuple[float, float]:
    """Unit vector for ``angle`` (0 = up, clockwise)."""
    rad = math.radians(angle)
    return math.sin(rad), -math.cos(rad)


@dataclass
class Ship:
    x: float = FIELD_W / 2
    y: float = FIELD_H / 2
    vx: float = 0.0
    vy: float = 0.0
    angle: float = 0.0


@dataclass
class Bullet:
    x: float
    y: float
    vx: float
    vy: float
    life: float
    friendly: bool


@dataclass
class Rock:
    x: float
    y: float
    vx: float
    vy: float
    size: int
    spin: float  # degrees per second
    angle: float = 0.0
    shape: tuple[float, ...] = ()  # per-vertex radius multipliers, for drawing

    @property
    def radius(self) -> float:
        return ROCK_SIZES[self.size][0]


@dataclass
class Drone:
    """A patrol craft that crosses the field, weaving, and shoots at the ship."""

    x: float
    y: float
    vx: float
    kind: Literal["large", "small"]
    base_y: float
    time: float = 0.0
    fire_timer: float = DRONE_FIRE_EVERY
    travelled: float = 0.0

    @property
    def radius(self) -> float:
        return DRONE_RADIUS if self.kind == "large" else DRONE_RADIUS * 0.7


@dataclass
class VoidDrift:
    """Complete game state."""

    rng: random.Random = field(default_factory=random.Random)
    ship: Ship = field(default_factory=Ship)
    rocks: list[Rock] = field(default_factory=list)
    bullets: list[Bullet] = field(default_factory=list)
    drones: list[Drone] = field(default_factory=list)
    lives: int = START_LIVES
    score: int = 0
    wave: int = 0
    over: bool = False
    turn: int = 0  # -1 left, 1 right
    thrust: bool = False
    ship_alive: bool = True
    respawn_timer: float = 0.0
    invulnerable: float = INVULNERABLE_SECONDS
    cooldown: float = 0.0
    warp_cooldown: float = 0.0
    wave_timer: float = 0.0  # countdown to the next wave once the field is clear
    drone_timer: float = 0.0
    next_extra_life: int = EXTRA_LIFE_EVERY
    drones_destroyed: int = 0
    _events: list[Event] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.wave == 0:
            self.start_wave(1)

    # ------------------------------------------------------------------ setup
    def start_wave(self, wave: int) -> None:
        self.wave = wave
        count = min(3 + wave, 11)
        self.rocks = [self._new_rock(*self._spawn_point(), 3) for _ in range(count)]
        self.drone_timer = self._drone_delay()

    def _spawn_point(self) -> tuple[float, float]:
        """A random point away from the ship."""
        for _ in range(100):
            x, y = self.rng.uniform(0, FIELD_W), self.rng.uniform(0, FIELD_H)
            if distance(x, y, self.ship.x, self.ship.y) > SAFE_RADIUS * 1.6:
                return x, y
        return (self.ship.x + FIELD_W / 2) % FIELD_W, (self.ship.y + FIELD_H / 2) % FIELD_H

    def _new_rock(
        self, x: float, y: float, size: int, base: tuple[float, float] = (0.0, 0.0)
    ) -> Rock:
        low, high = ROCK_SPEED
        boost = 1 + min(0.6, (self.wave - 1) * 0.06) + (3 - size) * 0.25
        speed = self.rng.uniform(low, high) * boost
        angle = self.rng.uniform(0, 360)
        dx, dy = heading(angle)
        shape = tuple(self.rng.uniform(0.72, 1.08) for _ in range(ROCK_VERTICES))
        return Rock(
            x,
            y,
            base[0] * 0.4 + dx * speed,
            base[1] * 0.4 + dy * speed,
            size,
            self.rng.uniform(-60, 60),
            self.rng.uniform(0, 360),
            shape,
        )

    def _drone_delay(self) -> float:
        return self.rng.uniform(9.0, 16.0) / (1 + 0.08 * self.wave)

    # ------------------------------------------------------------------ input
    def fire(self) -> bool:
        """Shoot if possible. Returns whether a bullet was fired."""
        if not self.ship_alive or self.over or self.cooldown > 0:
            return False
        if sum(1 for b in self.bullets if b.friendly) >= MAX_BULLETS:
            return False
        s = self.ship
        dx, dy = heading(s.angle)
        self.bullets.append(
            Bullet(
                s.x + dx * SHIP_RADIUS,
                s.y + dy * SHIP_RADIUS,
                s.vx + dx * BULLET_SPEED,
                s.vy + dy * BULLET_SPEED,
                BULLET_LIFE,
                True,
            )
        )
        self.cooldown = FIRE_COOLDOWN
        self._events.append(Event("shot", s.x, s.y))
        return True

    def warp(self) -> bool:
        """Jump to a random spot away from rocks (an emergency escape)."""
        if not self.ship_alive or self.over or self.warp_cooldown > 0:
            return False
        s = self.ship
        self._events.append(Event("warp", s.x, s.y))
        for _ in range(60):
            x, y = self.rng.uniform(40, FIELD_W - 40), self.rng.uniform(40, FIELD_H - 40)
            if all(distance(x, y, r.x, r.y) > r.radius + 60 for r in self.rocks):
                break
        s.x, s.y, s.vx, s.vy = x, y, 0.0, 0.0
        self.warp_cooldown = WARP_COOLDOWN
        self.invulnerable = max(self.invulnerable, 0.4)
        self._events.append(Event("warp", s.x, s.y))
        return True

    # ------------------------------------------------------------------ simulation
    def update(self, dt: float) -> list[Event]:
        """Advance by ``dt`` seconds and return what happened."""
        while dt > 0 and not self.over:
            step = min(dt, MAX_STEP)
            self._step(step)
            dt -= step
        events, self._events = self._events, []
        return events

    def _step(self, dt: float) -> None:
        self.cooldown = max(0.0, self.cooldown - dt)
        self.warp_cooldown = max(0.0, self.warp_cooldown - dt)
        self.invulnerable = max(0.0, self.invulnerable - dt)
        self._move_ship(dt)
        self._move_bullets(dt)
        for rock in self.rocks:
            rock.x, rock.y = wrap(rock.x + rock.vx * dt, rock.y + rock.vy * dt)
            rock.angle = (rock.angle + rock.spin * dt) % 360
        self._update_drones(dt)
        self._collide()
        self._advance_wave(dt)

    def _move_ship(self, dt: float) -> None:
        if not self.ship_alive:
            self.respawn_timer -= dt
            if self.respawn_timer <= 0 and self._center_is_clear():
                self._respawn()
            return
        s = self.ship
        s.angle = (s.angle + self.turn * TURN_SPEED * dt) % 360
        if self.thrust:
            dx, dy = heading(s.angle)
            s.vx += dx * THRUST * dt
            s.vy += dy * THRUST * dt
        damping = max(0.0, 1 - DRAG * dt)
        s.vx *= damping
        s.vy *= damping
        speed = math.hypot(s.vx, s.vy)
        if speed > MAX_SPEED:
            s.vx *= MAX_SPEED / speed
            s.vy *= MAX_SPEED / speed
        s.x, s.y = wrap(s.x + s.vx * dt, s.y + s.vy * dt)

    def _center_is_clear(self) -> bool:
        cx, cy = FIELD_W / 2, FIELD_H / 2
        rocks_clear = all(distance(cx, cy, r.x, r.y) > SAFE_RADIUS + r.radius for r in self.rocks)
        shots_clear = all(
            distance(cx, cy, b.x, b.y) > SAFE_RADIUS for b in self.bullets if not b.friendly
        )
        return rocks_clear and shots_clear

    def _respawn(self) -> None:
        self.ship = Ship()
        self.ship_alive = True
        self.invulnerable = INVULNERABLE_SECONDS

    def _move_bullets(self, dt: float) -> None:
        alive = []
        for b in self.bullets:
            b.life -= dt
            if b.life > 0:
                b.x, b.y = wrap(b.x + b.vx * dt, b.y + b.vy * dt)
                alive.append(b)
        self.bullets = alive

    def _update_drones(self, dt: float) -> None:
        if self.wave >= FIRST_DRONE_WAVE and not self.drones and self.rocks:
            self.drone_timer -= dt
            if self.drone_timer <= 0:
                self._spawn_drone()
        for d in self.drones:
            d.time += dt
            d.x += d.vx * dt
            d.travelled += abs(d.vx * dt)
            d.y = (d.base_y + math.sin(d.time * 1.7) * 70) % FIELD_H
            d.fire_timer -= dt
            if d.fire_timer <= 0 and self.ship_alive:
                d.fire_timer = DRONE_FIRE_EVERY * (0.7 if d.kind == "small" else 1.0)
                self._drone_shoot(d)
        # Drones leave after one crossing.
        self.drones = [d for d in self.drones if d.travelled < FIELD_W + 2 * d.radius]
        for d in self.drones:
            d.x %= FIELD_W

    def _spawn_drone(self) -> None:
        # Small (accurate, valuable) drones become likelier as the score grows.
        small_chance = min(0.7, 0.1 + self.score / 40_000)
        kind: Literal["large", "small"] = "small" if self.rng.random() < small_chance else "large"
        direction = self.rng.choice((-1, 1))
        y = self.rng.uniform(80, FIELD_H - 80)
        x = 0.0 if direction > 0 else float(FIELD_W)
        speed = DRONE_SPEED * (1.3 if kind == "small" else 1.0)
        self.drones.append(Drone(x, y, direction * speed, kind, y))
        self.drone_timer = self._drone_delay()

    def _drone_shoot(self, d: Drone) -> None:
        if d.kind == "small":
            # Aim at the ship (with a little error that shrinks as the score grows).
            dx = wrapped_delta(d.x, self.ship.x, FIELD_W)
            dy = wrapped_delta(d.y, self.ship.y, FIELD_H)
            error = max(4.0, 18.0 - self.score / 5000)
            angle = math.degrees(math.atan2(dx, -dy)) + self.rng.uniform(-error, error)
        else:
            angle = self.rng.uniform(0, 360)
        vx, vy = heading(angle)
        self.bullets.append(
            Bullet(d.x, d.y, vx * DRONE_BULLET_SPEED, vy * DRONE_BULLET_SPEED, 1.6, False)
        )

    # ------------------------------------------------------------------ collisions
    def _collide(self) -> None:
        for b in list(self.bullets):
            if not b.friendly:
                continue
            rock = next((r for r in self.rocks if distance(b.x, b.y, r.x, r.y) < r.radius), None)
            if rock is not None:
                self.bullets.remove(b)
                self._break_rock(rock, (b.vx, b.vy))
                continue
            drone = next(
                (d for d in self.drones if distance(b.x, b.y, d.x, d.y) < d.radius + 2), None
            )
            if drone is not None:
                self.bullets.remove(b)
                self._destroy_drone(drone, by_player=True)
        # Drones crashing into rocks.
        for d in list(self.drones):
            rock = next(
                (r for r in self.rocks if distance(d.x, d.y, r.x, r.y) < r.radius + d.radius),
                None,
            )
            if rock is not None:
                self._destroy_drone(d, by_player=False)
                self._break_rock(rock, (d.vx, 0.0), award=False)
        if self.ship_alive and self.invulnerable <= 0:
            self._collide_ship()

    def _collide_ship(self) -> None:
        s = self.ship
        rock = next(
            (r for r in self.rocks if distance(s.x, s.y, r.x, r.y) < r.radius + SHIP_RADIUS * 0.8),
            None,
        )
        if rock is not None:
            self._break_rock(rock, (s.vx, s.vy))
            self._lose_ship()
            return
        for d in list(self.drones):
            if distance(s.x, s.y, d.x, d.y) < d.radius + SHIP_RADIUS * 0.8:
                self._destroy_drone(d, by_player=True)
                self._lose_ship()
                return
        for b in self.bullets:
            if not b.friendly and distance(s.x, s.y, b.x, b.y) < SHIP_RADIUS * 0.8:
                self.bullets.remove(b)
                self._lose_ship()
                return

    def _break_rock(self, rock: Rock, impact: tuple[float, float], award: bool = True) -> None:
        self.rocks.remove(rock)
        if award:
            self._add_score(ROCK_SIZES[rock.size][1])
        self._events.append(Event("rock_destroyed", rock.x, rock.y, rock.size))
        if rock.size > 1:
            for _ in range(2):
                self.rocks.append(self._new_rock(rock.x, rock.y, rock.size - 1, (rock.vx, rock.vy)))
        if not self.rocks:
            self.wave_timer = WAVE_DELAY
            self._events.append(Event("wave_cleared", size=self.wave))

    def _destroy_drone(self, drone: Drone, by_player: bool) -> None:
        self.drones.remove(drone)
        if by_player:
            self._add_score(DRONE_POINTS[drone.kind])
            self.drones_destroyed += 1
        self._events.append(Event("drone_destroyed", drone.x, drone.y))

    def _lose_ship(self) -> None:
        s = self.ship
        self.ship_alive = False
        self.lives -= 1
        self.turn, self.thrust = 0, False
        self._events.append(Event("ship_destroyed", s.x, s.y))
        if self.lives <= 0:
            self.over = True
            self._events.append(Event("game_over", s.x, s.y))
        else:
            self.respawn_timer = RESPAWN_SECONDS

    def _add_score(self, points: int) -> None:
        self.score += points
        while self.score >= self.next_extra_life:
            self.next_extra_life += EXTRA_LIFE_EVERY
            if self.lives < MAX_LIVES:
                self.lives += 1
                self._events.append(Event("extra_life"))

    def _advance_wave(self, dt: float) -> None:
        if self.rocks or self.wave_timer <= 0:
            return
        self.wave_timer -= dt
        if self.wave_timer <= 0:
            self.drones.clear()
            self.start_wave(self.wave + 1)
