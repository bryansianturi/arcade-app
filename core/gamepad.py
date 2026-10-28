"""Gamepad support through ``pygame.joystick``, mapped to the shared actions.

Pads can be plugged in or removed at any time. The D-pad (hat) and left stick
give directions; buttons map to ``action`` and ``pause``. The stick is turned
into digital presses with a dead zone and hysteresis, so it behaves like a
D-pad in menus and grid games.

Button numbering differs between controllers; :data:`DEFAULT_BUTTONS` covers the
common layouts (Xbox/PlayStation/Switch Pro via SDL): the bottom face button
confirms, the right face button backs out, and Start/Back/Select pause.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from typing import TYPE_CHECKING

import pygame

if TYPE_CHECKING:
    from core.input import Action

log = logging.getLogger(__name__)

DEFAULT_BUTTONS: dict[int, Action] = {
    0: "action",  # A / Cross
    1: "pause",  # B / Circle: back
    6: "pause",  # Back / Select / Share (XInput)
    7: "pause",  # Start / Options (XInput)
    9: "pause",  # Start on many other pads
}
STICK_PRESS = 0.55  # stick deflection that counts as a press
STICK_RELEASE = 0.35  # ... and that releases it again (hysteresis)

#: (action, pressed, source) where source identifies the control for held-state.
GamepadAction = tuple["Action", bool, str]


class GamepadInput:
    """Tracks connected pads and converts their events into action presses."""

    def __init__(self, buttons: dict[int, Action] | None = None) -> None:
        self.buttons = dict(DEFAULT_BUTTONS if buttons is None else buttons)
        self.pads: dict[int, pygame.joystick.JoystickType] = {}
        # (instance_id, axis) -> direction currently pressed by that axis
        self._axis_state: dict[tuple[int, int], Action | None] = {}
        self._hat_state: dict[tuple[int, int], tuple[int, int]] = {}

    @property
    def connected(self) -> list[str]:
        """Names of connected pads."""
        return [pad.get_name() for pad in self.pads.values()]

    def translate(self, event: pygame.event.Event) -> Iterator[GamepadAction]:
        if event.type == pygame.JOYDEVICEADDED:
            self._add(event.device_index)
        elif event.type == pygame.JOYDEVICEREMOVED:
            yield from self._remove(event.instance_id)
        elif event.type in (pygame.JOYBUTTONDOWN, pygame.JOYBUTTONUP):
            action = self.buttons.get(event.button)
            if action is not None:
                source = f"pad:{event.instance_id}:b{event.button}"
                yield action, event.type == pygame.JOYBUTTONDOWN, source
        elif event.type == pygame.JOYHATMOTION:
            yield from self._hat(event.instance_id, event.hat, event.value)
        elif event.type == pygame.JOYAXISMOTION and event.axis in (0, 1):
            yield from self._axis(event.instance_id, event.axis, event.value)

    def _add(self, device_index: int) -> None:
        try:
            pad = pygame.joystick.Joystick(device_index)
        except pygame.error:
            log.exception("Could not open gamepad %d", device_index)
            return
        self.pads[pad.get_instance_id()] = pad
        log.info("Gamepad connected: %s", pad.get_name())

    def _remove(self, instance_id: int) -> Iterator[GamepadAction]:
        pad = self.pads.pop(instance_id, None)
        if pad is not None:
            log.info("Gamepad disconnected: %s", pad.get_name())
        # Release anything that pad was holding.
        for (pid, axis), direction in list(self._axis_state.items()):
            if pid == instance_id:
                del self._axis_state[(pid, axis)]
                if direction is not None:
                    yield direction, False, f"pad:{pid}:a{axis}"
        for pid, hat in list(self._hat_state):
            if pid == instance_id:
                yield from self._hat(pid, hat, (0, 0))
                del self._hat_state[(pid, hat)]
        for button, action in self.buttons.items():
            yield action, False, f"pad:{instance_id}:b{button}"

    def _hat(self, pid: int, hat: int, value: tuple[int, int]) -> Iterator[GamepadAction]:
        old = self._hat_state.get((pid, hat), (0, 0))
        self._hat_state[(pid, hat)] = value
        for axis, (neg, pos) in enumerate((("left", "right"), ("down", "up"))):
            before, after = old[axis], value[axis]
            if before == after:
                continue
            source = f"pad:{pid}:h{hat}{'xy'[axis]}"
            if before:
                yield (pos if before > 0 else neg), False, source  # type: ignore[misc]
            if after:
                yield (pos if after > 0 else neg), True, source  # type: ignore[misc]

    def _axis(self, pid: int, axis: int, value: float) -> Iterator[GamepadAction]:
        neg: Action = "left" if axis == 0 else "up"  # stick y grows downwards
        pos: Action = "right" if axis == 0 else "down"
        current = self._axis_state.get((pid, axis))
        if current is None:
            target: Action | None = (
                pos if value >= STICK_PRESS else neg if value <= -STICK_PRESS else None
            )
        elif abs(value) < STICK_RELEASE or (value > 0) != (current == pos):
            target = pos if value >= STICK_PRESS else neg if value <= -STICK_PRESS else None
        else:
            target = current
        if target == current:
            return
        source = f"pad:{pid}:a{axis}"
        self._axis_state[(pid, axis)] = target
        if current is not None:
            yield current, False, source
        if target is not None:
            yield target, True, source
