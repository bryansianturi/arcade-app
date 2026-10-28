from __future__ import annotations

import itertools
import random

import pytest

from apps.skyhop.logic import (
    EDGE_MARGIN,
    FIELD_H,
    GATE_SPACING,
    GATE_W,
    HOP_VELOCITY,
    MAX_GAP_SHIFT,
    MIN_GAP,
    PLAYER_R,
    PLAYER_X,
    Gate,
    Skyhop,
    circle_hits_rect,
)
from core.base_app import AppContext


def flying(seed: int = 0) -> Skyhop:
    g = Skyhop(random.Random(seed))
    g.hop()
    return g


def test_ready_state_bobs_without_falling() -> None:
    g = Skyhop(random.Random(0))
    g.update(3)
    assert g.state == "ready" and abs(g.y - FIELD_H * 0.42) <= 8 and not g.gates


def test_first_hop_starts_the_game() -> None:
    g = flying()
    assert g.state == "flying" and g.vy == HOP_VELOCITY and len(g.gates) == 1


def test_gravity_pulls_down_and_ground_ends_the_game() -> None:
    g = flying()
    g.gates.clear()
    y = g.y
    g.update(0.5)
    assert g.y > y - 100  # rose briefly, then started falling
    g.update(3)
    assert g.state == "over" and g.y == g.ground_y - PLAYER_R


def test_hitting_the_ceiling_kills() -> None:
    g = flying()
    g.gates.clear()
    for _ in range(40):
        g.hop()
        g.update(0.05)
    assert g.state in ("falling", "over")


def test_passing_a_gate_scores_and_hitting_one_falls() -> None:
    g = flying()
    cruise = g.y
    g.gates = [Gate(PLAYER_X + 40, cruise, 400)]  # huge gap right in front
    scored = False
    for _ in range(60):
        if g.y > cruise:  # simple autopilot: hold altitude
            g.hop()
        scored |= g.update(1 / 60)
    assert scored and g.score == 1 and g.state == "flying"

    g = flying()
    g.gates = [Gate(PLAYER_X + 20, g.y - 300, 120)]  # gap far above: crash into the lower pillar
    g.update(0.3)
    assert g.state in ("falling", "over")


def test_gates_keep_spawning_with_bounded_gaps() -> None:
    g = flying(3)
    g.gates[0].gap_y = 300
    for _ in range(600):
        g.update(1 / 60)
        if g.state != "flying":
            g.state = "flying"  # keep the world scrolling for this test
            g.y = 300
        g.vy = 0
    assert len(g.gates) >= 3
    xs = [gate.x for gate in g.gates]
    assert all(b - a == pytest.approx(GATE_SPACING) for a, b in itertools.pairwise(xs))
    for a, b in itertools.pairwise(g.gates):
        assert abs(b.gap_y - a.gap_y) <= MAX_GAP_SHIFT + 1e-6
        assert b.gap_y - b.gap / 2 >= EDGE_MARGIN - 1e-6
        assert b.gap_y + b.gap / 2 <= g.ground_y - EDGE_MARGIN + 1e-6


def test_difficulty_ramps_and_caps() -> None:
    g = Skyhop(random.Random(0))
    base_speed, base_gap = g.speed, g.gap
    g.score = 10
    assert g.speed > base_speed and g.gap < base_gap
    g.score = 1000
    assert g.gap == MIN_GAP and g.speed <= 400


def test_circle_rect_collision() -> None:
    assert circle_hits_rect(0, 0, 10, 5, -5, 10, 10)
    assert not circle_hits_rect(0, 0, 10, 20, 20, 5, 5)
    assert GATE_W > 0


def test_app_records_best(app_context: AppContext) -> None:
    from apps.skyhop.app import SkyhopApp

    app = SkyhopApp(app_context)
    app.on_enter()
    app._hop()
    app.game.score = 9
    app.game.gates.clear()
    app.update(5)
    assert app.game.state == "over" and app.menu is not None and app.new_best
