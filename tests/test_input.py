"""Shared input mapping: keyboard and gamepad to actions, rebinding, persistence."""

from __future__ import annotations

from typing import Any

import pygame
import pytest

from core.input import (
    ACTIONDOWN,
    ACTIONUP,
    DEFAULT_KEYS,
    InputMap,
    action_of,
    direction,
    is_action,
    key_label,
)
from core.storage import Storage
from tests.conftest import key, key_up

E = pygame.event.Event


def down(m: InputMap, k: int, unicode: str = "", text: bool = False) -> list[pygame.event.Event]:
    return m.translate(key(k, unicode), text_mode=text)


def test_bound_keys_produce_actions() -> None:
    m = InputMap()
    [event] = down(m, pygame.K_a)
    assert event.type == ACTIONDOWN and event.action == "left" and not event.repeat
    assert is_action(event, "left") and action_of(event) == "left"
    assert direction(event) == (-1, 0)
    assert down(m, pygame.K_x) == []  # unbound
    [enter] = down(m, pygame.K_KP_ENTER)  # fixed alias
    assert enter.action == "action"


def test_held_state_and_release() -> None:
    m = InputMap()
    down(m, pygame.K_LEFT)
    down(m, pygame.K_a)
    assert m.held("left")
    [up] = m.translate(key_up(pygame.K_LEFT))
    assert up.type == ACTIONUP and up.action == "left"
    assert m.held("left")  # still held by A
    m.translate(key_up(pygame.K_a))
    assert not m.held("left")


def test_os_key_repeat_is_flagged() -> None:
    m = InputMap()
    [first] = down(m, pygame.K_RIGHT)
    [again] = down(m, pygame.K_RIGHT)
    assert not first.repeat and again.repeat
    assert is_action(again, "right") and not is_action(again, "right", repeat=False)


def test_text_mode_suppresses_printable_keys_only() -> None:
    m = InputMap()
    assert down(m, pygame.K_w, "w", text=True) == []
    assert down(m, pygame.K_SPACE, " ", text=True) == []
    assert [e.action for e in down(m, pygame.K_UP, "", text=True)] == ["up"]
    assert [e.action for e in down(m, pygame.K_RETURN, "\r", text=True)] == ["action"]
    assert [e.action for e in down(m, pygame.K_ESCAPE, "\x1b", text=True)] == ["pause"]


def test_focus_loss_releases_everything() -> None:
    m = InputMap()
    down(m, pygame.K_UP)
    events = m.translate(E(pygame.WINDOWFOCUSLOST))
    assert [(e.type, e.action) for e in events] == [(ACTIONUP, "up")]
    assert not m.held("up")


def test_rebinding_moves_keys_between_actions() -> None:
    m = InputMap()
    m.bind("action", 1, pygame.K_a)  # A was "left"
    assert m.keys_for("action") == (pygame.K_SPACE, pygame.K_a)
    assert m.keys_for("left") == (pygame.K_LEFT,)
    [event] = down(m, pygame.K_a)
    assert event.action == "action"
    m.bind("left", 1, pygame.K_j)  # fills the free slot
    assert m.keys_for("left") == (pygame.K_LEFT, pygame.K_j)
    m.clear("left", 0)
    assert m.keys_for("left") == (pygame.K_j,)
    with pytest.raises(ValueError):
        m.bind("up", 0, pygame.K_F12)
    with pytest.raises(ValueError, match="Pause needs"):
        m.clear("pause", 0)
    with pytest.raises(ValueError, match="Pause needs"):
        m.bind("up", 0, pygame.K_ESCAPE)  # would steal the only pause key
    assert m.keys_for("pause") == (pygame.K_ESCAPE,)
    m.reset()
    assert m.bindings == DEFAULT_KEYS


