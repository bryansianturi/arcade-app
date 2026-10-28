"""Firefly rules: collect motes of light in a maze while four shades hunt you.

Pure Python, no pygame. Everything moves on a tile grid: an actor sits on a
tile and is ``progress`` (0..1) of the way to the next tile in its direction.
Rows marked as tunnels wrap around at the left and right edges.

Each shade has its own way of choosing a target tile while chasing:

* **Stalker**: your tile.
* **Ambusher**: four tiles ahead of you.
* **Flanker**: the Stalker's position mirrored through a point two tiles ahead
  of you, so the two close in from opposite sides.
* **Wanderer**: chases from afar, but heads home once within eight tiles.

Shades alternate between *scatter* (each retreats to its own corner) and
*chase*. Eating a lantern frightens them for a while, and frightened shades can
be caught for 200, 400, 800 then 1600 points.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Literal

#: The maze. ``#`` wall · ``.`` mote · ``o`` lantern · ``P`` start · ``H`` shade house ·
#: ``-`` house door (shades only) · space: empty floor (or unreachable void).
MAZE = (
    "#####################",
    "#.........#.........#",
    "#o###.###.#.###.###o#",
    "#.###.###.#.###.###.#",
    "#...................#",
    "#.###.#.#####.#.###.#",
    "#.....#...#...#.....#",
    "#####.###.#.###.#####",
    "    #.#.......#.#    ",
    "#####.#.##-##.#.#####",
    "     ...#HHH#...     ",
    "#####.#.#####.#.#####",
    "    #.#.......#.#    ",
    "#####.#.#####.#.#####",
    "#.........#.........#",
    "#.###.###.#.###.###.#",
    "#o..#.....P.....#..o#",
    "###.#.#.#####.#.#.###",
    "#.....#...#...#.....#",
    "#.#######.#.#######.#",
    "#...................#",
    "#####################",
)
COLS, ROWS = len(MAZE[0]), len(MAZE)

Tile = tuple[int, int]  # (col, row)
Direction = tuple[int, int]
UP: Direction = (0, -1)
DOWN: Direction = (0, 1)
LEFT: Direction = (-1, 0)
RIGHT: Direction = (1, 0)
STOP: Direction = (0, 0)
#: Tie-break order when two moves are equally good.
DIRECTIONS: tuple[Direction, ...] = (UP, LEFT, DOWN, RIGHT)

PLAYER_SPEED = 7.6  # tiles per second
SHADE_SPEED = 7.0
FRIGHTENED_SPEED = 4.4
RETURN_SPEED = 15.0
TUNNEL_SPEED = 4.0
SPEEDUP_PER_LEVEL = 0.04  # +4% per level, capped below
MAX_SPEEDUP = 0.25
CATCH_DISTANCE = 0.6  # tiles

MOTE_POINTS = 10
LANTERN_POINTS = 50
SHADE_POINTS = (200, 400, 800, 1600)
START_LIVES = 3
EXTRA_LIFE_AT = 10_000

#: Alternating scatter/chase phases (seconds); the last chase lasts forever.
PHASES = (7.0, 20.0, 7.0, 20.0, 5.0, 20.0, 5.0)
DEATH_PAUSE = 1.6
LEVEL_PAUSE = 2.0

Personality = Literal["stalker", "ambusher", "flanker", "wanderer"]
PERSONALITIES: tuple[Personality, ...] = ("stalker", "ambusher", "flanker", "wanderer")
SCATTER_CORNERS: dict[Personality, Tile] = {
    "stalker": (COLS - 2, -3),
    "ambusher": (1, -3),
    "flanker": (COLS - 1, ROWS + 1),
    "wanderer": (0, ROWS + 1),
}
RELEASE_AFTER: dict[Personality, float] = {
    "stalker": 0.0,
    "ambusher": 1.5,
    "flanker": 5.0,
    "wanderer": 9.0,
}
WANDERER_SHY_DISTANCE = 8

ShadeState = Literal["house", "leaving", "active", "returning"]
EventKind = Literal[
    "mote", "lantern", "shade_caught", "player_caught", "level_clear", "game_over", "extra_life"
]


def find(char: str) -> list[Tile]:
    return [(c, r) for r, row in enumerate(MAZE) for c, ch in enumerate(row) if ch == char]


PLAYER_START: Tile = find("P")[0]
DOOR: Tile = find("-")[0]
HOUSE: tuple[Tile, ...] = tuple(find("H"))
HOUSE_EXIT: Tile = (DOOR[0], DOOR[1] - 1)
TUNNEL_ROWS = frozenset(r for r, row in enumerate(MAZE) if row[0] == " " and row[-1] == " ")


def wrap_col(col: int) -> int:
    return col % COLS


def is_tunnel(tile: Tile) -> bool:
    """Tunnel floor outside the maze walls (slow for shades)."""
    col, row = tile
    if row not in TUNNEL_ROWS:
        return False
    line = MAZE[row]
    return line[: col + 1].strip() == "" or line[col:].strip() == ""


def walkable(tile: Tile, *, shade: bool = False, door: bool = False) -> bool:
    col, row = tile
    if not 0 <= row < ROWS:
        return False
    ch = MAZE[row][wrap_col(col)]
    if ch == "#":
        return False
    if ch == "-":
        return door
    if ch == "H":
        return shade and door
    return True


def step(tile: Tile, direction: Direction) -> Tile:
    return wrap_col(tile[0] + direction[0]), tile[1] + direction[1]


def opposite(direction: Direction) -> Direction:
    return -direction[0], -direction[1]


def tile_distance_sq(a: Tile, b: Tile) -> int:
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2


@dataclass
class Actor:
    tile: Tile
    direction: Direction = STOP
    progress: float = 0.0  # 0..1 towards ``step(tile, direction)``

    @property
    def x(self) -> float:
        """Column as a float (may briefly be -0.x or COLS-0.x in a tunnel)."""
        return self.tile[0] + self.direction[0] * self.progress

    @property
    def y(self) -> float:
        return self.tile[1] + self.direction[1] * self.progress

    def distance_to(self, other: Actor) -> float:
        dx = abs(self.x - other.x)
        dx = min(dx, COLS - dx)
        return float((dx**2 + (self.y - other.y) ** 2) ** 0.5)


@dataclass
class Shade(Actor):
    personality: Personality = "stalker"
    state: ShadeState = "house"
    frightened: bool = False
    house_timer: float = 0.0


@dataclass(frozen=True)
class Event:
    kind: EventKind
    tile: Tile = (0, 0)
    points: int = 0


@dataclass
class Firefly:
    """Complete game state. Steer with :attr:`want`; advance with :meth:`update`."""

    rng: random.Random = field(default_factory=random.Random)
    level: int = 1
    score: int = 0
    lives: int = START_LIVES
    over: bool = False
    want: Direction = STOP  # the direction the player is asking for
    player: Actor = field(default_factory=lambda: Actor(PLAYER_START))
    shades: list[Shade] = field(default_factory=list)
    motes: set[Tile] = field(default_factory=set)
    lanterns: set[Tile] = field(default_factory=set)
    phase: int = 0
    phase_timer: float = PHASES[0]
    fright_timer: float = 0.0
    combo: int = 0  # shades caught during the current fright
    pause: float = 0.0  # frozen after a catch or between levels
    pending: Literal["", "respawn", "level"] = ""
    extra_life_given: bool = False
    _events: list[Event] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._load_level()

    # ------------------------------------------------------------------ setup
    def _load_level(self) -> None:
        self.motes = set(find("."))
        self.lanterns = set(find("o"))
        self.phase = 0
        self.phase_timer = PHASES[0]
        self.fright_timer = 0.0
        self._reset_actors()

    def _reset_actors(self) -> None:
        self.player = Actor(PLAYER_START)
        self.want = STOP
        house = list(HOUSE)
        self.shades = []
        for i, personality in enumerate(PERSONALITIES):
            if personality == "stalker":
                shade = Shade(HOUSE_EXIT, LEFT, personality=personality, state="active")
            else:
                shade = Shade(house[min(i - 1, len(house) - 1)], personality=personality)
                shade.house_timer = RELEASE_AFTER[personality] / (1 + 0.3 * (self.level - 1))
            self.shades.append(shade)

    @property
    def speedup(self) -> float:
        return 1 + min(MAX_SPEEDUP, SPEEDUP_PER_LEVEL * (self.level - 1))

    @property
    def fright_seconds(self) -> float:
        return max(2.0, 7.0 - 0.6 * (self.level - 1))

    @property
    def scattering(self) -> bool:
        return self.phase < len(PHASES) and self.phase % 2 == 0

    @property
    def remaining(self) -> int:
        return len(self.motes) + len(self.lanterns)

    # ------------------------------------------------------------------ simulation
    def update(self, dt: float) -> list[Event]:
        if not self.over:
            remaining = dt
            while remaining > 0 and not self.over:
                chunk = min(remaining, 1 / 120)
                self._step(chunk)
                remaining -= chunk
        events, self._events = self._events, []
        return events

    def _step(self, dt: float) -> None:
        if self.pause > 0:
            self.pause -= dt
            if self.pause <= 0:
                if self.pending == "respawn":
                    self._reset_actors()
                elif self.pending == "level":
                    self.level += 1
                    self._load_level()
                self.pending = ""
            return
        self._update_phase(dt)
        self._move_player(dt)
        self._eat()
        if self.pending:  # the maze was just cleared
            return
        for shade in self.shades:
            self._move_shade(shade, dt)
        self._collide()

    def _update_phase(self, dt: float) -> None:
        if self.fright_timer > 0:
            self.fright_timer -= dt
            if self.fright_timer <= 0:
                for s in self.shades:
                    s.frightened = False
            return  # the scatter/chase clock pauses while shades are frightened
        if self.phase < len(PHASES):
            self.phase_timer -= dt
            if self.phase_timer <= 0:
                self.phase += 1
                if self.phase < len(PHASES):
                    self.phase_timer = PHASES[self.phase]
                for s in self.shades:  # a phase change makes active shades turn around
                    if s.state == "active":
                        self._reverse(s)

    # ------------------------------------------------------------------ player
    def _move_player(self, dt: float) -> None:
        p = self.player
        if p.direction != STOP and self.want == opposite(p.direction):
            # Turning back is allowed at any time.
            p.tile, p.progress, p.direction = step(p.tile, p.direction), 1 - p.progress, self.want
        if p.direction == STOP:
            self._choose_player_direction()
        p.progress += PLAYER_SPEED * self.speedup * dt
        while p.direction != STOP and p.progress >= 1:
            p.tile = step(p.tile, p.direction)
            p.progress -= 1
            self._eat()
            self._choose_player_direction()
        if p.direction == STOP:
            p.progress = 0.0

    def _choose_player_direction(self) -> None:
        p = self.player
        if self.want != STOP and walkable(step(p.tile, self.want)):
            p.direction = self.want
        elif p.direction == STOP or not walkable(step(p.tile, p.direction)):
            p.direction = STOP

    def _eat(self) -> None:
        p = self.player
        tile = p.tile if p.progress < 0.5 else step(p.tile, p.direction)
        if tile in self.motes:
            self.motes.discard(tile)
            self._add_score(MOTE_POINTS)
            self._events.append(Event("mote", tile, MOTE_POINTS))
        elif tile in self.lanterns:
            self.lanterns.discard(tile)
            self._add_score(LANTERN_POINTS)
            self._events.append(Event("lantern", tile, LANTERN_POINTS))
            self._frighten()
        if self.remaining == 0 and not self.pending:
            self._events.append(Event("level_clear", tile))
            self.pause, self.pending = LEVEL_PAUSE, "level"

    def _frighten(self) -> None:
        self.fright_timer = self.fright_seconds
        self.combo = 0
        for s in self.shades:
            if s.state == "active":
                s.frightened = True
                self._reverse(s)

    def _add_score(self, points: int) -> None:
        self.score += points
        if not self.extra_life_given and self.score >= EXTRA_LIFE_AT:
            self.extra_life_given = True
            self.lives += 1
            self._events.append(Event("extra_life"))

    # ------------------------------------------------------------------ shades
    @staticmethod
    def _reverse(s: Shade) -> None:
        if s.direction != STOP:
            s.tile, s.progress, s.direction = (
                step(s.tile, s.direction),
                1 - s.progress,
                opposite(s.direction),
            )

    def _shade_speed(self, s: Shade) -> float:
        if s.state == "returning":
            return RETURN_SPEED
        if s.state in ("house", "leaving"):
            return SHADE_SPEED * 0.5
        if is_tunnel(s.tile):
            return TUNNEL_SPEED
        if s.frightened:
            return FRIGHTENED_SPEED
        return SHADE_SPEED * self.speedup

    def _move_shade(self, s: Shade, dt: float) -> None:
        if s.state == "house":
            s.house_timer -= dt
            if s.house_timer <= 0:
                s.state = "leaving"
            return
        if s.direction == STOP:
            s.direction = self._choose(s)
        s.progress += self._shade_speed(s) * dt
        while s.progress >= 1 and s.direction != STOP:
            s.tile = step(s.tile, s.direction)
            s.progress -= 1
            if s.state == "leaving" and s.tile == HOUSE_EXIT:
                s.state = "active"
            elif s.state == "returning" and s.tile in HOUSE:
                s.state, s.frightened = "leaving", False
            s.direction = self._choose(s)

    def target(self, s: Shade) -> Tile:
        """The tile ``s`` is heading for right now."""
        if s.state == "leaving":
            return HOUSE_EXIT
        if s.state == "returning":
            return HOUSE[len(HOUSE) // 2]
        if self.scattering:
            return SCATTER_CORNERS[s.personality]
        p = self.player.tile
        facing = self.player.direction
        if s.personality == "ambusher":
            return p[0] + 4 * facing[0], p[1] + 4 * facing[1]
        if s.personality == "flanker":
            stalker = next((x for x in self.shades if x.personality == "stalker"), s)
            pivot = (p[0] + 2 * facing[0], p[1] + 2 * facing[1])
            return 2 * pivot[0] - stalker.tile[0], 2 * pivot[1] - stalker.tile[1]
        if s.personality == "wanderer":
            near = tile_distance_sq(s.tile, p) < WANDERER_SHY_DISTANCE**2
            return SCATTER_CORNERS["wanderer"] if near else p
        return p

    def _choose(self, s: Shade) -> Direction:
        through_door = s.state in ("leaving", "returning")
        options = [
            d
            for d in DIRECTIONS
            if walkable(step(s.tile, d), shade=True, door=through_door)
            and (d != opposite(s.direction) or through_door)
        ]
        if not options:  # dead end: turn around
            back = opposite(s.direction)
            return back if walkable(step(s.tile, back), shade=True, door=through_door) else STOP
        if s.frightened and s.state == "active":
            return self.rng.choice(options)
        goal = self.target(s)
        return min(options, key=lambda d: tile_distance_sq(step(s.tile, d), goal))

    # ------------------------------------------------------------------ collisions
    def _collide(self) -> None:
        for s in self.shades:
            if s.state != "active" or self.player.distance_to(s) > CATCH_DISTANCE:
                continue
            if s.frightened:
                points = SHADE_POINTS[min(self.combo, len(SHADE_POINTS) - 1)]
                self.combo += 1
                s.state, s.frightened = "returning", False
                self._add_score(points)
                self._events.append(Event("shade_caught", s.tile, points))
            else:
                self._caught()
                return

    def _caught(self) -> None:
        self.lives -= 1
        self._events.append(Event("player_caught", self.player.tile))
        if self.lives <= 0:
            self.over = True
            self._events.append(Event("game_over", self.player.tile))
        else:
            self.pause, self.pending = DEATH_PAUSE, "respawn"
            self.fright_timer = 0.0
