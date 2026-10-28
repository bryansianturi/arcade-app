"""Skyhop rules: one-button flying through gaps. No pygame.

Difficulty ramps with the score: gates move faster and gaps get smaller,
both capped so the game stays fair.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Literal

FIELD_W, FIELD_H = 1000, 620
GROUND_H = 56
PLAYER_X = 260
PLAYER_R = 16
GRAVITY = 1850.0
HOP_VELOCITY = -560.0
MAX_FALL = 880.0
GATE_W = 84
GATE_SPACING = 310
START_SPEED, MAX_GATE_SPEED, SPEED_PER_POINT = 240.0, 400.0, 4.0
START_GAP, MIN_GAP, GAP_PER_POINT = 196.0, 140.0, 2.0
MAX_GAP_SHIFT = 170.0  # how far the gap centre can move between neighbouring gates
EDGE_MARGIN = 70.0
MAX_STEP = 1 / 240

State = Literal["ready", "flying", "falling", "over"]


@dataclass
class Gate:
    x: float  # left edge
    gap_y: float  # centre of the gap
    gap: float
    passed: bool = False

    @property
    def top_bottom(self) -> float:
        """y where the upper pillar ends."""
        return self.gap_y - self.gap / 2

    @property
    def bottom_top(self) -> float:
        """y where the lower pillar starts."""
        return self.gap_y + self.gap / 2


def circle_hits_rect(
    cx: float, cy: float, r: float, x: float, y: float, w: float, h: float
) -> bool:
    nx = max(x, min(cx, x + w))
    ny = max(y, min(cy, y + h))
    return (cx - nx) ** 2 + (cy - ny) ** 2 < r * r


@dataclass
class Skyhop:
    rng: random.Random = field(default_factory=random.Random)
    y: float = FIELD_H * 0.42
    vy: float = 0.0
    score: int = 0
    state: State = "ready"
    gates: list[Gate] = field(default_factory=list)
    distance: float = 0.0  # total scrolled, for parallax
    time: float = 0.0

    @property
    def speed(self) -> float:
        return min(MAX_GATE_SPEED, START_SPEED + SPEED_PER_POINT * self.score)

    @property
    def gap(self) -> float:
        return max(MIN_GAP, START_GAP - GAP_PER_POINT * self.score)

    @property
    def ground_y(self) -> float:
        return FIELD_H - GROUND_H

    @property
    def tilt(self) -> float:
        """Visual nose angle in degrees, derived from vertical speed."""
        return max(-25.0, min(70.0, self.vy / MAX_FALL * 70))

    def hop(self) -> None:
        if self.state == "ready":
            self.state = "flying"
            self._spawn_gate(FIELD_W + 120)
        if self.state == "flying":
            self.vy = HOP_VELOCITY

    def update(self, dt: float) -> bool:
        """Advance the game. Returns ``True`` if a gate was passed this frame."""
        scored = False
        steps = max(1, math.ceil(dt / MAX_STEP))
        for _ in range(steps):
            scored |= self._step(dt / steps)
        return scored

    def _step(self, dt: float) -> bool:
        self.time += dt
        if self.state == "ready":
            self.y = FIELD_H * 0.42 + math.sin(self.time * 3) * 8  # idle bob
            self.distance += START_SPEED * 0.5 * dt
            return False
        if self.state == "over":
            return False

        self.vy = min(MAX_FALL, self.vy + GRAVITY * dt)
        self.y += self.vy * dt
        if self.y + PLAYER_R >= self.ground_y:
            self.y = self.ground_y - PLAYER_R
            self.state = "over"
            return False
        if self.state == "falling":
            return False

        scored = False
        speed = self.speed  # read once: scoring below changes it mid-loop
        self.distance += speed * dt
        for gate in self.gates:
            gate.x -= speed * dt
            if not gate.passed and gate.x + GATE_W / 2 < PLAYER_X:
                gate.passed = True
                self.score += 1
                scored = True
        self.gates = [g for g in self.gates if g.x + GATE_W > -10]
        if self.gates and self.gates[-1].x < FIELD_W + 120 - GATE_SPACING:
            self._spawn_gate(self.gates[-1].x + GATE_SPACING)

        if self.y - PLAYER_R <= 0 or self._hits_gate():
            self.state = "falling"
            self.vy = max(self.vy, 0.0)
        return scored

    def _hits_gate(self) -> bool:
        for g in self.gates:
            if circle_hits_rect(
                PLAYER_X, self.y, PLAYER_R - 2, g.x, -100, GATE_W, g.top_bottom + 100
            ):
                return True
            if circle_hits_rect(PLAYER_X, self.y, PLAYER_R - 2, g.x, g.bottom_top, GATE_W, FIELD_H):
                return True
        return False

    def _spawn_gate(self, x: float) -> None:
        gap = self.gap
        low = EDGE_MARGIN + gap / 2
        high = self.ground_y - EDGE_MARGIN - gap / 2
        if self.gates:
            prev = self.gates[-1].gap_y
            low, high = max(low, prev - MAX_GAP_SHIFT), min(high, prev + MAX_GAP_SHIFT)
        self.gates.append(Gate(x, self.rng.uniform(low, high), gap))