def test_bindings_round_trip_through_storage(storage: Storage) -> None:
    m = InputMap()
    m.bind("pause", 1, pygame.K_q)
    m.save(storage)
    loaded = InputMap.load(storage)
    assert loaded.bindings == m.bindings
    storage.save_json("input.json", {"up": ["not a key", "i"], "down": "oops", "left": ["f12"]})
    odd = InputMap.load(storage)
    assert odd.keys_for("up") == (pygame.K_i,)
    assert odd.keys_for("down") == DEFAULT_KEYS["down"]
    assert odd.keys_for("left") == ()  # reserved key dropped


def test_labels() -> None:
    m = InputMap()
    assert m.label("action") == "Space" and m.label("pause") == "Esc"
    assert m.labels("left", "right") == "←/→"
    assert key_label(pygame.K_q) == "Q"
    m.bindings["up"] = ()
    assert m.label("up") == "—"


# ---------------------------------------------------------------------- gamepad
def pad(m: InputMap, event_type: int, **attrs: Any) -> list[tuple[int, str]]:
    return [(e.type, e.action) for e in m.translate(E(event_type, instance_id=0, **attrs))]


def test_gamepad_buttons() -> None:
    m = InputMap()
    assert pad(m, pygame.JOYBUTTONDOWN, button=0) == [(ACTIONDOWN, "action")]
    assert m.held("action")
    assert pad(m, pygame.JOYBUTTONUP, button=0) == [(ACTIONUP, "action")]
    assert pad(m, pygame.JOYBUTTONDOWN, button=7) == [(ACTIONDOWN, "pause")]
    assert pad(m, pygame.JOYBUTTONDOWN, button=3) == []  # unmapped


def test_gamepad_hat() -> None:
    m = InputMap()
    assert pad(m, pygame.JOYHATMOTION, hat=0, value=(0, 1)) == [(ACTIONDOWN, "up")]
    assert pad(m, pygame.JOYHATMOTION, hat=0, value=(1, 1)) == [(ACTIONDOWN, "right")]
    assert pad(m, pygame.JOYHATMOTION, hat=0, value=(1, -1)) == [
        (ACTIONUP, "up"),
        (ACTIONDOWN, "down"),
    ]
    assert pad(m, pygame.JOYHATMOTION, hat=0, value=(0, 0)) == [
        (ACTIONUP, "right"),
        (ACTIONUP, "down"),
    ]
    assert not any(m.held(a) for a in ("up", "down", "left", "right"))


def test_gamepad_stick_has_dead_zone_and_hysteresis() -> None:
    m = InputMap()
    assert pad(m, pygame.JOYAXISMOTION, axis=0, value=0.3) == []
    assert pad(m, pygame.JOYAXISMOTION, axis=0, value=0.8) == [(ACTIONDOWN, "right")]
    assert pad(m, pygame.JOYAXISMOTION, axis=0, value=0.45) == []  # still held
    assert pad(m, pygame.JOYAXISMOTION, axis=0, value=0.1) == [(ACTIONUP, "right")]
    assert pad(m, pygame.JOYAXISMOTION, axis=1, value=-0.9) == [(ACTIONDOWN, "up")]
    assert pad(m, pygame.JOYAXISMOTION, axis=1, value=0.9) == [
        (ACTIONUP, "up"),
        (ACTIONDOWN, "down"),
    ]
    assert pad(m, pygame.JOYAXISMOTION, axis=3, value=1.0) == []  # right stick ignored


def test_gamepad_removal_releases_held_controls() -> None:
    m = InputMap()
    pad(m, pygame.JOYAXISMOTION, axis=0, value=-1.0)
    pad(m, pygame.JOYBUTTONDOWN, button=0)
    pad(m, pygame.JOYHATMOTION, hat=0, value=(0, 1))
    released = pad(m, pygame.JOYDEVICEREMOVED)
    assert sorted(released) == sorted([(ACTIONUP, "left"), (ACTIONUP, "action"), (ACTIONUP, "up")])
    assert not any(m.held(a) for a in ("left", "action", "up"))
