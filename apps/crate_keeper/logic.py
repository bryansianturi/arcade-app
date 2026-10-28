"""Crate Keeper rules: push every crate onto a target. Pure Python, no pygame.

Levels use the usual text notation::

    #  wall          .  target
    $  crate         *  crate on a target
    @  keeper        +  keeper on a target
       (space) floor

They are stored as JSON files in ``levels/`` next to this module, each with a
``name`` and a ``map`` (a list of rows). :func:`solve` is a breadth-first
search over crate pushes; the test-suite uses it to prove every bundled level
can be solved.
"""

from __future__ import annotations

import json
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

Pos = tuple[int, int]  # (row, col)
LEVELS_DIR = Path(__file__).parent / "levels"

DIRECTIONS: dict[str, Pos] = {"up": (-1, 0), "down": (1, 0), "left": (0, -1), "right": (0, 1)}


class LevelError(ValueError):
    """A level file is malformed."""


@dataclass(frozen=True)
class Level:
    name: str
    walls: frozenset[Pos]
    goals: frozenset[Pos]
    boxes: frozenset[Pos]
    start: Pos
    width: int
    height: int

    @classmethod
    def parse(cls, name: str, rows: list[str]) -> Level:
        walls, goals, boxes = set(), set(), set()
        start: Pos | None = None
        for r, row in enumerate(rows):
            for c, ch in enumerate(row):
                if ch == "#":
                    walls.add((r, c))
                elif ch in ".*+":
                    goals.add((r, c))
                if ch in "$*":
                    boxes.add((r, c))
                if ch in "@+":
                    if start is not None:
                        raise LevelError(f"{name}: more than one keeper")
                    start = (r, c)
                if ch not in "#.$*@+ ":
                    raise LevelError(f"{name}: unknown character {ch!r}")
        if start is None:
            raise LevelError(f"{name}: no keeper")
        if not boxes or len(boxes) != len(goals):
            raise LevelError(f"{name}: {len(boxes)} crates but {len(goals)} targets")
        level = cls(
            name,
            frozenset(walls),
            frozenset(goals),
            frozenset(boxes),
            start,
            max(len(r) for r in rows),
            len(rows),
        )
        if level._leaks():
            raise LevelError(f"{name}: the keeper can walk off the map")
        return level

    def _leaks(self) -> bool:
        seen, queue = {self.start}, deque([self.start])
        while queue:
            r, c = queue.popleft()
            if not (0 <= r < self.height and 0 <= c < self.width):
                return True
            for dr, dc in DIRECTIONS.values():
                nxt = (r + dr, c + dc)
                if nxt not in seen and nxt not in self.walls:
                    seen.add(nxt)
                    queue.append(nxt)
        return False

    def floor(self) -> frozenset[Pos]:
        """Every square the keeper could ever stand on (inside the walls)."""
        seen, queue = {self.start}, deque([self.start])
        while queue:
            r, c = queue.popleft()
            for dr, dc in DIRECTIONS.values():
                nxt = (r + dr, c + dc)
                if nxt not in seen and nxt not in self.walls:
                    seen.add(nxt)
                    queue.append(nxt)
        return frozenset(seen)


def load_levels(folder: Path = LEVELS_DIR) -> list[Level]:
    """Load ``*.json`` levels sorted by file name."""
    levels = []
    for path in sorted(folder.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            rows = data["map"]
            if not (isinstance(rows, list) and all(isinstance(r, str) for r in rows)):
                raise LevelError(f"{path.name}: 'map' must be a list of strings")
            levels.append(Level.parse(str(data.get("name", path.stem)), rows))
        except (OSError, json.JSONDecodeError, KeyError) as exc:
            raise LevelError(f"{path.name}: {exc}") from exc
    return levels


@dataclass
class Game:
    level: Level
    player: Pos = (0, 0)
    boxes: set[Pos] = field(default_factory=set)
    moves: int = 0
    pushes: int = 0
    facing: str = "down"
    _undo: list[tuple[Pos, frozenset[Pos], int, int, str]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.restart()

    def restart(self) -> None:
        self.player = self.level.start
        self.boxes = set(self.level.boxes)
        self.moves = self.pushes = 0
        self._undo.clear()

    @property
    def solved(self) -> bool:
        return self.boxes == set(self.level.goals)

    @property
    def boxes_home(self) -> int:
        return len(self.boxes & self.level.goals)

    def move(self, direction: str) -> str:
        """Step the keeper. Returns ``"push"``, ``"move"`` or ``"blocked"``."""
        dr, dc = DIRECTIONS[direction]
        self.facing = direction
        r, c = self.player
        ahead = (r + dr, c + dc)
        if ahead in self.level.walls or self.solved:
            return "blocked"
        pushing = ahead in self.boxes
        if pushing:
            beyond = (r + 2 * dr, c + 2 * dc)
            if beyond in self.level.walls or beyond in self.boxes:
                return "blocked"
        self._undo.append(
            (self.player, frozenset(self.boxes), self.moves, self.pushes, self.facing)
        )
        if pushing:
            self.boxes.remove(ahead)
            self.boxes.add(beyond)
            self.pushes += 1
        self.player = ahead
        self.moves += 1
        return "push" if pushing else "move"

    def undo(self) -> bool:
        if not self._undo:
            return False
        self.player, boxes, self.moves, self.pushes, self.facing = self._undo.pop()
        self.boxes = set(boxes)
        return True

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)


# ---------------------------------------------------------------------- solver
def dead_squares(level: Level) -> frozenset[Pos]:
    """Floor squares a crate can never be pushed off and onto a target from.

    Computed by pulling crates backwards from every target: anything a crate
    can't be pulled to is dead.
    """
    floor = level.floor()
    alive = set(level.goals)
    queue = deque(level.goals)
    while queue:
        r, c = queue.popleft()
        for dr, dc in DIRECTIONS.values():
            prev = (r + dr, c + dc)  # where the crate came from
            keeper = (r + 2 * dr, c + 2 * dc)  # where the puller stood
            if prev in floor and keeper in floor and prev not in alive:
                alive.add(prev)
                queue.append(prev)
    return frozenset(floor - alive)


def solve(level: Level, max_states: int = 400_000) -> int | None:
    """Fewest pushes needed to solve ``level`` (``None`` if unsolvable within the budget)."""
    dead = dead_squares(level)
    goals = level.goals

    def reachable(player: Pos, boxes: frozenset[Pos]) -> set[Pos]:
        seen, queue = {player}, deque([player])
        while queue:
            r, c = queue.popleft()
            for dr, dc in DIRECTIONS.values():
                nxt = (r + dr, c + dc)
                if nxt not in seen and nxt not in level.walls and nxt not in boxes:
                    seen.add(nxt)
                    queue.append(nxt)
        return seen

    start_boxes = level.boxes
    region = reachable(level.start, start_boxes)
    start = (min(region), start_boxes)
    seen = {start}
    frontier = deque([(level.start, start_boxes, 0)])
    while frontier:
        player, boxes, pushes = frontier.popleft()
        if boxes == goals:
            return pushes
        region = reachable(player, boxes)
        for box in boxes:
            for dr, dc in DIRECTIONS.values():
                stand, to = (box[0] - dr, box[1] - dc), (box[0] + dr, box[1] + dc)
                if stand not in region or to in level.walls or to in boxes or to in dead:
                    continue
                new_boxes = (boxes - {box}) | {to}
                key = (min(reachable(box, new_boxes)), new_boxes)
                if key in seen:
                    continue
                seen.add(key)
                if len(seen) > max_states:
                    return None
                frontier.append((box, new_boxes, pushes + 1))
    return None
