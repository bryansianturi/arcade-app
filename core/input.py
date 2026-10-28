"""Shared, remappable controls.

Instead of hard-coding keys, apps and screens react to *actions*. The main loop
passes every raw event through :meth:`InputMap.translate`, which emits extra
``ACTIONDOWN`` / ``ACTIONUP`` events for bound keyboard keys and gamepad input::

    from core.input import is_action

    def handle_event(self, event):
        if is_action(event, "left"):
            self.move(-1)

Held state (for continuous movement) is available as ``self.input.held("left")``.

The raw key events are still delivered, so app-specific shortcuts (``N`` for a
new game, ``F`` to flag...) keep using ``pygame.KEYDOWN``. An app must not
handle the *same* control both ways.

**Typing.** Scenes that accept text (``Scene.wants_text`` / ``BaseApp.uses_text_input``)
get no actions from printable keys, so typing "w" never also means "up".
Arrows, Enter, Esc and gamepads still work there.

Bindings are saved to ``input.json`` as key names (``"left"``, ``"a"``...).
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Literal, get_args

import pygame

from core.gamepad import GamepadInput
from core.storage import Storage

log = logging.getLogger(__name__)

Action = Literal["up", "down", "left", "right", "action", "pause"]
ACTIONS: tuple[Action, ...] = get_args(Action)

ACTION_LABELS: dict[Action, str] = {
    "up": "Up",
    "down": "Down",
    "left": "Left",
    "right": "Right",
    "action": "Action / confirm",
    "pause": "Pause / back",
}

#: Each action can have this many keys bound.
SLOTS = 2

DEFAULT_KEYS: dict[Action, tuple[int, ...]] = {
    "up": (pygame.K_UP, pygame.K_w),
    "down": (pygame.K_DOWN, pygame.K_s),
    "left": (pygame.K_LEFT, pygame.K_a),
    "right": (pygame.K_RIGHT, pygame.K_d),
    "action": (pygame.K_SPACE, pygame.K_RETURN),
    "pause": (pygame.K_ESCAPE,),
}

#: Keys that also trigger an action without being remappable.
FIXED_KEYS: dict[int, Action] = {pygame.K_KP_ENTER: "action"}

#: Global hotkeys handled by the main loop; they can't be bound.
RESERVED_KEYS = frozenset({pygame.K_F5, pygame.K_F11, pygame.K_F12})

INPUT_FILE = "input.json"

ACTIONDOWN = pygame.event.custom_type()
ACTIONUP = pygame.event.custom_type()


def is_action(event: pygame.event.Event, action: Action, *, repeat: bool = True) -> bool:
    """Whether ``event`` is a press of ``action``. ``repeat=False`` ignores key repeat."""
    return (
        event.type == ACTIONDOWN
        and event.action == action
        and (repeat or not getattr(event, "repeat", False))
    )


def is_action_up(event: pygame.event.Event, action: Action) -> bool:
    return event.type == ACTIONUP and event.action == action


def action_of(event: pygame.event.Event) -> Action | None:
    """The action pressed by ``event``, or ``None``."""
    if event.type != ACTIONDOWN:
        return None
    action: Action = event.action
    return action


#: Grid steps (dx, dy) for the four direction actions.
DIRECTION_STEPS: dict[Action, tuple[int, int]] = {
    "up": (0, -1),
    "down": (0, 1),
    "left": (-1, 0),
    "right": (1, 0),
}


def direction(event: pygame.event.Event) -> tuple[int, int] | None:
    """The grid step ``(dx, dy)`` if ``event`` presses a direction action, else ``None``."""
    action = action_of(event)
    return None if action is None else DIRECTION_STEPS.get(action)


def key_label(key: int) -> str:
    """Human-readable key name for the controls screen."""
    name = pygame.key.name(key)
    special = {
        "return": "Enter",
        "escape": "Esc",
        "space": "Space",
        "up": "↑",
        "down": "↓",
        "left": "←",
        "right": "→",
    }
    return special.get(name, name.title() if len(name) > 1 else name.upper())


class InputMap:
    """Key bindings plus live held-state, shared by every scene."""

    def __init__(self, bindings: dict[Action, tuple[int, ...]] | None = None) -> None:
        self.bindings: dict[Action, tuple[int, ...]] = dict(bindings or DEFAULT_KEYS)
        self.gamepads = GamepadInput()
        self._held_keys: set[int] = set()
        # action -> active sources ("key:<code>" / gamepad ids)
        self._held: dict[Action, set[str]] = {a: set() for a in ACTIONS}

    # ------------------------------------------------------------------ persistence
    @classmethod
    def load(cls, storage: Storage) -> InputMap:
        mapping = cls()
        data = storage.load_json(INPUT_FILE)
        for action in ACTIONS:
            names = data.get(action)
            if not isinstance(names, list):
                continue
            keys = []
            for name in names[:SLOTS]:
                try:
                    code = pygame.key.key_code(name) if isinstance(name, str) else None
                except ValueError:
                    code = None
                if code is not None and code not in RESERVED_KEYS:
                    keys.append(code)
            mapping.bindings[action] = tuple(keys)
        return mapping

    def save(self, storage: Storage) -> None:
        storage.save_json(
            INPUT_FILE,
            {a: [pygame.key.name(k) for k in keys] for a, keys in self.bindings.items()},
        )

    # ------------------------------------------------------------------ bindings
    def action_for_key(self, key: int) -> Action | None:
        for action, keys in self.bindings.items():
            if key in keys:
                return action
        return FIXED_KEYS.get(key)

    def bind(self, action: Action, slot: int, key: int) -> None:
        """Bind ``key`` to ``action``'s ``slot``, unbinding it from anything else.

        Raises ``ValueError`` for reserved keys, or if "pause" would be left
        without a key (there would be no way to open the pause menu).
        """
        if key in RESERVED_KEYS:
            raise ValueError(f"{key_label(key)} is reserved")
        bindings = {a: tuple(k for k in keys if k != key) for a, keys in self.bindings.items()}
        slots = list(self.bindings[action])
        if slot < len(slots):
            slots[slot] = key
        else:
            slots.append(key)
        bindings[action] = tuple(dict.fromkeys(slots))[:SLOTS]
        self._commit(bindings)

    def clear(self, action: Action, slot: int) -> None:
        """Remove the key in ``slot`` (``ValueError`` if it is the last pause key)."""
        slots = list(self.bindings[action])
        if slot < len(slots):
            del slots[slot]
        self._commit({**self.bindings, action: tuple(slots)})

    def _commit(self, bindings: dict[Action, tuple[int, ...]]) -> None:
        if not bindings["pause"]:
            raise ValueError("Pause needs at least one key")
        self.bindings = bindings
        self.release_all()

    def reset(self) -> None:
        self.bindings = dict(DEFAULT_KEYS)
        self.release_all()

    def keys_for(self, action: Action) -> tuple[int, ...]:
        return self.bindings.get(action, ())

    def label(self, action: Action) -> str:
        """The primary key's name for on-screen hints (e.g. ``"Space"``)."""
        keys = self.keys_for(action)
        return key_label(keys[0]) if keys else "—"

    def labels(self, *actions: Action, sep: str = "/") -> str:
        """Primary key names joined, e.g. ``labels("left", "right")`` → ``"←/→"``."""
        return sep.join(self.label(a) for a in actions)

    # ------------------------------------------------------------------ live state
    def held(self, action: Action) -> bool:
        """Whether ``action`` is currently held on any keyboard key or gamepad."""
        return bool(self._held[action])

    def release_all(self) -> list[pygame.event.Event]:
        """Forget held input (e.g. on focus loss); returns the ``ACTIONUP`` events."""
        events = [
            pygame.event.Event(ACTIONUP, action=a, source="system")
            for a in ACTIONS
            if self._held[a]
        ]
        self._held = {a: set() for a in ACTIONS}
        self._held_keys.clear()
        return events

    def translate(
        self, event: pygame.event.Event, text_mode: bool = False
    ) -> list[pygame.event.Event]:
        """Return the action events produced by ``event`` (often none).

        ``text_mode`` suppresses actions from printable keys (see module docs).
        """
        if event.type == pygame.WINDOWFOCUSLOST:
            return self.release_all()
        if event.type in (pygame.KEYDOWN, pygame.KEYUP):
            return list(self._from_key(event, text_mode))
        return [
            self._emit(action, pressed, source, "gamepad")
            for action, pressed, source in self.gamepads.translate(event)
            if pressed or source in self._held[action]
        ]

    def _from_key(self, event: pygame.event.Event, text_mode: bool) -> Iterable[pygame.event.Event]:
        key = event.key
        source = f"key:{key}"
        if event.type == pygame.KEYUP:
            self._held_keys.discard(key)
            for action in ACTIONS:
                if source in self._held[action]:
                    yield self._emit(action, False, source, "keyboard", key=key)
            return
        repeat = key in self._held_keys
        self._held_keys.add(key)
        bound = self.action_for_key(key)
        if bound is None:
            return
        typed = getattr(event, "unicode", "")
        if text_mode and typed and typed.isprintable():
            return
        yield self._emit(bound, True, source, "keyboard", key=key, repeat=repeat)

    def _emit(
        self,
        action: Action,
        pressed: bool,
        source: str,
        device: str,
        key: int | None = None,
        repeat: bool = False,
    ) -> pygame.event.Event:
        if pressed:
            self._held[action].add(source)
            return pygame.event.Event(
                ACTIONDOWN, action=action, repeat=repeat, source=device, key=key
            )
        self._held[action].discard(source)
        return pygame.event.Event(ACTIONUP, action=action, source=device, key=key)
