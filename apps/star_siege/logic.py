"""Star Siege rules: a fixed-screen shooter. Pure Python, no pygame.

Coordinates are in a ``FIELD_W`` × ``FIELD_H`` playfield with the origin at
the top-left. :meth:`SiegeGame.update` returns a list of :class:`Event`
objects so the UI can add particles and effects without the rules knowing
anything about drawing.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Literal

FIELD_W, FIELD_H = 1000, 620

PLAYER_W, PLAYER_H = 52, 28
PLAYER_Y = FIELD_H - 56
PLAYER_SPEED = 430.0
PLAYER_SHOT_SPEED = 760.0
PLAYER_COOLDOWN = 0.28
MAX_PLAYER_SHOTS = 2
START_LIVES = 3
MAX_LIVES = 5
EXTRA_LIFE_EVERY = 1500
INVULNERABLE_SECONDS = 1.6

ROWS, COLS = 5, 10
ENEMY_W, ENEMY_H = 40, 30
SPACING_X, SPACING_Y = 62, 50
EDGE_MARGIN = 16
DROP = 22
BASE_SPEED = 38.0
ROW_KIND = (0, 1, 1, 2, 2)  # enemy type per row, top to bottom
POINTS = (30, 20, 10)  # per enemy type

SHIELD_COUNT = 4
SHIELD_CELL = 8
SHIELD_COLS, SHIELD_ROWS = 11, 7
SHIELD_Y = PLAYER_Y - 96

WAVE_INTRO_SECONDS = 1.6
MAX_STEP = 1 / 120  # physics sub-step so fast bullets can't tunnel through cells

EventKind = Literal[
    "shot", "enemy_destroyed", "player_hit", "shield_hit", "wave_cleared", "extra_life", "game_over"
]


@dataclass(frozen=True)
class Box:
    """An axis-aligned rectangle."""

    x: float
    y: float
    w: float
    h: float

    @property
    def right(self) -> float:
        return self.x + self.w

    @property
    def bottom(self) -> float:
        return self.y + self.h

    @property
    def center(self) -> tuple[float, float]:
        return (self.x + self.w / 2, self.y + self.h / 2)

    def intersects(self, other: Box) -> bool:
        return (
            self.x < other.right
            and other.x < self.right
            and self.y < other.bottom
            and other.y < self.bottom
        )


@dataclass(frozen=True)
class Event:
    kind: EventKind
    x: float = 0.0
    y: float = 0.0
    variant: int = 0


@dataclass
class Enemy:
    row: int
    col: int
    kind: int
    alive: bool = True


@dataclass
class Bullet:
    x: float  # centre x
    y: float  # top
    vy: float
    friendly: bool
    w: float = 4
    h: float = 16

    @property
    def box(self) -> Box:
        return Box(self.x - self.w / 2, self.y, self.w, self.h)


@dataclass
class Shield:
    """A bunker made of small cells that are destroyed one by one."""

    x: float
    y: float
    cells: set[tuple[int, int]] = field(default_factory=set)

    @classmethod
    def build(cls, x: float, y: float) -> Shield:
        cells = set()
        for r in range(SHIELD_ROWS):
            for c in range(SHIELD_COLS):
                corner = r == 0 and c in (0, SHIELD_COLS - 1)
                arch = r >= SHIELD_ROWS - 3 and 3 <= c <= SHIELD_COLS - 4
                if not corner and not arch:
                    cells.add((r, c))
        return cls(x, y, cells)

    def cell_box(self, r: int, c: int) -> Box:
        return Box(self.x + c * SHIELD_CELL, self.y + r * SHIELD_CELL, SHIELD_CELL, SHIELD_CELL)

    @property
    def box(self) -> Box:
        return Box(self.x, self.y, SHIELD_COLS * SHIELD_CELL, SHIELD_ROWS * SHIELD_CELL)

    def hit(self, box: Box, rng: random.Random) -> tuple[int, int] | None:
        """Destroy the first cell overlapping ``box`` (plus some neighbours)."""
        if not self.box.intersects(box):
            return None
        for cell in sorted(self.cells):
            if self.cell_box(*cell).intersects(box):
                self.cells.discard(cell)
                r, c = cell
                for dr, dc in ((0, 1), (0, -1), (1, 0), (-1, 0)):
                    if rng.random() < 0.35:
                        self.cells.discard((r + dr, c + dc))
                return cell
        return None

    def erode(self, box: Box) -> None:
        """Remove every cell overlapping ``box`` (enemies flying through)."""
        self.cells = {cell for cell in self.cells if not self.cell_box(*cell).intersects(box)}


@dataclass
class SiegeGame:
    """Complete game state. Drive it with :attr:`move`, :meth:`fire` and :meth:`update`."""

    rng: random.Random = field(default_factory=random.Random)
    player_x: float = FIELD_W / 2
    lives: int = START_LIVES
    score: int = 0
    wave: int = 0
    move: int = 0  # -1 left, 0 still, 1 right (set by the UI every frame)
    over: bool = False
    invulnerable: float = 0.0
    wave_intro: float = 0.0
    enemies: list[Enemy] = field(default_factory=list)
    bullets: list[Bullet] = field(default_factory=list)
    shields: list[Shield] = field(default_factory=list)
    formation_x: float = 0.0
    formation_y: float = 0.0
    direction: int = 1
    cooldown: float = 0.0
    enemy_fire_timer: float = 1.0
    next_extra_life: int = EXTRA_LIFE_EVERY
    _events: list[Event] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.wave == 0:
            self.start_wave(1)

    # ------------------------------------------------------------------ setup
    def start_wave(self, wave: int) -> None:
        self.wave = wave
        self.enemies = [Enemy(r, c, ROW_KIND[r]) for r in range(ROWS) for c in range(COLS)]
        block_w = (COLS - 1) * SPACING_X + ENEMY_W
        self.formation_x = (FIELD_W - block_w) / 2
        self.formation_y = 60 + min(wave - 1, 6) * 16
        self.direction = 1
        self.bullets.clear()
        gap = FIELD_W / SHIELD_COUNT
        width = SHIELD_COLS * SHIELD_CELL
        self.shields = [
            Shield.build(gap * (i + 0.5) - width / 2, SHIELD_Y) for i in range(SHIELD_COUNT)
        ]
        self.wave_intro = WAVE_INTRO_SECONDS
        self.enemy_fire_timer = 1.0

    # ------------------------------------------------------------------ queries
    @property
    def player_box(self) -> Box:
        return Box(self.player_x - PLAYER_W / 2, PLAYER_Y, PLAYER_W, PLAYER_H)

    def enemy_box(self, e: Enemy) -> Box:
        return Box(
            self.formation_x + e.col * SPACING_X,
            self.formation_y + e.row * SPACING_Y,
            ENEMY_W,
            ENEMY_H,
        )

    def alive_enemies(self) -> list[Enemy]:
        return [e for e in self.enemies if e.alive]

    @property
    def total_enemies(self) -> int:
        return ROWS * COLS

    def formation_speed(self) -> float:
        """Horizontal speed: faster each wave and much faster as the formation thins out."""
        alive = len(self.alive_enemies())
        thinned = 1 - alive / self.total_enemies
        return BASE_SPEED * (1 + 0.15 * (self.wave - 1)) * (1 + 5 * thinned**2)

    def enemy_fire_interval(self) -> float:
        alive = len(self.alive_enemies())
        thinned = 1 - alive / self.total_enemies
        return max(0.3, 1.25 - 0.08 * (self.wave - 1) - 0.5 * thinned)

    # ------------------------------------------------------------------ input
    def fire(self) -> bool:
        """Shoot if the cooldown allows it. Returns whether a shot was fired."""
        if self.over or self.wave_intro > 0 or self.cooldown > 0:
            return False
        if sum(1 for b in self.bullets if b.friendly) >= MAX_PLAYER_SHOTS:
            return False
        self.bullets.append(Bullet(self.player_x, PLAYER_Y - 16, -PLAYER_SHOT_SPEED, True))
        self.cooldown = PLAYER_COOLDOWN
        self._events.append(Event("shot", self.player_x, PLAYER_Y))
        return True

    # ------------------------------------------------------------------ simulation
    def update(self, dt: float) -> list[Event]:
        """Advance the game by ``dt`` seconds and return what happened."""
        steps = max(1, math.ceil(dt / MAX_STEP))
        for _ in range(steps):
            if self.over:
                break
            self._step(dt / steps)
        events, self._events = self._events, []
        return events

    def _step(self, dt: float) -> None:
        self.cooldown = max(0.0, self.cooldown - dt)
        self.invulnerable = max(0.0, self.invulnerable - dt)
        half = PLAYER_W / 2
        self.player_x = min(
            FIELD_W - half, max(half, self.player_x + self.move * PLAYER_SPEED * dt)
        )

        if self.wave_intro > 0:
            self.wave_intro -= dt
            return
        self._move_formation(dt)
        self._enemy_fire(dt)
        self._move_bullets(dt)
        if not self.over and not self.alive_enemies():
            self._events.append(Event("wave_cleared", variant=self.wave))
            self.start_wave(self.wave + 1)

    def _move_formation(self, dt: float) -> None:
        alive = self.alive_enemies()
        if not alive:
            return
        self.formation_x += self.direction * self.formation_speed() * dt
        boxes = [self.enemy_box(e) for e in alive]
        left = min(b.x for b in boxes)
        right = max(b.right for b in boxes)
        if (self.direction > 0 and right >= FIELD_W - EDGE_MARGIN) or (
            self.direction < 0 and left <= EDGE_MARGIN
        ):
            # Clamp back inside, drop down and reverse.
            overshoot = (
                right - (FIELD_W - EDGE_MARGIN) if self.direction > 0 else left - EDGE_MARGIN
            )
            self.formation_x -= overshoot
            self.formation_y += DROP
            self.direction *= -1
            boxes = [self.enemy_box(e) for e in alive]

        for box in boxes:
            for shield in self.shields:
                shield.erode(box)
        if max(b.bottom for b in boxes) >= PLAYER_Y:
            self._game_over()

    def _enemy_fire(self, dt: float) -> None:
        self.enemy_fire_timer -= dt
        if self.enemy_fire_timer > 0:
            return
        self.enemy_fire_timer = self.enemy_fire_interval() * self.rng.uniform(0.6, 1.4)
        # Only the lowest enemy in each column can shoot.
        lowest: dict[int, Enemy] = {}
        for e in self.alive_enemies():
            if e.col not in lowest or e.row > lowest[e.col].row:
                lowest[e.col] = e
        if not lowest:
            return
        # Prefer columns near the player to keep pressure on.
        columns = sorted(
            lowest.values(), key=lambda e: abs(self.enemy_box(e).center[0] - self.player_x)
        )
        shooter = columns[0] if self.rng.random() < 0.4 else self.rng.choice(columns)
        box = self.enemy_box(shooter)
        speed = 290 + 18 * min(self.wave - 1, 10)
        self.bullets.append(Bullet(box.center[0], box.bottom, speed, False, w=5, h=14))

    def _move_bullets(self, dt: float) -> None:
        remaining: list[Bullet] = []
        for bullet in self.bullets:
            bullet.y += bullet.vy * dt
            if bullet.y + bullet.h < 0 or bullet.y > FIELD_H:
                continue
            if self._resolve_hit(bullet):
                continue
            remaining.append(bullet)
        # Player and enemy shots cancel each other out.
        friendly = [b for b in remaining if b.friendly]
        hostile = [b for b in remaining if not b.friendly]
        for f in friendly:
            for h in hostile:
                if f.box.intersects(h.box):
                    remaining = [b for b in remaining if b is not f and b is not h]
                    hostile.remove(h)
                    break
        self.bullets = remaining

    def _resolve_hit(self, bullet: Bullet) -> bool:
        box = bullet.box
        for shield in self.shields:
            cell = shield.hit(box, self.rng)
            if cell is not None:
                cx, cy = shield.cell_box(*cell).center
                self._events.append(Event("shield_hit", cx, cy))
                return True
        if bullet.friendly:
            for e in self.alive_enemies():
                ebox = self.enemy_box(e)
                if ebox.intersects(box):
                    e.alive = False
                    self._add_score(POINTS[e.kind])
                    self._events.append(Event("enemy_destroyed", *ebox.center, variant=e.kind))
                    return True
            return False
        if self.invulnerable <= 0 and self.player_box.intersects(box):
            self._player_hit()
            return True
        return False

    def _add_score(self, points: int) -> None:
        self.score += points
        if self.score >= self.next_extra_life:
            self.next_extra_life += EXTRA_LIFE_EVERY
            if self.lives < MAX_LIVES:
                self.lives += 1
                self._events.append(Event("extra_life", self.player_x, PLAYER_Y))

    def _player_hit(self) -> None:
        self.lives -= 1
        x, y = self.player_box.center
        self._events.append(Event("player_hit", x, y))
        if self.lives <= 0:
            self._game_over()
            return
        self.invulnerable = INVULNERABLE_SECONDS
        self.bullets = [b for b in self.bullets if b.friendly]

    def _game_over(self) -> None:
        if not self.over:
            self.over = True
            self._events.append(Event("game_over", *self.player_box.center))
